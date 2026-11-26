"""Konfiguratsiya: hamma narsa environment variables orqali."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional


def parse_ids(raw: str) -> tuple[int, ...]:
    out: list[int] = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError as exc:
            raise ValueError(f"ADMIN_IDS ichida noto'g'ri qiymat: {part!r}") from exc
    return tuple(out)


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: tuple[int, ...]
    database_url: str
    tasks_channel_id: str = ""      # boshlang'ich qiymat; admin paneldan o'zgartirish mumkin
    official_channel: str = ""      # majburiy obuna kanali (ixtiyoriy)
    port: int = 10000
    log_level: str = "INFO"
    keepalive_url: str = ""


def load_config(env: Optional[Mapping[str, str]] = None) -> Config:
    env = os.environ if env is None else env
    token = env.get("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable kerak")
    admins = parse_ids(env.get("ADMIN_IDS") or env.get("ADMIN_ID", ""))
    if not admins:
        raise RuntimeError("ADMIN_IDS (yoki ADMIN_ID) environment variable kerak")
    db = env.get("DATABASE_URL", "").strip()
    if not db:
        raise RuntimeError("DATABASE_URL environment variable kerak")
    if db.startswith("postgres://"):
        db = "postgresql://" + db[len("postgres://"):]
    return Config(
        bot_token=token,
        admin_ids=admins,
        database_url=db,
        tasks_channel_id=env.get("TASKS_CHANNEL_ID", "").strip(),
        official_channel=env.get("OFFICIAL_CHANNEL", "").strip(),
        port=int(env.get("PORT", "10000")),
        log_level=env.get("LOG_LEVEL", "INFO").upper(),
        keepalive_url=env.get("RENDER_EXTERNAL_URL", env.get("KEEPALIVE_URL", "")).strip(),
    )
