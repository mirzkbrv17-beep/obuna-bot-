from __future__ import annotations

from typing import Optional

from config import Config


async def upsert_user(db, tg_user) -> tuple[dict, bool]:
    row = await db.fetchrow(
        """INSERT INTO users (id, username, full_name) VALUES ($1,$2,$3)
           ON CONFLICT (id) DO UPDATE
             SET username = EXCLUDED.username, full_name = EXCLUDED.full_name, last_seen = now()
           RETURNING *, (xmax = 0) AS is_new""",
        tg_user.id, tg_user.username, tg_user.full_name or "",
    )
    data = dict(row)
    return data, bool(data.pop("is_new"))


def is_unlimited(cfg: Config, user: dict) -> bool:
    """Admin (ID bo'yicha) va VIP foydalanuvchilar uchun cheksiz coin."""
    return user["id"] in cfg.admin_ids or bool(user.get("is_vip"))


async def find_user(db, query: str) -> Optional[dict]:
    q = query.strip()
    if q.lstrip("-").isdigit():
        row = await db.fetchrow("SELECT * FROM users WHERE id=$1", int(q))
    else:
        row = await db.fetchrow("SELECT * FROM users WHERE lower(username)=lower($1)", q.lstrip("@"))
    return dict(row) if row else None


async def adjust_balance(conn, user_id: int, amount: int, kind: str,
                         ref_id: Optional[int] = None, note: Optional[str] = None) -> int:
    """Balansni o'zgartiradi va tranzaksiyalar tarixiga yozadi (tranzaksiya ichida chaqiriladi)."""
    bal = await conn.fetchval(
        "UPDATE users SET balance = balance + $2 WHERE id=$1 RETURNING balance", user_id, amount)
    if bal is None:
        raise LookupError(f"user {user_id} topilmadi")
    await conn.execute(
        "INSERT INTO transactions(user_id, amount, balance_after, kind, ref_id, note) "
        "VALUES($1,$2,$3,$4,$5,$6)", user_id, amount, bal, kind, ref_id, note)
    return bal


async def register_referral(db, invited_id: int, referrer_id: int) -> bool:
    """Yangi foydalanuvchini referal sifatida yozadi. O'zini o'zi taklif qilish va qayta yozish bloklanadi."""
    if invited_id == referrer_id:
        return False
    async with db.tx() as c:
        ok = await c.fetchval("SELECT 1 FROM users WHERE id=$1 AND NOT is_banned", referrer_id)
        if not ok:
            return False
        status = await c.execute(
            "INSERT INTO referrals(invited_id, referrer_id) VALUES($1,$2) ON CONFLICT DO NOTHING",
            invited_id, referrer_id)
        if not status.endswith(" 1"):
            return False
        await c.execute("UPDATE users SET referrer_id=$2 WHERE id=$1 AND referrer_id IS NULL",
                        invited_id, referrer_id)
        return True
