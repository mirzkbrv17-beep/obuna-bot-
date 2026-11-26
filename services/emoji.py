"""Premium Custom Emoji boshqaruvi (admin paneldan sozlanadi) + oddiy emoji fallback."""
from __future__ import annotations

import re
from typing import Optional

DEFAULTS: dict[str, str] = {
    "order": "👥", "earn": "🪙", "balance": "👛", "orders": "📦", "referral": "👥", "profile": "👤",
    "coin": "🪙", "megaphone": "📢", "check": "✅", "wait": "⏳", "id": "🆔", "link": "🔗",
    "robot": "🤖", "back": "⬅️", "home": "🏠", "cross": "❌", "gift": "🎁", "warn": "⚠️",
    "crown": "👑", "stats": "📊", "settings": "⚙️", "box": "📦", "pic": "🏞",
}

DESCRIPTIONS: dict[str, str] = {
    "order": "Menyu: Obunachi buyurtma", "earn": "Menyu: Coin ishlash", "balance": "Menyu: Balansim",
    "orders": "Menyu: Buyurtmalarim", "referral": "Menyu: Referal", "profile": "Menyu: Profil",
    "coin": "Coin belgisi", "megaphone": "Kanal / e'lon", "check": "Tasdiqlash", "wait": "Qoldi",
    "id": "ID", "link": "Havola", "robot": "Botimiz", "back": "Orqaga", "home": "Asosiy menyu",
    "cross": "Bekor qilish", "gift": "Sovg'a", "warn": "Ogohlantirish", "crown": "VIP / sarlavha",
    "stats": "Statistika", "settings": "Sozlamalar", "box": "Buyurtma soni", "pic": "Post bezagi",
}

_TG_EMOJI_RE = re.compile(r'<tg-emoji emoji-id="\d+">(.*?)</tg-emoji>', re.S)


def strip_tg_emoji(text: str) -> str:
    return _TG_EMOJI_RE.sub(lambda m: m.group(1), text)


class EmojiManager:
    def __init__(self) -> None:
        self.ids: dict[str, str] = {}
        self.enabled = True

    async def load(self, db) -> None:
        rows = await db.fetch("SELECT key, custom_id FROM emoji")
        self.ids = {r["key"]: r["custom_id"] for r in rows}

    def custom_id(self, key: str) -> Optional[str]:
        return self.ids.get(key) if self.enabled else None

    def plain(self, key: str) -> str:
        return DEFAULTS.get(key, "•")

    def tg(self, key: str) -> str:
        cid = self.custom_id(key)
        if cid:
            return f'<tg-emoji emoji-id="{cid}">{self.plain(key)}</tg-emoji>'
        return self.plain(key)

    def fallback_for_id(self, cid: str) -> str:
        for key, value in self.ids.items():
            if value == cid:
                return self.plain(key)
        return "•"

    async def set(self, db, key: str, cid: str) -> None:
        if key not in DEFAULTS:
            raise KeyError(key)
        if not cid.isdigit():
            raise ValueError("Custom emoji ID faqat raqamlardan iborat bo'lishi kerak")
        await db.execute(
            "INSERT INTO emoji(key, custom_id) VALUES($1,$2) "
            "ON CONFLICT (key) DO UPDATE SET custom_id = EXCLUDED.custom_id", key, cid)
        self.ids[key] = cid

    async def clear(self, db, key: str) -> None:
        await db.execute("DELETE FROM emoji WHERE key=$1", key)
        self.ids.pop(key, None)


emoji = EmojiManager()


def E(key: str) -> str:
    return emoji.tg(key)
