"""Admin panel (/admin). Faqat ADMIN_IDS dagi foydalanuvchilar uchun."""
from __future__ import annotations

import logging
from html import escape
from typing import Optional

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import BaseFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, TelegramObject

from config import Config
from services import users as users_svc
from services.chats import INVITE, OrderError, bot_member, parse_chat_ref, resolve_target
from services.emoji import DEFAULTS as EMOJI_DEFAULTS, DESCRIPTIONS as EMOJI_DESC, emoji
from services.keyboards import ib, kb, not_menu
from services.logs import log_admin
from services.settings import BOOL_KEYS, INT_KEYS, settings

log = logging.getLogger(__name__)
router = Router(name="admin")


class AdminFilter(BaseFilter):
    async def __call__(self, event: TelegramObject, cfg: Config) -> bool:
        u = getattr(event, "from_user", None)
        return bool(u and u.id in cfg.admin_ids)


router.message.filter(AdminFilter(), F.chat.type == "private")
router.callback_query.filter(AdminFilter())


class AdminStates(StatesGroup):
    find_user = State()
    amount = State()
    setting = State()
    emoji = State()
    tasks_channel = State()
    official_channel = State()


async def show(event, text: str, markup=None) -> None:
    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=markup)
            return
        except TelegramBadRequest:
            pass
        await event.message.answer(text, reply_markup=markup)
    else:
        await event.answer(text, reply_markup=markup)


def home_kb():
    return kb(
        [ib("stats", "Statistika", cb="adm:stats"), ib("order", "Foydalanuvchilar", cb="adm:users")],
        [ib("coin", "Coin kanali", cb="adm:tchan"), ib("megaphone", "Majburiy kanal", cb="adm:ochan")],
        [ib("settings", "Sozlamalar", cb="adm:settings"), ib("gift", "Premium emoji", cb="adm:emoji")],
        [ib("crown", "VIP ro‘yxati", cb="adm:vips"), ib("box", "Loglar", cb="adm:logs")],
    )


def back_kb():
    return kb([ib("back", "Admin panel", cb="adm:home")])


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await show(message, "👑 <b>Admin panel</b>", home_kb())


@router.callback_query(F.data == "adm:home")
async def cb_home(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb.answer()
    await show(cb, "👑 <b>Admin panel</b>", home_kb())


# ------------------------------------------------------------------ statistika
@router.callback_query(F.data == "adm:stats")
async def stats(cb: CallbackQuery, db) -> None:
    await cb.answer()
    q = db.fetchval
    users, vips = await q("SELECT count(*) FROM users"), await q("SELECT count(*) FROM users WHERE is_vip")
    new24 = await q("SELECT count(*) FROM users WHERE created_at > now() - interval '24 hours'")
    by = {r["status"]: r for r in await db.fetch(
        "SELECT status, count(*) AS n, COALESCE(sum(quantity),0) AS qty, COALESCE(sum(done_count),0) AS done "
        "FROM orders GROUP BY status")}
    g = lambda s, f: (by[s][f] if s in by else 0)  # noqa: E731
    coins = await q("SELECT COALESCE(sum(balance),0) FROM users")
    earned = await q("SELECT count(*) FROM earnings WHERE status='active'")
    revoked = await q("SELECT count(*) FROM earnings WHERE status='revoked'")
    refs = await q("SELECT count(*) FROM referrals"), await q("SELECT count(*) FROM referrals WHERE rewarded")
    await show(cb, (
        "📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{users}</b> (24 soatda +{new24}), VIP: {vips}\n"
        f"🪙 Umumiy balans: <b>{coins}</b>\n\n"
        f"📦 Buyurtmalar:\n  🟢 faol: {g('active', 'n')} ({g('active', 'done')}/{g('active', 'qty')})\n"
        f"  ✅ bajarilgan: {g('completed', 'n')}\n  🚫 bekor: {g('cancelled', 'n')}\n\n"
        f"✅ Faol obunalar: {earned} · ↩️ chiqib ketganlar: {revoked}\n"
        f"👥 Referallar: {refs[0]} (mukofot berilgan: {refs[1]})"), back_kb())


# ------------------------------------------------------------ foydalanuvchilar
def card_text(u: dict, n_orders: int) -> str:
    uname = f"@{escape(u['username'])}" if u["username"] else "—"
    return (f"👤 <b>{escape(u['full_name'])}</b> ({uname})\n🆔 <code>{u['id']}</code>\n"
            f"🪙 Balans: <b>{u['balance']}</b>\n💎 VIP: {'ha' if u['is_vip'] else 'yo‘q'} · "
            f"🚫 Ban: {'ha' if u['is_banned'] else 'yo‘q'}\n📦 Buyurtmalar: {n_orders}\n"
            f"📅 Ro‘yxatdan: {u['created_at']:%d.%m.%Y}")


def card_kb(u: dict):
    uid = u["id"]
    return kb(
        [ib("check", "Coin qo‘shish", cb=f"adm:u:{uid}:add", style="success"),
         ib("cross", "Coin ayirish", cb=f"adm:u:{uid}:sub", style="danger")],
        [ib("crown", "VIP bekor qilish" if u["is_vip"] else "VIP berish", cb=f"adm:u:{uid}:vip"),
         ib("warn", "Blokdan chiqarish" if u["is_banned"] else "Bloklash", cb=f"adm:u:{uid}:ban")],
        [ib("back", "Admin panel", cb="adm:home")])


async def send_card(event, db, uid: int) -> None:
    row = await db.fetchrow("SELECT * FROM users WHERE id=$1", uid)
    if row is None:
        await show(event, "Foydalanuvchi topilmadi.", back_kb())
        return
    n = await db.fetchval("SELECT count(*) FROM orders WHERE owner_id=$1", uid)
    await show(event, card_text(dict(row), n), card_kb(dict(row)))


@router.callback_query(F.data == "adm:users")
async def users_menu(cb: CallbackQuery, state: FSMContext, db) -> None:
    await cb.answer()
    await state.set_state(AdminStates.find_user)
    rows = await db.fetch("SELECT id, full_name FROM users ORDER BY created_at DESC LIMIT 8")
    buttons = [[ib("profile", f"{r['full_name'][:25] or r['id']} · {r['id']}", cb=f"adm:u:{r['id']}")] for r in rows]
    buttons.append([ib("back", "Admin panel", cb="adm:home")])
    await show(cb, "👥 <b>Foydalanuvchilar</b>\n\nID yoki @username yuboring, yoki so‘nggilardan tanlang:", kb(*buttons))


@router.message(AdminStates.find_user, not_menu)
async def find_user(message: Message, state: FSMContext, db) -> None:
    u = await users_svc.find_user(db, message.text or "")
    if not u:
        await message.answer("❌ Topilmadi. ID yoki @username yuboring.", reply_markup=back_kb())
        return
    await state.clear()
    await send_card(message, db, u["id"])


@router.callback_query(F.data.regexp(r"^adm:u:-?\d+$"))
async def open_card(cb: CallbackQuery, state: FSMContext, db) -> None:
    await cb.answer()
    await state.clear()
    await send_card(cb, db, int(cb.data.split(":")[2]))


@router.callback_query(F.data.regexp(r"^adm:u:-?\d+:(add|sub)$"))
async def ask_amount(cb: CallbackQuery, state: FSMContext) -> None:
    _, _, uid, op = cb.data.split(":")
    await cb.answer()
    await state.set_state(AdminStates.amount)
    await state.update_data(uid=int(uid), op=op)
    await show(cb, f"Qancha coin {'qo‘shamiz' if op == 'add' else 'ayiramiz'}? Son yuboring:", back_kb())


@router.message(AdminStates.amount, not_menu)
async def do_amount(message: Message, state: FSMContext, db, cfg: Config) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer("❌ Musbat butun son yuboring.", reply_markup=back_kb())
        return
    data = await state.get_data()
    await state.clear()
    amt = int(raw) * (1 if data["op"] == "add" else -1)
    async with db.tx() as c:
        try:
            bal = await users_svc.adjust_balance(
                c, data["uid"], amt, "admin_add" if amt > 0 else "admin_sub", None,
                f"admin {message.from_user.id}")
        except LookupError:
            await message.answer("Foydalanuvchi topilmadi.", reply_markup=back_kb())
            return
    await log_admin(db, message.from_user.id, "balance", str(data["uid"]), f"{amt:+d} -> {bal}")
    await message.answer(f"✅ Bajarildi. Yangi balans: <b>{bal}</b>")
    await send_card(message, db, data["uid"])


@router.callback_query(F.data.regexp(r"^adm:u:-?\d+:(vip|ban)$"))
async def toggle_flag(cb: CallbackQuery, db) -> None:
    _, _, uid, what = cb.data.split(":")
    col = "is_vip" if what == "vip" else "is_banned"
    row = await db.fetchrow(f"UPDATE users SET {col} = NOT {col} WHERE id=$1 RETURNING {col}", int(uid))
    if row is None:
        await cb.answer("Topilmadi", show_alert=True)
        return
    await log_admin(db, cb.from_user.id, what, uid, "yoqildi" if row[col] else "o‘chirildi")
    await cb.answer("Bajarildi")
    await send_card(cb, db, int(uid))


@router.callback_query(F.data == "adm:vips")
async def vips(cb: CallbackQuery, db) -> None:
    await cb.answer()
    rows = await db.fetch("SELECT id, full_name FROM users WHERE is_vip ORDER BY id LIMIT 40")
    buttons = [[ib("crown", f"{r['full_name'][:25]} · {r['id']}", cb=f"adm:u:{r['id']}")] for r in rows]
    buttons.append([ib("back", "Admin panel", cb="adm:home")])
    await show(cb, f"👑 <b>VIP foydalanuvchilar</b> ({len(rows)})" if rows else "VIP foydalanuvchilar yo‘q.", kb(*buttons))


# ------------------------------------------------------------------- kanallar
async def _channel_prompt(cb: CallbackQuery, state: FSMContext, st: State, title: str, current: str, clear_cb: Optional[str]):
    await cb.answer()
    await state.set_state(st)
    rows = []
    if clear_cb:
        rows.append([ib("cross", "O‘chirish", cb=clear_cb, style="danger")])
    rows.append([ib("back", "Admin panel", cb="adm:home")])
    await show(cb, f"{title}\n\nHozirgi: <code>{escape(current) or '—'}</code>\n\n"
                   "Yangi kanalni yuboring: <code>@username</code>, ID (<code>-100...</code>) yoki undan post forward qiling.\n"
                   "Bot u yerda admin bo‘lishi kerak.", kb(*rows))


@router.callback_query(F.data == "adm:tchan")
async def tchan(cb: CallbackQuery, state: FSMContext) -> None:
    await _channel_prompt(cb, state, AdminStates.tasks_channel, "🪙 <b>Coin ishlash (vazifalar) kanali</b>",
                          settings.get("tasks_channel_id"), None)


@router.callback_query(F.data == "adm:ochan")
async def ochan(cb: CallbackQuery, state: FSMContext) -> None:
    await _channel_prompt(cb, state, AdminStates.official_channel, "📢 <b>Majburiy obuna kanali</b> (ixtiyoriy)",
                          settings.get("official_channel"), "adm:ochan:clear")


@router.callback_query(F.data == "adm:ochan:clear")
async def ochan_clear(cb: CallbackQuery, state: FSMContext, db) -> None:
    await state.clear()
    for k in ("official_channel", "official_channel_link", "official_channel_title"):
        await settings.set(k, "")
    await log_admin(db, cb.from_user.id, "official_channel", "", "o‘chirildi")
    await cb.answer("O‘chirildi")
    await show(cb, "✅ Majburiy obuna o‘chirildi.", back_kb())


async def _ref_from_message(message: Message):
    origin = getattr(message, "forward_origin", None)
    if origin is not None and getattr(origin, "chat", None) is not None:
        return origin.chat.id
    return parse_chat_ref(message.text or "")


@router.message(AdminStates.tasks_channel, not_menu)
async def set_tasks_channel(message: Message, state: FSMContext, bot: Bot, db, worker) -> None:
    ref = await _ref_from_message(message)
    if ref in (None, INVITE):
        await message.answer("❌ Kanalni @username, ID yoki forward orqali yuboring.", reply_markup=back_kb())
        return
    try:
        t = await resolve_target(bot, message.from_user.id, ref, require_user_admin=False)
        me = await bot_member(bot, t.chat_id)
        if t.chat_type == "channel" and getattr(me, "can_post_messages", True) is False:
            raise OrderError("❌ Botga «Xabarlarni joylash» huquqini bering.")
        if getattr(me, "can_delete_messages", True) is False or getattr(me, "can_edit_messages", True) is False:
            raise OrderError("❌ Botga «Xabarlarni tahrirlash» va «o‘chirish» huquqlarini bering.")
    except OrderError as e:
        await message.answer(str(e), reply_markup=back_kb())
        return
    await state.clear()
    await settings.set("tasks_channel_id", str(t.chat_id))
    await settings.set("tasks_channel_link", t.invite_link)
    await log_admin(db, message.from_user.id, "tasks_channel", str(t.chat_id), t.title)
    worker.wake()
    await message.answer(f"✅ Vazifalar kanali: <b>{escape(t.title)}</b>", reply_markup=back_kb())


@router.message(AdminStates.official_channel, not_menu)
async def set_official_channel(message: Message, state: FSMContext, bot: Bot, db) -> None:
    ref = await _ref_from_message(message)
    if ref in (None, INVITE):
        await message.answer("❌ Kanalni @username, ID yoki forward orqali yuboring.", reply_markup=back_kb())
        return
    try:
        t = await resolve_target(bot, message.from_user.id, ref, require_user_admin=False)
    except OrderError as e:
        await message.answer(str(e), reply_markup=back_kb())
        return
    await state.clear()
    await settings.set("official_channel", str(t.chat_id))
    await settings.set("official_channel_link", t.invite_link)
    await settings.set("official_channel_title", t.title)
    await log_admin(db, message.from_user.id, "official_channel", str(t.chat_id), t.title)
    await message.answer(f"✅ Majburiy obuna kanali: <b>{escape(t.title)}</b>", reply_markup=back_kb())


# ------------------------------------------------------------------ sozlamalar
def settings_view():
    lines, rows = ["⚙️ <b>Bot sozlamalari</b>\n"], []
    for k, label in INT_KEYS.items():
        lines.append(f"• {label}: <b>{settings.get(k)}</b>")
        rows.append([ib("settings", label, cb=f"adm:s:{k}")])
    for k, label in BOOL_KEYS.items():
        on = settings.bool(k)
        lines.append(f"• {label}: <b>{'yoqilgan' if on else 'o‘chirilgan'}</b>")
        rows.append([ib("check" if on else "cross", f"{label}: {'ON' if on else 'OFF'}", cb=f"adm:t:{k}")])
    rows.append([ib("back", "Admin panel", cb="adm:home")])
    return "\n".join(lines), kb(*rows)


@router.callback_query(F.data == "adm:settings")
async def settings_menu(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb.answer()
    text, markup = settings_view()
    await show(cb, text, markup)


@router.callback_query(F.data.startswith("adm:t:"))
async def toggle_setting(cb: CallbackQuery, db) -> None:
    key = cb.data[6:]
    if key not in BOOL_KEYS:
        await cb.answer()
        return
    await settings.set(key, "0" if settings.bool(key) else "1")
    await log_admin(db, cb.from_user.id, "setting", key, settings.get(key))
    await cb.answer("Saqlandi")
    text, markup = settings_view()
    await show(cb, text, markup)


@router.callback_query(F.data.startswith("adm:s:"))
async def ask_setting(cb: CallbackQuery, state: FSMContext) -> None:
    key = cb.data[6:]
    if key not in INT_KEYS:
        await cb.answer()
        return
    await cb.answer()
    await state.set_state(AdminStates.setting)
    await state.update_data(key=key)
    await show(cb, f"<b>{INT_KEYS[key]}</b>\nHozirgi: <b>{settings.get(key)}</b>\n\nYangi qiymatni yuboring (butun son):", back_kb())


@router.message(AdminStates.setting, not_menu)
async def save_setting(message: Message, state: FSMContext, db) -> None:
    raw = (message.text or "").strip()
    key = (await state.get_data())["key"]
    if not raw.isdigit():
        await message.answer("❌ Butun son yuboring.", reply_markup=back_kb())
        return
    val = int(raw)
    minimum = 0 if key == "referral_reward" else 1
    if val < minimum:
        await message.answer(f"❌ Qiymat kamida {minimum} bo‘lishi kerak.", reply_markup=back_kb())
        return
    if key == "min_order" and val > settings.int("max_order") or key == "max_order" and val < settings.int("min_order"):
        await message.answer("❌ Minimal buyurtma maksimaldan katta bo‘lmasligi kerak.", reply_markup=back_kb())
        return
    old = settings.get(key)
    await settings.set(key, str(val))
    await state.clear()
    await log_admin(db, message.from_user.id, "setting", key, f"{old} -> {val}")
    text, markup = settings_view()
    await message.answer("✅ Saqlandi.\n\n" + text, reply_markup=markup)


# --------------------------------------------------------------- premium emoji
def emoji_view():
    rows = []
    for k in EMOJI_DEFAULTS:
        mark = "✅" if k in emoji.ids else "—"
        rows.append([ib(k, f"{EMOJI_DESC[k]} [{mark}]", cb=f"adm:e:{k}")])
    rows.append([ib("back", "Admin panel", cb="adm:home")])
    return (
        "💎 <b>Premium custom emoji</b>\n\nO‘zgartirmoqchi bo‘lgan joyni tanlang. Keyin <b>premium emoji</b> yuboring "
        "(ID o‘zi aniqlanadi), yoki emoji ID raqamini yozing. <code>0</code> — o‘chirish (oddiy emoji ishlaydi).\n\n"
        "ℹ️ Telegram qoidasi: custom emoji faqat bot egasida Telegram Premium bo‘lsa yoki botga Fragment'da "
        "qo‘shimcha username sotib olingan bo‘lsa ko‘rinadi; boshqa hollarda avtomatik oddiy emoji ko‘rsatiladi."
    ), kb(*rows)


@router.callback_query(F.data == "adm:emoji")
async def emoji_menu(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb.answer()
    text, markup = emoji_view()
    await show(cb, text, markup)


@router.callback_query(F.data.startswith("adm:e:"))
async def ask_emoji(cb: CallbackQuery, state: FSMContext) -> None:
    key = cb.data[6:]
    if key not in EMOJI_DEFAULTS:
        await cb.answer()
        return
    await cb.answer()
    await state.set_state(AdminStates.emoji)
    await state.update_data(key=key)
    await show(cb, f"<b>{EMOJI_DESC[key]}</b> ({EMOJI_DEFAULTS[key]})\nHozirgi ID: <code>{emoji.ids.get(key, '—')}</code>\n\n"
                   "Premium emoji yuboring yoki ID yozing (<code>0</code> — o‘chirish):", kb([ib("back", "Emoji ro‘yxati", cb="adm:emoji")]))


@router.message(AdminStates.emoji, not_menu)
async def save_emoji(message: Message, state: FSMContext, db) -> None:
    key = (await state.get_data())["key"]
    cid = None
    for ent in message.entities or []:
        if ent.type == "custom_emoji" and ent.custom_emoji_id:
            cid = ent.custom_emoji_id
            break
    raw = (message.text or "").strip()
    if cid is None and raw.isdigit():
        cid = raw
    if cid is None:
        await message.answer("❌ Premium emoji yuboring yoki ID raqamini yozing.", reply_markup=back_kb())
        return
    if cid == "0":
        await emoji.clear(db, key)
        await log_admin(db, message.from_user.id, "emoji", key, "o‘chirildi")
    else:
        await emoji.set(db, key, cid)
        await log_admin(db, message.from_user.id, "emoji", key, cid)
    await state.clear()
    text, markup = emoji_view()
    await message.answer("✅ Saqlandi.\n\n" + text, reply_markup=markup)


# ----------------------------------------------------------------------- loglar
@router.callback_query(F.data == "adm:logs")
async def logs(cb: CallbackQuery, db) -> None:
    await cb.answer()
    rows = await db.fetch("SELECT * FROM admin_logs ORDER BY id DESC LIMIT 20")
    body = "\n".join(
        f"{r['created_at']:%d.%m %H:%M} · <code>{r['admin_id']}</code> · {escape(r['action'])} "
        f"{escape(r['target'])} {escape(r['details'])}" for r in rows) or "Loglar yo‘q."
    await show(cb, f"📜 <b>So‘nggi amallar</b>\n\n{body}", back_kb())
