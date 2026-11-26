from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import load_config, parse_ids
from services.chats import INVITE, parse_chat_ref
from services.emoji import E, emoji, strip_tg_emoji
from services.fallback import strip_method
from services.keyboards import ib, is_menu_text, main_menu, norm
from services.tasks import post_kb, render_post


def test_parse_chat_ref():
    assert parse_chat_ref("@my_channel") == "@my_channel"
    assert parse_chat_ref("https://t.me/my_channel") == "@my_channel"
    assert parse_chat_ref("t.me/my_channel/15") == "@my_channel"
    assert parse_chat_ref("-1001234567890") == -1001234567890
    assert parse_chat_ref("https://t.me/c/1234567890/5") == -1001234567890
    assert parse_chat_ref("https://t.me/+AbCdEf123") == INVITE
    assert parse_chat_ref("https://t.me/joinchat/AAAA") == INVITE
    assert parse_chat_ref("salom dunyo") is None
    assert parse_chat_ref("") is None


def test_menu_matching_with_and_without_icon():
    assert norm("👥 Obunachi buyurtma") == "obunachi buyurtma"
    assert is_menu_text("Coin ishlash") and is_menu_text("🪙 Coin ishlash")
    assert not is_menu_text("salom")


def test_emoji_fallback_and_custom():
    emoji.ids, emoji.enabled = {}, True
    assert E("coin") == "🪙"
    emoji.ids = {"coin": "5368324170671202286"}
    assert E("coin") == '<tg-emoji emoji-id="5368324170671202286">🪙</tg-emoji>'
    btn = ib("coin", "Balans", cb="x")
    assert btn.icon_custom_emoji_id == "5368324170671202286" and btn.text == "Balans"
    emoji.enabled = False
    assert E("coin") == "🪙" and ib("coin", "Balans", cb="x").text == "🪙 Balans"
    emoji.ids, emoji.enabled = {}, True


def test_strip_method_removes_custom_emoji():
    emoji.ids = {"coin": "111"}
    m = SendMessage(chat_id=1, text='a <tg-emoji emoji-id="111">🪙</tg-emoji> b',
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="Ok", callback_data="c", icon_custom_emoji_id="111")]]))
    alt = strip_method(m)
    assert alt.text == "a 🪙 b"
    b = alt.reply_markup.inline_keyboard[0][0]
    assert b.icon_custom_emoji_id is None and b.text == "🪙 Ok"
    assert strip_method(SendMessage(chat_id=1, text="plain")) is None
    emoji.ids = {}
    assert strip_tg_emoji('<tg-emoji emoji-id="1">x</tg-emoji>') == "x"


def test_post_render():
    emoji.ids = {}
    o = {"id": 7, "chat_id": -1001, "chat_title": "Kanal <b>", "chat_type": "channel",
         "invite_link": "https://t.me/k", "quantity": 3, "done_count": 1}
    t = render_post(o)
    assert "Buyurtma: 3 ta" in t and "Bajarildi: 1 ta" in t and "Qoldi: 2 ta" in t
    assert "&lt;b&gt;" in t and "-1001" in t
    kbd = post_kb(o, "mybot")
    assert [b.text for r in kbd.inline_keyboard for b in r][1:] == ["✅ Tasdiqlash", "🤖 Botimiz"]
    assert kbd.inline_keyboard[1][0].callback_data == "ck:7"


def test_main_menu_has_six_buttons():
    assert sum(len(r) for r in main_menu().keyboard) == 6


def test_config():
    assert parse_ids("1, 2;3") == (1, 2, 3)
    c = load_config({"BOT_TOKEN": "t", "ADMIN_IDS": "5", "DATABASE_URL": "postgres://u@h/db"})
    assert c.database_url.startswith("postgresql://") and c.admin_ids == (5,)
    for bad in ({}, {"BOT_TOKEN": "t"}, {"BOT_TOKEN": "t", "ADMIN_IDS": "1"}):
        try:
            load_config(bad)
            assert False
        except RuntimeError:
            pass
