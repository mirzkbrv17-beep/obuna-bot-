import asyncio

import pytest

from services import coins, orders
from services.chats import Target
from services.users import adjust_balance, is_unlimited, register_referral
from tests.conftest import make_user


def target(chat_id=-100100, title="Kanal"):
    return Target(chat_id, title, "kanal", "channel", "https://t.me/kanal")


async def mk_order(db, owner=1, chat=-100100, qty=5, balance=1000, unlimited=False):
    await make_user(db, owner, balance)
    return (await orders.create_order(db, owner_id=owner, target=target(chat), quantity=qty, price=2,
                                      unlimited=unlimited, referral_reward=1)).order


async def test_concurrent_double_click_gives_one_coin(db):
    o = await mk_order(db)
    await make_user(db, 2)
    res = await asyncio.gather(*[coins.grant_subscription(db, 2, o["id"], 1) for _ in range(15)])
    assert [r.status for r in res].count("ok") == 1
    assert await db.fetchval("SELECT balance FROM users WHERE id=2") == 1
    assert await db.fetchval("SELECT count(*) FROM earnings") == 1
    assert await db.fetchval("SELECT count(*) FROM transactions WHERE user_id=2") == 1


async def test_one_coin_per_user_per_channel_across_orders(db):
    o1 = await mk_order(db, qty=2)
    await make_user(db, 2)
    assert (await coins.grant_subscription(db, 2, o1["id"], 1)).status == "ok"
    await orders.cancel_order(db, o1["id"], 1)
    o2 = (await orders.create_order(db, owner_id=1, target=target(), quantity=3, price=2,
                                    unlimited=False, referral_reward=1)).order
    assert (await coins.grant_subscription(db, 2, o2["id"], 1)).status == "already"
    await make_user(db, 3)
    assert (await coins.grant_subscription(db, 3, o2["id"], 1)).status == "ok"


async def test_leave_penalty_once_negative_balance_no_regrant(db):
    o = await mk_order(db)
    await make_user(db, 2)
    await coins.grant_subscription(db, 2, o["id"], 1)
    async with db.tx() as c:
        await adjust_balance(c, 2, -5, "admin_sub")
    r = await coins.revoke_earning(db, 2, o["chat_id"])
    assert r.balance == -5 and r.amount == 1
    assert await coins.revoke_earning(db, 2, o["chat_id"]) is None      # ikkinchi marta ayirilmaydi
    assert await db.fetchval("SELECT balance FROM users WHERE id=2") == -5
    assert (await coins.grant_subscription(db, 2, o["id"], 1)).status == "already"  # qayta obuna coin bermaydi
    # faol buyurtmada o'rin qayta bo'shadi
    assert await db.fetchval("SELECT done_count FROM orders WHERE id=$1", o["id"]) == 0


async def test_completion_and_closed(db):
    o = await mk_order(db, qty=2)
    for uid in (2, 3, 4):
        await make_user(db, uid)
    assert (await coins.grant_subscription(db, 2, o["id"], 1)).completed is False
    last = await coins.grant_subscription(db, 3, o["id"], 1)
    assert last.status == "ok" and last.completed is True
    assert (await coins.grant_subscription(db, 4, o["id"], 1)).status == "closed"
    row = await db.fetchrow("SELECT status, done_count, post_dirty FROM orders WHERE id=$1", o["id"])
    assert row["status"] == "completed" and row["done_count"] == 2


async def test_concurrent_grants_never_exceed_quantity(db):
    o = await mk_order(db, qty=3)
    for uid in range(10, 30):
        await make_user(db, uid)
    res = await asyncio.gather(*[coins.grant_subscription(db, u, o["id"], 1) for u in range(10, 30)])
    assert [r.status for r in res].count("ok") == 3
    assert await db.fetchval("SELECT done_count FROM orders WHERE id=$1", o["id"]) == 3


async def test_owner_cannot_earn_from_own_order(db):
    o = await mk_order(db)
    assert (await coins.grant_subscription(db, 1, o["id"], 1)).status == "own"


async def test_order_charges_and_insufficient(db):
    await make_user(db, 1, 5)
    with pytest.raises(orders.InsufficientCoins):
        await orders.create_order(db, owner_id=1, target=target(), quantity=10, price=2,
                                  unlimited=False, referral_reward=1)
    assert await db.fetchval("SELECT balance FROM users WHERE id=1") == 5
    r = await orders.create_order(db, owner_id=1, target=target(), quantity=2, price=2,
                                  unlimited=False, referral_reward=1)
    assert r.balance == 1 and r.order["cost"] == 4


async def test_concurrent_orders_cannot_overspend(db):
    await make_user(db, 1, 10)
    async def attempt(i):
        try:
            await orders.create_order(db, owner_id=1, target=target(-100200 - i), quantity=3, price=2,
                                      unlimited=False, referral_reward=1)
            return True
        except orders.InsufficientCoins:
            return False
    res = await asyncio.gather(*[attempt(i) for i in range(5)])
    assert res.count(True) == 1 and await db.fetchval("SELECT balance FROM users WHERE id=1") == 4


async def test_admin_and_vip_unlimited_no_charge(db, cfg):
    await make_user(db, 1000, 0)
    await make_user(db, 5, 0, vip=True)
    assert is_unlimited(cfg, {"id": 1000, "is_vip": False}) and is_unlimited(cfg, {"id": 5, "is_vip": True})
    assert not is_unlimited(cfg, {"id": 6, "is_vip": False})
    r = await orders.create_order(db, owner_id=1000, target=target(), quantity=50000, price=2,
                                  unlimited=True, referral_reward=1)
    assert r.order["cost"] == 0 and r.order["is_free"] and r.balance == 0
    assert await db.fetchval("SELECT count(*) FROM transactions") == 0


async def test_one_active_order_per_chat(db):
    await mk_order(db)
    with pytest.raises(orders.ActiveOrderExists):
        await orders.create_order(db, owner_id=1, target=target(), quantity=1, price=2,
                                  unlimited=False, referral_reward=1)


async def test_referral_rewarded_once_and_self_blocked(db):
    await make_user(db, 1)
    await make_user(db, 2, 100)
    assert not await register_referral(db, 1, 1)                       # o'zini taklif qilish
    assert await register_referral(db, 2, 1)
    assert not await register_referral(db, 2, 1)                       # takroriy yozuv
    assert await db.fetchval("SELECT balance FROM users WHERE id=1") == 0   # xarid qilmaguncha coin yo'q
    r = await orders.create_order(db, owner_id=2, target=target(-100301), quantity=1, price=2,
                                  unlimited=False, referral_reward=1)
    assert r.referrer_id == 1 and await db.fetchval("SELECT balance FROM users WHERE id=1") == 1
    r2 = await orders.create_order(db, owner_id=2, target=target(-100302), quantity=1, price=2,
                                   unlimited=False, referral_reward=1)
    assert r2.referrer_id is None and await db.fetchval("SELECT balance FROM users WHERE id=1") == 1


async def test_cancel_refunds_unfulfilled_part(db):
    o = await mk_order(db, qty=5, balance=100)           # 10 coin yechildi -> 90
    await make_user(db, 2)
    await coins.grant_subscription(db, 2, o["id"], 1)    # 1 ta bajarildi
    order, refund = await orders.cancel_order(db, o["id"], 1)
    assert refund == 8 and await db.fetchval("SELECT balance FROM users WHERE id=1") == 98
    assert await orders.cancel_order(db, o["id"], 1) is None
    assert await orders.cancel_order(db, o["id"], 999) is None


async def test_migrations_idempotent(db):
    await db.migrate()
    assert await db.fetchval("SELECT count(*) FROM schema_migrations") == 1
