"""Balans, buyurtmalar, referal, profil."""
from __future__ import annotations

from html import escape
from urllib.parse import quote

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message

from config import Config
from services import orders as orders_svc
from services.emoji import E
from services.keyboards import home_kb, ib, kb
from services.settings import settings
from services.users import is_unlimited

router = Router(name="account")

KIND_LABELS = {
    "earn": "Obuna uchun", "order": "Buyurtma", "refund": "Qaytarildi",
    "leave_penalty": "Chiqib ketish jarimasi", "referral": "Referal mukofoti",
    "admin_add": "Admin qo‘shdi", "admin_sub": "Admin ayirdi",
}
STATUS_LABELS = {"active": "🟢 Faol", "completed": "✅ Bajarildi", "cancelled": "🚫 Bekor qilindi"}


def fmt_balance(cfg: Config, user: dict) -> str:
    return "♾ Cheksiz" if is_unlimited(cfg, user) else str(user["balance"])


async def show_balance(message: Message, user: dict, db, cfg: Config) -> None:
    fresh = await db.fetchrow("SELECT * FROM users WHERE id=$1", user["id"])
    rows = await db.fetch(
        "SELECT * FROM transactions WHERE user_id=$1 ORDER BY id DESC LIMIT 8", user["id"])
    hist = "\n".join(
        f"{'➕' if r['amount'] > 0 else '➖'} {r['amount']:+d} · {KIND_LABELS.get(r['kind'], r['kind'])}"
        f" · {r['created_at']:%d.%m %H:%M}" for r in rows) or "Hozircha harakat yo‘q."
    await message.answer(
        f"{E('balance')} <b>Balansingiz</b>\n\n{E('coin')} Coin: <b>{fmt_balance(cfg, dict(fresh))}</b>\n\n"
        f"<b>So‘nggi harakatlar:</b>\n{hist}",
        reply_markup=kb([ib("earn", "Coin ishlash", cb="go_earn", style="success")],
                        [ib("home", "Asosiy menyu", cb="menu")]))


async def show_orders(message: Message, user: dict, db) -> None:
    rows = await orders_svc.user_orders(db, user["id"])
    if not rows:
        await message.answer(f"{E('orders')} Sizda hali buyurtmalar yo‘q.", reply_markup=home_kb())
        return
    lines, buttons = [], []
    for o in rows:
        lines.append(f"<b>#{o['id']}</b> · {escape(o['chat_title'][:40])}\n"
                     f"   {STATUS_LABELS[o['status']]} · {o['done_count']}/{o['quantity']} ta")
        if o["status"] == "active":
            buttons.append([ib("cross", f"#{o['id']} ni bekor qilish", cb=f"co:{o['id']}")])
    buttons.append([ib("home", "Asosiy menyu", cb="menu")])
    await message.answer(f"{E('orders')} <b>Buyurtmalarim</b>\n\n" + "\n\n".join(lines),
                         reply_markup=kb(*buttons))


@router.callback_query(F.data.startswith("co:"))
async def cancel_order_cb(cb: CallbackQuery, db, user: dict, worker) -> None:
    res = await orders_svc.cancel_order(db, int(cb.data[3:]), user["id"])
    if res is None:
        await cb.answer("Buyurtma topilmadi yoki allaqachon yakunlangan.", show_alert=True)
        return
    o, refund = res
    worker.wake()
    await cb.answer("Buyurtma bekor qilindi.")
    await cb.message.answer(
        f"🚫 <b>Buyurtma #{o['id']} bekor qilindi.</b>\n"
        f"Bajarilmagan qism uchun qaytarildi: <b>{refund}</b> {E('coin')}", reply_markup=home_kb())


async def show_referral(message: Message, user: dict, db, bot: Bot) -> None:
    me = await bot.me()
    link = f"https://t.me/{me.username}?start=ref_{user['id']}"
    total = await db.fetchval("SELECT count(*) FROM referrals WHERE referrer_id=$1", user["id"])
    paid = await db.fetchval(
        "SELECT count(*) FROM referrals WHERE referrer_id=$1 AND rewarded", user["id"])
    share = f"https://t.me/share/url?url={quote(link)}&text={quote('ABU SUB BOT — kanalingizga haqiqiy obunachilar!')}"
    await message.answer(
        f"{E('referral')} <b>Referal tizimi</b>\n\n"
        f"Do‘stingiz havolangiz orqali kirib, kamida <b>1 ta obunachi</b> buyurtma qilsa, "
        f"siz <b>+{settings.int('referral_reward')} coin</b> olasiz (har bir do‘st uchun bir marta).\n\n"
        f"{E('link')} Havolangiz:\n<code>{link}</code>\n\n"
        f"👥 Taklif qilinganlar: <b>{total}</b>\n{E('check')} Mukofot olingan: <b>{paid}</b>",
        reply_markup=kb([ib("megaphone", "Ulashish", url=share)], [ib("home", "Asosiy menyu", cb="menu")]))


async def show_profile(message: Message, user: dict, db, cfg: Config) -> None:
    fresh = dict(await db.fetchrow("SELECT * FROM users WHERE id=$1", user["id"]))
    n_orders = await db.fetchval("SELECT count(*) FROM orders WHERE owner_id=$1", user["id"])
    earned = await db.fetchval(
        "SELECT count(*) FROM earnings WHERE user_id=$1 AND status='active'", user["id"])
    role = "👑 Admin" if user["id"] in cfg.admin_ids else ("💎 VIP" if fresh["is_vip"] else "Oddiy")
    uname = f"@{escape(fresh['username'])}" if fresh["username"] else "—"
    await message.answer(
        f"{E('profile')} <b>Profil</b>\n\n{E('id')} ID: <code>{fresh['id']}</code>\n"
        f"Ism: {escape(fresh['full_name'])}\nUsername: {uname}\nStatus: {role}\n"
        f"{E('coin')} Balans: <b>{fmt_balance(cfg, fresh)}</b>\n"
        f"{E('orders')} Buyurtmalar: {n_orders}\n{E('check')} Faol obunalar: {earned}\n"
        f"Ro‘yxatdan o‘tgan: {fresh['created_at']:%d.%m.%Y}",
        reply_markup=home_kb())
