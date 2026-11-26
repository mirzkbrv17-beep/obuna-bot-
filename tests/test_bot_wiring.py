"""Dispatcher + handlerlar ulanishini soxta Telegram sessiyasi bilan tekshiradi."""
from datetime import datetime

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.types import Chat, Message, MessageEntity, Update, User

from bot import build_dispatcher
from handlers.middleware import UserMiddleware  # noqa: F401
from services.settings import settings
from services.tasks import PostWorker


class MockSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []

    async def close(self):
        pass

    async def stream_content(self, *a, **k):
        yield b""

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        name = type(method).__name__
        if name == "GetMe":
            return User(id=999, is_bot=True, first_name="B", username="absub_bot")
        if name == "SendMessage":
            return Message(message_id=len(self.calls), date=datetime.now(),
                           chat=Chat(id=method.chat_id, type="private"), text=method.text)
        return True

    def texts(self):
        return [getattr(c, "text", "") or "" for c in self.calls if type(c).__name__ == "SendMessage"]


def upd(uid, text, n=1):
    ents = [MessageEntity(type="bot_command", offset=0, length=len(text.split()[0]))] if text.startswith("/") else None
    return Update(update_id=n, message=Message(
        message_id=n, date=datetime.now(), chat=Chat(id=uid, type="private"),
        from_user=User(id=uid, is_bot=False, first_name="Ali"), text=text, entities=ents))


async def test_start_menu_and_order_flow(db, cfg):
    sess = MockSession()
    bot = Bot("123:abc", session=sess)
    worker = PostWorker(bot, db)
    dp = build_dispatcher(db, cfg, worker)
    await dp.feed_update(bot, upd(77, "/start"))
    assert any("xush kelibsiz" in t for t in sess.texts())
    await dp.feed_update(bot, upd(77, "👛 Balansim", 2))
    assert any("Balansingiz" in t for t in sess.texts())
    await dp.feed_update(bot, upd(77, "👥 Obunachi buyurtma", 3))      # balans 0 -> Coin ishlashga yo'naltiradi
    assert any("Coin yetarli emas" in t for t in sess.texts())
    await db.execute("UPDATE users SET balance=100 WHERE id=77")
    await dp.feed_update(bot, upd(77, "Obunachi buyurtma", 4))         # custom icon holati (emojisiz matn)
    assert any("Nechta obunachi" in t for t in sess.texts())
    await dp.feed_update(bot, upd(77, "abc", 5))
    assert any("faqat son" in t for t in sess.texts())
    await dp.feed_update(bot, upd(77, "20", 6))
    assert any("havolasini yuboring" in t for t in sess.texts())
    await dp.feed_update(bot, upd(77, "👤 Profil", 7))                  # menyu FSM holatini bekor qiladi
    assert any("Profil" in t for t in sess.texts())
    await dp.feed_update(bot, upd(77, "👥 Referal", 8))
    assert any("start=ref_77" in t for t in sess.texts())


async def test_referral_start_only_for_new_users(db, cfg):
    sess = MockSession()
    bot = Bot("123:abc", session=sess)
    dp = build_dispatcher(db, cfg, PostWorker(bot, db))
    await dp.feed_update(bot, upd(10, "/start"))
    await dp.feed_update(bot, upd(20, "/start ref_10", 2))
    assert await db.fetchval("SELECT referrer_id FROM users WHERE id=20") == 10
    await dp.feed_update(bot, upd(10, "/start ref_20", 3))             # mavjud foydalanuvchi referal bo'la olmaydi
    assert await db.fetchval("SELECT referrer_id FROM users WHERE id=10") is None
    await dp.feed_update(bot, upd(30, "/start ref_30", 4))             # o'zini o'zi
    assert await db.fetchval("SELECT referrer_id FROM users WHERE id=30") is None
    await dp.feed_update(bot, upd(1000, "/admin", 5))
    assert any("Admin panel" in t for t in sess.texts())
    n = len(sess.texts())
    await dp.feed_update(bot, upd(10, "/admin", 6))                    # oddiy foydalanuvchiga admin panel yo'q
    assert len(sess.texts()) == n
