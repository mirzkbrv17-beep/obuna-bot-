"""Vazifa posti hayot sikli: joylash -> tasdiqlash -> yangilash -> o'chirish -> egasiga xabar."""
from datetime import datetime

from aiogram import Bot
from aiogram.types import (CallbackQuery, Chat, ChatFullInfo, ChatMemberMember, Message,
                           Update, User)

from bot import build_dispatcher
from services import orders
from services.chats import Target
from services.settings import settings
from services.tasks import PostWorker
from tests.conftest import make_user
from tests.test_bot_wiring import MockSession


class LifecycleSession(MockSession):
    member = True

    async def make_request(self, bot, method, timeout=None):
        name = type(method).__name__
        if name == "GetChat":
            cid = int(method.chat_id) if str(method.chat_id).lstrip("-").isdigit() else -1001
            return ChatFullInfo.model_construct(id=cid, type="channel", title="T", photo=None)
        if name == "GetChatMember":
            status = "member" if self.member else "left"
            from aiogram.types import ChatMemberLeft
            u = User(id=method.user_id, is_bot=False, first_name="x")
            return ChatMemberMember(user=u) if self.member else ChatMemberLeft(user=u)
        return await super().make_request(bot, method, timeout)

    def of(self, name):
        return [c for c in self.calls if type(c).__name__ == name]


def cb_update(uid, data, n):
    msg = Message(message_id=5, date=datetime.now(), chat=Chat(id=-100999, type="channel"), text="post")
    return Update(update_id=n, callback_query=CallbackQuery(
        id=str(n), from_user=User(id=uid, is_bot=False, first_name="U"), chat_instance="ci",
        data=data, message=msg))


async def test_full_task_lifecycle(db, cfg):
    sess = LifecycleSession()
    bot = Bot("123:abc", session=sess)
    worker = PostWorker(bot, db)
    dp = build_dispatcher(db, cfg, worker)
    await settings.set("tasks_channel_id", "-100999")
    await make_user(db, 1, 100)
    await make_user(db, 2)
    o = (await orders.create_order(
        db, owner_id=1, target=Target(-100500, "Kanal A", "kanal_a", "channel", "https://t.me/kanal_a"),
        quantity=1, price=1, unlimited=False, referral_reward=1)).order

    await worker.cycle()                                   # post joylanadi
    sent = [c for c in sess.of("SendMessage") if str(c.chat_id) == "-100999"]
    assert sent and "Yangi obuna vazifasi" in sent[0].text and "Kanal A" in sent[0].text
    kb = sent[0].reply_markup.inline_keyboard
    assert kb[1][0].callback_data == f"ck:{o['id']}" and kb[0][0].url == "https://t.me/kanal_a"
    assert await db.fetchval("SELECT post_message_id FROM orders WHERE id=$1", o["id"])

    # a'zo, lekin yangi qo'shilgani yozilmagan (strict) -> coin yo'q
    await dp.feed_update(bot, cb_update(2, f"ck:{o['id']}", 1))
    assert "avvaldan" in sess.of("AnswerCallbackQuery")[-1].text
    assert await db.fetchval("SELECT balance FROM users WHERE id=2") == 0

    # a'zo emas -> coin yo'q
    sess.member = False
    await dp.feed_update(bot, cb_update(2, f"ck:{o['id']}", 2))
    assert "obuna bo‘lmagansiz" in sess.of("AnswerCallbackQuery")[-1].text
    sess.member = True

    await db.execute("INSERT INTO join_events(chat_id, user_id, joined_at) VALUES(-100500, 2, now())")
    await dp.feed_update(bot, cb_update(2, f"ck:{o['id']}", 3))
    assert "+1 coin" in sess.of("AnswerCallbackQuery")[-1].text
    assert await db.fetchval("SELECT balance FROM users WHERE id=2") == 1
    await dp.feed_update(bot, cb_update(2, f"ck:{o['id']}", 4))     # qayta bosish
    assert await db.fetchval("SELECT balance FROM users WHERE id=2") == 1

    await worker.cycle()                                   # buyurtma yakunlangan: post o'chadi, egaga xabar
    assert sess.of("DeleteMessage")
    assert any(str(c.chat_id) == "1" and "to‘liq bajarildi" in c.text for c in sess.of("SendMessage"))
    row = await db.fetchrow("SELECT status, post_deleted, owner_notified FROM orders WHERE id=$1", o["id"])
    assert row["status"] == "completed" and row["post_deleted"] and row["owner_notified"]


async def test_post_counters_refresh_on_progress(db, cfg):
    sess = LifecycleSession()
    bot = Bot("123:abc", session=sess)
    worker = PostWorker(bot, db)
    await settings.set("tasks_channel_id", "-100999")
    await make_user(db, 1, 100)
    await make_user(db, 2)
    o = (await orders.create_order(
        db, owner_id=1, target=Target(-100501, "Kanal B", None, "channel", "https://t.me/+abc"),
        quantity=3, price=1, unlimited=False, referral_reward=1)).order
    await worker.cycle()
    from services.coins import grant_subscription
    await grant_subscription(db, 2, o["id"], 1)
    await worker.cycle()
    edits = sess.of("EditMessageText")
    assert edits and "Bajarildi: 1 ta" in edits[-1].text and "Qoldi: 2 ta" in edits[-1].text
