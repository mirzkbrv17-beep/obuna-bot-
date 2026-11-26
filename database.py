"""PostgreSQL (asyncpg) ulanishi va migratsiyalar."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Optional

import asyncpg

log = logging.getLogger(__name__)
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class Database:
    def __init__(self, dsn: str, *, max_size: int = 10) -> None:
        self.dsn = dsn
        self.max_size = max_size
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(
            self.dsn, min_size=1, max_size=self.max_size, command_timeout=30
        )

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def migrate(self) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
            # bir vaqtda bir nechta nusxa migratsiya qilmasligi uchun
            await conn.execute("SELECT pg_advisory_lock(7770001)")
            try:
                done = {r["name"] for r in await conn.fetch("SELECT name FROM schema_migrations")}
                for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                    if path.name in done:
                        continue
                    log.info("Migratsiya: %s", path.name)
                    async with conn.transaction():
                        await conn.execute(path.read_text(encoding="utf-8"))
                        await conn.execute(
                            "INSERT INTO schema_migrations(name) VALUES($1)", path.name
                        )
            finally:
                await conn.execute("SELECT pg_advisory_unlock(7770001)")

    async def fetch(self, query: str, *args: Any):
        assert self.pool is not None
        return await self.pool.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any):
        assert self.pool is not None
        return await self.pool.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: Any):
        assert self.pool is not None
        return await self.pool.fetchval(query, *args)

    async def execute(self, query: str, *args: Any):
        assert self.pool is not None
        return await self.pool.execute(query, *args)

    @asynccontextmanager
    async def tx(self) -> AsyncIterator[asyncpg.Connection]:
        """Bitta PostgreSQL tranzaksiyasi."""
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                yield conn
