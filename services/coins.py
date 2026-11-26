"""Coin berish / qaytarib olish. Takroriy coin PostgreSQL UNIQUE + tranzaksiyalar bilan bloklanadi."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from services.users import adjust_balance


@dataclass
class GrantResult:
    status: str            # ok | closed | own | already
    balance: int = 0
    completed: bool = False
    reward: int = 0


async def grant_subscription(db, user_id: int, order_id: int, reward: int) -> GrantResult:
    async with db.tx() as c:
        order = await c.fetchrow("SELECT * FROM orders WHERE id=$1 FOR UPDATE", order_id)
        if order is None or order["status"] != "active" or order["done_count"] >= order["quantity"]:
            return GrantResult("closed")
        if order["owner_id"] == user_id:
            return GrantResult("own")
        ins = await c.fetchrow(
            "INSERT INTO earnings(user_id, chat_id, order_id, amount) VALUES($1,$2,$3,$4) "
            "ON CONFLICT (user_id, chat_id) DO NOTHING RETURNING id",
            user_id, order["chat_id"], order_id, reward)
        if ins is None:
            return GrantResult("already")
        done = order["done_count"] + 1
        completed = done >= order["quantity"]
        await c.execute(
            "UPDATE orders SET done_count=$2, post_dirty=true, "
            "status = CASE WHEN $3 THEN 'completed' ELSE status END, "
            "completed_at = CASE WHEN $3 THEN now() ELSE completed_at END WHERE id=$1",
            order_id, done, completed)
        bal = await adjust_balance(c, user_id, reward, "earn", order_id,
                                   f"Obuna: {order['chat_title']}")
        return GrantResult("ok", bal, completed, reward)


@dataclass
class RevokeResult:
    balance: int
    amount: int
    order_id: int
    chat_id: int


async def revoke_earning(db, user_id: int, chat_id: int) -> Optional[RevokeResult]:
    """Kanaldan chiqib ketgan foydalanuvchidan coin ayiradi (faqat bir marta). Balans manfiy bo'lishi mumkin."""
    async with db.tx() as c:
        e = await c.fetchrow(
            "UPDATE earnings SET status='revoked', revoked_at=now() "
            "WHERE user_id=$1 AND chat_id=$2 AND status='active' RETURNING *", user_id, chat_id)
        if e is None:
            return None
        bal = await adjust_balance(c, user_id, -e["amount"], "leave_penalty", e["order_id"],
                                   "Kanaldan chiqib ketdi")
        # faol buyurtmada o'rin qayta bo'shaydi; yakunlangan buyurtma o'zgarmaydi
        await c.execute(
            "UPDATE orders SET done_count = GREATEST(done_count-1, 0), post_dirty=true "
            "WHERE id=$1 AND status='active'", e["order_id"])
        return RevokeResult(bal, e["amount"], e["order_id"], chat_id)
