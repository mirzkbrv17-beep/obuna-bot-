"""Custom emoji / tugma ikonkasi qabul qilinmasa, so'rovni oddiy emoji bilan qayta yuboradi."""
from __future__ import annotations

import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

from services.emoji import emoji, strip_tg_emoji

log = logging.getLogger(__name__)
_HINTS = ("emoji", "document_invalid", "button_icon", "icon", "style")


def _strip_markup(markup):
    if isinstance(markup, InlineKeyboardMarkup):
        rows = markup.inline_keyboard
    elif isinstance(markup, ReplyKeyboardMarkup):
        rows = markup.keyboard
    else:
        return markup, False
    changed = False
    new_rows = []
    for row in rows:
        new_row = []
        for b in row:
            cid = getattr(b, "icon_custom_emoji_id", None)
            if cid or getattr(b, "style", None):
                text = f"{emoji.fallback_for_id(cid)} {b.text}" if cid else b.text
                b = b.model_copy(update={"icon_custom_emoji_id": None, "style": None, "text": text})
                changed = True
            new_row.append(b)
        new_rows.append(new_row)
    if not changed:
        return markup, False
    field = "inline_keyboard" if isinstance(markup, InlineKeyboardMarkup) else "keyboard"
    return markup.model_copy(update={field: new_rows}), True


def strip_method(method):
    """Method nusxasini custom emoji'siz qaytaradi; o'zgartirish kerak bo'lmasa None."""
    upd: dict = {}
    for field in ("text", "caption"):
        v = getattr(method, field, None)
        if isinstance(v, str) and "<tg-emoji" in v:
            upd[field] = strip_tg_emoji(v)
    rm = getattr(method, "reply_markup", None)
    if rm is not None:
        new_rm, changed = _strip_markup(rm)
        if changed:
            upd["reply_markup"] = new_rm
    return method.model_copy(update=upd) if upd else None


class EmojiFallbackMiddleware(BaseRequestMiddleware):
    async def __call__(self, make_request, bot, method):
        try:
            return await make_request(bot, method)
        except TelegramBadRequest as exc:
            if any(h in str(exc).lower() for h in _HINTS):
                alt = strip_method(method)
                if alt is not None:
                    log.warning("Custom emoji rad etildi, oddiy emoji bilan qayta yuborilmoqda: %s", exc)
                    return await make_request(bot, alt)
            raise
