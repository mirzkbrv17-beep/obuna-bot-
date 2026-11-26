"""Vazifalar kanaliga post qo'yish/yangilash/o'chirish va egasiga xabar berish (fon ishchisi)."""
from __future__ import annotations

import asyncio
import logging
from html import escape
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import (TelegramAPIError, TelegramBadRequest, TelegramForbiddenError,
                                TelegramRetryAfter)
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup

from services.chats import chat_photo
from services.emoji import E
from services.keyboards import ib, kb
from services.settings import settings

log = logging.getLogger(__name__)


def render_post(o: dict) -> str:
    left = max(o["quantity"] - o["done_count"], 0)
    kind = "Kanalga" if o["chat_type"] == "channel" else "Guruhga"
    title = escape(o["chat_title"][:64])
    return (
        f"{E('megaphone')} <b>Yangi obuna vazifasi:</b> {title}\n\n"
        f"{E('pic')} {kind} kiring va obuna bo‘ling.\n"
        f"{E('id')} ID: <code>{o['chat_id']}</code>\n"
        f"{E('box')} Buyurtma: {o['quantity']} ta · {E('check')} Bajarildi: {o['done_count']} ta · "
        f"{E('wait')} Qoldi: {left} ta\n"
        f"{E('link')} <a href=\"{escape(o['invite_link'])}\">{title}</a>\n"
        f"{E('coin')} Tasdiqlangan obuna uchun: +{settings.int('earn_reward')} coin\n\n"
        f"«{kind} kirish» orqali obuna bo‘ling, keyin «Tasdiqlash» orqali botda a’zolikni tekshiring 👇"
    )


def post_kb(o: dict, bot_username: str) -> InlineKeyboardMarkup:
    kind = "Kanalga" if o["chat_type"] == "channel" else "Guruhga"
    return kb(
        [ib("megaphone", f"{kind} kirish", url=o["invite_link"])],
        [ib("check", "Tasdiqlash", cb=f"ck:{o['id']}", style="success"),
         ib("robot", "Botimiz", url=f"https://t.me/{bot_username}")],
    )


def tasks_chat() -> Optional[str]:
    v = settings.get("tasks_channel_id").strip()
    return v or None


class PostWorker:
    def __init__(self, bot: Bot, db) -> None:
        self.bot, self.db = bot, db
        self._wake = asyncio.Event()

    def wake(self) -> None:
        self._wake.set()

    async def run(self) -> None:
        while True:
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=10)
            except asyncio.TimeoutError:
                pass
            self._wake.clear()
            try:
                await self.cycle()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("PostWorker xatosi")
            await asyncio.sleep(1)   # bir postni soniyada 1 martadan ko'p tahrirlamaslik uchun

    async def cycle(self) -> None:
        await self._publish_missing()
        await self._refresh_dirty()
        await self._delete_finished()
        await self._notify_completed()

    async def _publish_missing(self) -> None:
        chat = tasks_chat()
        if not chat:
            return
        rows = await self.db.fetch(
            "SELECT * FROM orders WHERE status='active' AND post_message_id IS NULL ORDER BY id LIMIT 20")
        username = (await self.bot.me()).username
        for r in rows:
            o = dict(r)
            try:
                photo = await chat_photo(self.bot, o["chat_id"])
                text, markup = render_post(o), post_kb(o, username)
                if photo:
                    msg = await self.bot.send_photo(chat, BufferedInputFile(photo, "chat.jpg"),
                                                    caption=text, reply_markup=markup)
                else:
                    msg = await self.bot.send_message(chat, text, reply_markup=markup)
                await self.db.execute(
                    "UPDATE orders SET post_chat_id=$2, post_message_id=$3, post_has_photo=$4 "
                    "WHERE id=$1 AND post_message_id IS NULL",
                    o["id"], msg.chat.id, msg.message_id, bool(photo))
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
                return
            except TelegramAPIError as e:
                log.error("Postni joylab bo'lmadi (order %s): %s", o["id"], e)
                return  # kanal sozlamasi xato bo'lsa keyingi siklda qayta uriniladi

    async def _refresh_dirty(self) -> None:
        rows = await self.db.fetch(
            "UPDATE orders SET post_dirty=false WHERE id IN ("
            " SELECT id FROM orders WHERE status='active' AND post_dirty AND post_message_id IS NOT NULL"
            " ORDER BY id LIMIT 20) RETURNING *")
        if not rows:
            return
        username = (await self.bot.me()).username
        for r in rows:
            o = dict(r)
            text, markup = render_post(o), post_kb(o, username)
            try:
                if o["post_has_photo"]:
                    await self.bot.edit_message_caption(chat_id=o["post_chat_id"], message_id=o["post_message_id"],
                                                        caption=text, reply_markup=markup)
                else:
                    await self.bot.edit_message_text(text, chat_id=o["post_chat_id"],
                                                     message_id=o["post_message_id"], reply_markup=markup)
            except TelegramRetryAfter as e:
                await self.db.execute("UPDATE orders SET post_dirty=true WHERE id=$1", o["id"])
                await asyncio.sleep(e.retry_after)
            except TelegramBadRequest as e:
                msg = str(e).lower()
                if "not modified" in msg:
                    continue
                if "not found" in msg or "message_id_invalid" in msg:
                    # post qo'lda o'chirilgan -> qayta joylanadi
                    await self.db.execute("UPDATE orders SET post_message_id=NULL WHERE id=$1", o["id"])
                else:
                    log.error("Postni yangilab bo'lmadi (order %s): %s", o["id"], e)
            except TelegramAPIError as e:
                log.error("Postni yangilab bo'lmadi (order %s): %s", o["id"], e)

    async def _delete_finished(self) -> None:
        rows = await self.db.fetch(
            "SELECT * FROM orders WHERE status<>'active' AND post_message_id IS NOT NULL "
            "AND NOT post_deleted AND post_attempts < 10 ORDER BY id LIMIT 20")
        for r in rows:
            try:
                await self.bot.delete_message(r["post_chat_id"], r["post_message_id"])
                await self.db.execute("UPDATE orders SET post_deleted=true WHERE id=$1", r["id"])
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
                return
            except TelegramAPIError as e:
                gone = "not found" in str(e).lower()
                await self.db.execute(
                    "UPDATE orders SET post_attempts=post_attempts+1, post_deleted=$2 WHERE id=$1",
                    r["id"], gone)
                if not gone:
                    log.error("Postni o'chirib bo'lmadi (order %s): %s", r["id"], e)

    async def _notify_completed(self) -> None:
        rows = await self.db.fetch(
            "UPDATE orders SET owner_notified=true WHERE id IN ("
            " SELECT id FROM orders WHERE status='completed' AND NOT owner_notified LIMIT 20) RETURNING *")
        for o in rows:
            text = (f"{E('check')} <b>Buyurtma #{o['id']} to‘liq bajarildi!</b>\n\n"
                    f"{E('megaphone')} {escape(o['chat_title'])}\n"
                    f"{E('box')} {o['quantity']} ta obunachi qo‘shildi.\n\n"
                    f"Yana buyurtma berish uchun «Obunachi buyurtma» tugmasini bosing.")
            try:
                await self.bot.send_message(o["owner_id"], text)
            except (TelegramForbiddenError, TelegramBadRequest):
                log.info("Egasiga xabar yuborib bo'lmadi: %s", o["owner_id"])
            except TelegramAPIError as e:
                log.warning("Xabar xatosi: %s", e)
