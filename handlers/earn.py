"""Coin ishlash: kanal posti ostidagi «Tasdiqlash» va majburiy obuna."""
from __future__ import annotations

import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message

from services.chats import is_member
from services.coins import grant_subscription
from services.emoji import E
from services.keyboards import ib, kb
from services.settings import settings

log = logging.getLogger(__name__)
router = Router(name="earn")


async def _tasks_link(bot: Bot) -> str:
    link = settings.get("tasks_channel_link")
    if link:
        return link
    chat_id = settings.get("tasks_channel_id")
    if chat_id:
        try:
            chat = await bot.get_chat(chat_id)
            if chat.username:
                return f"https://t.me/{chat.username}"
        except TelegramAPIError:
            pass
    return ""


async def show_earn(message: Message, bot: Bot) -> None:
    official = settings.get("official_channel")
    reward = settings.int("earn_reward")
    text = f"{E('earn')} <b>COIN ISHLASH</b>\n━━━━━━━━━━━━━━\n"
    rows = []
    if official:
        title = escape(settings.get("official_channel_title") or "Rasmiy kanal")
        text += (f"\nCoin ishlash uchun avval rasmiy kanalimizga obuna bo‘ling:\n"
                 f"{E('megaphone')} <b>{title}</b>\n\n")
        link = settings.get("official_channel_link")
        if link:
            rows.append([ib("megaphone", "Obuna bo‘lish", url=link)])
        rows.append([ib("check", "Obuna bo‘ldim", cb="earn_check")])
    text += (f"Yangi vazifalar vazifalar kanalida chiqadi.\n\n"
             f"1️⃣ «Vazifalar kanali» ni bosing\n2️⃣ Post ostidagi «Kanalga kirish» orqali obuna bo‘ling\n"
             f"3️⃣ «Tasdiqlash» ni bosing — <b>+{reward} {E('coin')}</b>\n\n"
             f"{E('warn')} Obunadan chiqib ketsangiz, coin qaytarib olinadi va qayta obuna coin bermaydi.")
    tl = await _tasks_link(bot)
    if tl:
        rows.append([ib("megaphone", "Vazifalar kanali", url=tl, style="primary")])
    else:
        text += "\n\n<i>Vazifalar kanali hali sozlanmagan.</i>"
    rows.append([ib("home", "Asosiy menyu", cb="menu")])
    await message.answer(text, reply_markup=kb(*rows))


@router.callback_query(F.data == "go_earn")
async def go_earn(cb: CallbackQuery, bot: Bot) -> None:
    await cb.answer()
    await show_earn(cb.message, bot)


async def official_ok(bot: Bot, user_id: int) -> bool:
    official = settings.get("official_channel")
    if not official:
        return True
    try:
        return await is_member(bot, official, user_id)
    except TelegramAPIError as e:
        log.warning("Majburiy obunani tekshirib bo'lmadi: %s", e)
        return True   # bot sozlamasi xato bo'lsa foydalanuvchini bloklamaymiz


@router.callback_query(F.data == "earn_check")
async def earn_check(cb: CallbackQuery, bot: Bot) -> None:
    if await official_ok(bot, cb.from_user.id):
        await cb.answer("✅ Obuna tasdiqlandi! Vazifalar kanaliga o‘ting.", show_alert=True)
    else:
        await cb.answer("❌ Siz hali rasmiy kanalga obuna bo‘lmagansiz.", show_alert=True)


@router.callback_query(F.data.startswith("ck:"))
async def confirm_subscription(cb: CallbackQuery, bot: Bot, db, worker) -> None:
    user_id = cb.from_user.id
    order = await db.fetchrow("SELECT * FROM orders WHERE id=$1", int(cb.data[3:]))
    if order is None or order["status"] != "active":
        await cb.answer("Bu vazifa yakunlangan.", show_alert=True)
        return
    if order["owner_id"] == user_id:
        await cb.answer("O‘z buyurtmangiz uchun coin olib bo‘lmaydi.", show_alert=True)
        return
    if await db.fetchval("SELECT 1 FROM earnings WHERE user_id=$1 AND chat_id=$2", user_id, order["chat_id"]):
        await cb.answer("Siz bu kanal/guruh uchun coin olgansiz. Qayta coin berilmaydi.", show_alert=True)
        return
    if not await official_ok(bot, user_id):
        await cb.answer("Avval rasmiy kanalimizga obuna bo‘ling (botda «Coin ishlash» bo‘limi).", show_alert=True)
        return
    try:
        inside = await is_member(bot, order["chat_id"], user_id)
    except TelegramAPIError as e:
        log.warning("Tasdiqlashda a'zolikni tekshirib bo'lmadi (order %s): %s", order["id"], e)
        await cb.answer("Tekshirib bo‘lmadi. Birozdan so‘ng qayta urinib ko‘ring.", show_alert=True)
        return
    if not inside:
        await cb.answer("❌ Siz hali obuna bo‘lmagansiz. Avval «Kanalga kirish» ni bosing.", show_alert=True)
        return
    if settings.bool("strict_join"):
        fresh = await db.fetchval(
            "SELECT joined_at >= $3 FROM join_events WHERE chat_id=$1 AND user_id=$2",
            order["chat_id"], user_id, order["created_at"])
        if not fresh:
            await cb.answer("Siz bu kanalga avvaldan a’zosiz — yangi obuna hisoblanmaydi. "
                            "Chiqib, qayta kirsangiz hisoblanadi.", show_alert=True)
            return
    res = await grant_subscription(db, user_id, order["id"], settings.int("earn_reward"))
    if res.status == "ok":
        worker.wake()
        await cb.answer(f"✅ +{res.reward} coin! Balansingiz: {res.balance}", show_alert=True)
    elif res.status == "already":
        await cb.answer("Siz bu kanal/guruh uchun coin olgansiz. Qayta coin berilmaydi.", show_alert=True)
    elif res.status == "own":
        await cb.answer("O‘z buyurtmangiz uchun coin olib bo‘lmaydi.", show_alert=True)
    else:
        await cb.answer("Bu vazifa allaqachon yakunlangan.", show_alert=True)
