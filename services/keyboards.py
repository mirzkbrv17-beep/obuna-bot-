"""Tugmalar: custom emoji bo'lsa icon_custom_emoji_id, bo'lmasa oddiy emoji bilan."""
from __future__ import annotations

import re
from typing import Optional

from aiogram import F
from aiogram.types import (InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
                           ReplyKeyboardMarkup)

from services.emoji import emoji

MENU_LABELS = {
    "order": "Obunachi buyurtma", "earn": "Coin ishlash", "balance": "Balansim",
    "orders": "Buyurtmalarim", "referral": "Referal", "profile": "Profil",
}


def norm(text: Optional[str]) -> str:
    """Boshidagi emoji/belgilarni olib tashlaydi (custom icon bor-yo'qligidan qat'i nazar mos kelishi uchun)."""
    return re.sub(r"^[^\w]+", "", text or "").strip().lower()


_MENU_NORMS = {v.lower(): k for k, v in MENU_LABELS.items()}


def is_menu_text(text: Optional[str]) -> bool:
    return norm(text) in _MENU_NORMS


def is_menu(key: str):
    label = MENU_LABELS[key].lower()
    return F.text.func(lambda t: norm(t) == label)


def not_menu(message) -> bool:
    return not is_menu_text(getattr(message, "text", None))


def ib(key: str, text: str, *, cb: Optional[str] = None, url: Optional[str] = None,
       style: Optional[str] = None) -> InlineKeyboardButton:
    kw: dict = {}
    if cb is not None:
        kw["callback_data"] = cb
    if url is not None:
        kw["url"] = url
    if style:
        kw["style"] = style
    cid = emoji.custom_id(key)
    if cid:
        return InlineKeyboardButton(text=text, icon_custom_emoji_id=cid, **kw)
    return InlineKeyboardButton(text=f"{emoji.plain(key)} {text}", **kw)


def rb(key: str, text: str, style: Optional[str] = None) -> KeyboardButton:
    kw = {"style": style} if style else {}
    cid = emoji.custom_id(key)
    if cid:
        return KeyboardButton(text=text, icon_custom_emoji_id=cid, **kw)
    return KeyboardButton(text=f"{emoji.plain(key)} {text}", **kw)


def kb(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows])


def main_menu() -> ReplyKeyboardMarkup:
    L = MENU_LABELS
    return ReplyKeyboardMarkup(
        keyboard=[
            [rb("order", L["order"], "primary"), rb("earn", L["earn"], "success")],
            [rb("balance", L["balance"]), rb("orders", L["orders"])],
            [rb("referral", L["referral"]), rb("profile", L["profile"])],
        ],
        resize_keyboard=True, input_field_placeholder="Menyudan tanlang",
    )


def home_kb() -> InlineKeyboardMarkup:
    return kb([ib("home", "Asosiy menyu", cb="menu")])
