"""Kanal/guruhni aniqlash, admin huquqlarini va a'zolikni tekshirish."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional, Union

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from aiogram.types import ChatMember

log = logging.getLogger(__name__)

INVITE = "invite"
MEMBER_STATUSES = {"creator", "administrator", "member"}
_USERNAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{3,31}")
_URL = re.compile(r"^(?:https?://)?(?:www\.)?(?:t|telegram)\.me/(.+)$", re.I)


class OrderError(Exception):
    """Foydalanuvchiga ko'rsatiladigan xato matni."""


@dataclass
class Target:
    chat_id: int
    title: str
    username: Optional[str]
    chat_type: str
    invite_link: str


def member_is_in(m: ChatMember) -> bool:
    if m.status in MEMBER_STATUSES:
        return True
    return m.status == "restricted" and bool(getattr(m, "is_member", False))


def parse_chat_ref(text: str) -> Union[int, str, None]:
    """@username, t.me havolasi yoki -100... ID. Yopiq taklif havolasi uchun INVITE qaytaradi."""
    t = (text or "").strip()
    if not t:
        return None
    if re.fullmatch(r"-\d{5,}", t):
        return int(t)
    if t.startswith("@") and _USERNAME.fullmatch(t[1:]):
        return t
    m = _URL.match(t)
    if m:
        parts = m.group(1).split("?")[0].strip("/").split("/")
        first = parts[0]
        if first.startswith("+") or first == "joinchat":
            return INVITE
        if first == "c" and len(parts) >= 2 and parts[1].isdigit():
            return int("-100" + parts[1])
        if _USERNAME.fullmatch(first):
            return "@" + first
        return None
    if _USERNAME.fullmatch(t):
        return "@" + t
    return None


async def bot_member(bot: Bot, chat_id: Union[int, str]) -> ChatMember:
    me = await bot.me()
    return await bot.get_chat_member(chat_id, me.id)


async def resolve_target(bot: Bot, user_id: int, ref: Union[int, str],
                         *, require_user_admin: bool = True) -> Target:
    try:
        chat = await bot.get_chat(ref)
    except (TelegramBadRequest, TelegramForbiddenError):
        raise OrderError("❌ Kanal/guruh topilmadi yoki bot unga kira olmaydi. "
                         "Botni avval admin qiling, so'ng havolani qayta yuboring.")
    if chat.type not in ("channel", "group", "supergroup"):
        raise OrderError("❌ Bu kanal yoki guruh emas.")
    try:
        me = await bot_member(bot, chat.id)
    except TelegramAPIError:
        raise OrderError("❌ Bot bu kanal/guruhda admin emas. Botni admin qiling va qayta yuboring.")
    if me.status not in ("administrator", "creator"):
        raise OrderError("❌ Bot bu kanal/guruhda admin emas. Botni admin qiling "
                         "(a'zolarni ko'rish va taklif qilish huquqi bilan) va qayta yuboring.")
    if not chat.username and me.status == "administrator" and not getattr(me, "can_invite_users", False):
        raise OrderError("❌ Yopiq kanal/guruh uchun botga «Foydalanuvchilarni taklif qilish» "
                         "huquqini bering va qayta yuboring.")
    if require_user_admin:
        try:
            um = await bot.get_chat_member(chat.id, user_id)
        except TelegramAPIError:
            raise OrderError("❌ Admin ekanligingizni tekshirib bo'lmadi.")
        if um.status not in ("administrator", "creator"):
            raise OrderError("❌ Faqat shu kanal/guruh adminlari buyurtma bera oladi.")
    if chat.username:
        link = f"https://t.me/{chat.username}"
    else:
        link = getattr(chat, "invite_link", None)
        if not link:
            try:
                link = (await bot.create_chat_invite_link(chat.id, name="ABU SUB BOT")).invite_link
            except TelegramAPIError:
                raise OrderError("❌ Taklif havolasini yaratib bo'lmadi. Botga taklif huquqini bering.")
    return Target(chat.id, chat.title or str(chat.id), chat.username, chat.type, link)


async def is_member(bot: Bot, chat_id: Union[int, str], user_id: int) -> bool:
    """A'zolikni tekshiradi. API xatosida istisno ko'taradi (chaqiruvchi hal qiladi)."""
    return member_is_in(await bot.get_chat_member(chat_id, user_id))


async def chat_photo(bot: Bot, chat_id: int) -> Optional[bytes]:
    try:
        chat = await bot.get_chat(chat_id)
        if not chat.photo:
            return None
        buf = await bot.download(chat.photo.big_file_id)
        return buf.read() if buf else None
    except TelegramAPIError:
        log.warning("Kanal rasmini olib bo'lmadi: %s", chat_id)
        return None
