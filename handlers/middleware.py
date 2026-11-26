from __future__ import annotations

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from config import Config
from services.users import upsert_user


class UserMiddleware(BaseMiddleware):
    """Foydalanuvchini ro'yxatdan o'tkazadi (private chat va callback'lar), bloklanganlarni to'xtatadi."""

    def __init__(self, db, cfg: Config) -> None:
        self.db, self.cfg = db, cfg

    async def __call__(self, handler, event, data):
        tg_user = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)
        if isinstance(event, Message) and event.chat.type != "private":
            return await handler(event, data)
        user, is_new = await upsert_user(self.db, tg_user)
        if user["is_banned"] and tg_user.id not in self.cfg.admin_ids:
            if isinstance(event, CallbackQuery):
                await event.answer("🚫 Siz bloklangansiz.", show_alert=True)
            else:
                await event.answer("🚫 Siz bloklangansiz.")
            return None
        data["user"], data["is_new"] = user, is_new
        return await handler(event, data)
