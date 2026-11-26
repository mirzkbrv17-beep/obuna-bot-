"""chat_member / my_chat_member yangilanishlari va guruhda /id."""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import ChatMemberUpdated, Message

from services.chats import member_is_in
from services.checker import notify_penalty
from services.coins import revoke_earning

log = logging.getLogger(__name__)
router = Router(name="events")


@router.chat_member()
async def on_chat_member(event: ChatMemberUpdated, bot: Bot, db, worker) -> None:
    was, now = member_is_in(event.old_chat_member), member_is_in(event.new_chat_member)
    uid, chat_id = event.new_chat_member.user.id, event.chat.id
    if now and not was:
        # faqat faol buyurtmasi bor chatlarda yangi qo'shilganlik dalilini saqlaymiz
        if await db.fetchval("SELECT 1 FROM orders WHERE chat_id=$1 AND status='active'", chat_id):
            await db.execute(
                "INSERT INTO join_events(chat_id, user_id, joined_at) VALUES($1,$2,now()) "
                "ON CONFLICT (chat_id, user_id) DO UPDATE SET joined_at=now()", chat_id, uid)
    elif was and not now:
        res = await revoke_earning(db, uid, chat_id)
        if res:
            log.info("Chiqib ketdi: user=%s chat=%s, %s coin ayirildi", uid, chat_id, res.amount)
            await notify_penalty(bot, uid, res)
            worker.wake()


@router.my_chat_member()
async def on_bot_status(event: ChatMemberUpdated, bot: Bot, db) -> None:
    if event.new_chat_member.status in ("administrator", "creator"):
        return
    order = await db.fetchrow("SELECT * FROM orders WHERE chat_id=$1 AND status='active'", event.chat.id)
    if order:
        try:
            await bot.send_message(
                order["owner_id"],
                f"⚠️ Bot «{order['chat_title']}» da admin emas. Buyurtma #{order['id']} ishlashi uchun "
                f"botni qayta admin qiling yoki «Buyurtmalarim» dan bekor qiling (coin qaytariladi).")
        except TelegramAPIError:
            pass


@router.message(Command("id"), F.chat.type.in_({"group", "supergroup"}))
async def group_id(message: Message, bot: Bot) -> None:
    try:
        m = await bot.get_chat_member(message.chat.id, message.from_user.id)
    except TelegramAPIError:
        return
    if m.status in ("administrator", "creator"):
        await message.reply(f"Chat ID: <code>{message.chat.id}</code>")
