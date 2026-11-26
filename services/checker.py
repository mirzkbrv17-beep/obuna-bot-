"""Obuna holatini muntazam tekshirish: chiqib ketganlardan coin ayiriladi."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter

from services.chats import is_member
from services.coins import revoke_earning
from services.emoji import E
from services.settings import settings

log = logging.getLogger(__name__)


async def notify_penalty(bot: Bot, user_id: int, res, title: str = "") -> None:
    try:
        await bot.send_message(
            user_id,
            f"{E('warn')} Siz obunadan chiqib ketdingiz, shuning uchun balansingizdan "
            f"<b>{res.amount} coin</b> ayirildi.\nJoriy balans: <b>{res.balance}</b> {E('coin')}\n"
            f"Qayta obuna bo‘lish coin qaytarmaydi.")
    except TelegramAPIError:
        pass


class SubscriptionChecker:
    def __init__(self, bot: Bot, db, post_worker=None) -> None:
        self.bot, self.db, self.post_worker = bot, db, post_worker

    async def run(self) -> None:
        last_cleanup = 0.0
        while True:
            try:
                n = await self.cycle()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("SubscriptionChecker xatosi")
                n = 0
            now = asyncio.get_event_loop().time()
            if now - last_cleanup > 86400:
                last_cleanup = now
                await self.db.execute("DELETE FROM join_events WHERE joined_at < now() - interval '90 days'")
            await asyncio.sleep(5 if n >= 100 else 60)

    async def cycle(self, limit: int = 100) -> int:
        hours = max(settings.int("recheck_hours"), 1)
        rows = await self.db.fetch(
            "SELECT user_id, chat_id FROM earnings WHERE status='active' "
            "AND last_checked_at < now() - make_interval(hours => $1) "
            "ORDER BY last_checked_at LIMIT $2", hours, limit)
        revoked = False
        for r in rows:
            uid, chat_id = r["user_id"], r["chat_id"]
            try:
                inside = await is_member(self.bot, chat_id, uid)
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
                continue
            except TelegramAPIError as e:
                # bot admin emas / chat topilmadi: jarima bermaymiz, keyinroq qayta tekshiramiz
                log.warning("A'zolikni tekshirib bo'lmadi chat=%s user=%s: %s", chat_id, uid, e)
                inside = True
            if not inside:
                res = await revoke_earning(self.db, uid, chat_id)
                if res:
                    revoked = True
                    await notify_penalty(self.bot, uid, res)
            await self.db.execute(
                "UPDATE earnings SET last_checked_at=now() WHERE user_id=$1 AND chat_id=$2", uid, chat_id)
            await asyncio.sleep(0.1)
        if revoked and self.post_worker:
            self.post_worker.wake()
        return len(rows)
