from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import asyncpg

from services.chats import Target
from services.users import adjust_balance


class InsufficientCoins(Exception):
    def __init__(self, balance: int, cost: int) -> None:
        super().__init__(f"balance={balance} cost={cost}")
        self.balance, self.cost = balance, cost


class ActiveOrderExists(Exception):
    pass


@dataclass
class CreateResult:
    order: dict
    balance: int
    referrer_id: Optional[int] = None
    referral_reward: int = 0


async def create_order(db, *, owner_id: int, target: Target, quantity: int, price: int,
                       unlimited: bool, referral_reward: int) -> CreateResult:
    cost = 0 if unlimited else quantity * price
    try:
        async with db.tx() as c:
            user = await c.fetchrow("SELECT * FROM users WHERE id=$1 FOR UPDATE", owner_id)
            if user is None:
                raise LookupError("user")
            if not unlimited and user["balance"] < cost:
                raise InsufficientCoins(user["balance"], cost)
            if await c.fetchval("SELECT 1 FROM orders WHERE chat_id=$1 AND status='active'", target.chat_id):
                raise ActiveOrderExists()
            order = await c.fetchrow(
                """INSERT INTO orders (owner_id, chat_id, chat_title, chat_username, chat_type,
                       invite_link, quantity, price_per_sub, cost, is_free)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING *""",
                owner_id, target.chat_id, target.title, target.username, target.chat_type,
                target.invite_link, quantity, price, cost, unlimited)
            balance = user["balance"]
            if cost > 0:
                balance = await adjust_balance(c, owner_id, -cost, "order", order["id"],
                                               f"Buyurtma #{order['id']}")
            referrer_id = None
            if cost > 0 and referral_reward > 0:
                ref = await c.fetchrow(
                    "UPDATE referrals SET rewarded=true, rewarded_at=now() "
                    "WHERE invited_id=$1 AND rewarded=false RETURNING referrer_id", owner_id)
                if ref:
                    referrer_id = ref["referrer_id"]
                    await adjust_balance(c, referrer_id, referral_reward, "referral", order["id"],
                                         f"Referal: {owner_id}")
            return CreateResult(dict(order), balance, referrer_id, referral_reward if referrer_id else 0)
    except asyncpg.UniqueViolationError as exc:
        raise ActiveOrderExists() from exc


async def cancel_order(db, order_id: int, owner_id: int) -> Optional[tuple[dict, int]]:
    """Faol buyurtmani bekor qiladi, bajarilmagan qismi uchun coin qaytariladi. (order, refund)"""
    async with db.tx() as c:
        o = await c.fetchrow(
            "SELECT * FROM orders WHERE id=$1 AND owner_id=$2 FOR UPDATE", order_id, owner_id)
        if o is None or o["status"] != "active":
            return None
        refund = 0 if o["is_free"] else (o["quantity"] - o["done_count"]) * o["price_per_sub"]
        await c.execute(
            "UPDATE orders SET status='cancelled', owner_notified=true, post_dirty=false WHERE id=$1",
            order_id)
        if refund > 0:
            await adjust_balance(c, owner_id, refund, "refund", order_id, f"Bekor: #{order_id}")
        return dict(o), refund


async def user_orders(db, user_id: int, limit: int = 10) -> list[dict]:
    rows = await db.fetch("SELECT * FROM orders WHERE owner_id=$1 ORDER BY id DESC LIMIT $2", user_id, limit)
    return [dict(r) for r in rows]
