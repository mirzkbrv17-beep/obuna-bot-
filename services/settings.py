"""Sozlamalar (narxlar, kanallar, ...). DB'da saqlanadi, xotirada keshlanadi."""
from __future__ import annotations

from typing import Optional

from config import Config
from services.emoji import emoji

DEFAULTS: dict[str, str] = {
    "price_per_sub": "1",
    "min_order": "10",
    "max_order": "10000",
    "earn_reward": "1",
    "referral_reward": "1",
    "recheck_hours": "6",
    "strict_join": "1",
    "use_custom_emoji": "1",
    "tasks_channel_id": "",
    "tasks_channel_link": "",
    "official_channel": "",
    "official_channel_link": "",
    "official_channel_title": "",
}

INT_KEYS = {
    "price_per_sub": "1 ta obunachi narxi (coin)",
    "min_order": "Minimal buyurtma (ta)",
    "max_order": "Maksimal buyurtma (ta)",
    "earn_reward": "Obuna uchun beriladigan coin",
    "referral_reward": "Referal mukofoti (coin)",
    "recheck_hours": "Obunani qayta tekshirish (soat)",
}
BOOL_KEYS = {
    "strict_join": "Faqat yangi qo'shilganlarga coin",
    "use_custom_emoji": "Premium custom emoji",
}


class Settings:
    def __init__(self) -> None:
        self._db = None
        self._cfg: Optional[Config] = None
        self._cache: dict[str, str] = {}

    def bind(self, db, cfg: Config) -> None:
        self._db, self._cfg = db, cfg

    async def load(self) -> None:
        rows = await self._db.fetch("SELECT key, value FROM settings")
        self._cache = {r["key"]: r["value"] for r in rows}
        emoji.enabled = self.bool("use_custom_emoji")

    def get(self, key: str) -> str:
        if key in self._cache:
            return self._cache[key]
        if self._cfg is not None:
            if key == "tasks_channel_id" and self._cfg.tasks_channel_id:
                return self._cfg.tasks_channel_id
            if key == "official_channel" and self._cfg.official_channel:
                return self._cfg.official_channel
        return DEFAULTS.get(key, "")

    def int(self, key: str) -> int:
        try:
            return int(self.get(key))
        except ValueError:
            return int(DEFAULTS[key])

    def bool(self, key: str) -> bool:
        return self.get(key) in ("1", "true", "True", "yes")

    async def set(self, key: str, value: str) -> None:
        await self._db.execute(
            "INSERT INTO settings(key, value) VALUES($1,$2) "
            "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()", key, value)
        self._cache[key] = value
        if key == "use_custom_emoji":
            emoji.enabled = self.bool(key)


settings = Settings()
