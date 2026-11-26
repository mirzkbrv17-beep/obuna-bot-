"""Obunachi buyurtma berish (FSM)."""
from __future__ import annotations

import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from config import Config
from services import orders as orders_svc
from services.chats import INVITE, OrderError, Target, parse_chat_ref, resolve_target
from services.emoji import E
from services.keyboards import ib, kb, not_menu
from services.settings import settings
from services.users import is_unlimited

log = logging.getLogger(__name__)
router = Router(name="order")
router.message.filter(F.chat.type == "private")


class OrderFlow(StatesGroup):
    quantity = State()
    link = State()
    confirm = State()


def _cancel_kb():
    return kb([ib("cross", "Bekor qilish", cb="oc:no")])


def _earn_kb():
    return kb([ib("earn", "Coin ishlash", cb="go_earn", style="success")],
              [ib("home", "Asosiy menyu", cb="menu")])


async def begin_order(message: Message, state: FSMContext, user: dict, cfg: Config) -> None:
    await state.clear()
    price, mn, mx = settings.int("price_per_sub"), settings.int("min_order"), settings.int("max_order")
    unlimited = is_unlimited(cfg, user)
    if not unlimited and user["balance"] < mn * price:
        await message.answer(
            f"{E('warn')} <b>Coin yetarli emas.</b>\n\nEng kam buyurtma: {mn} ta × {price} = "
            f"<b>{mn * price}</b> {E('coin')}\nBalansingiz: <b>{user['balance']}</b> {E('coin')}\n\n"
            f"Avval «Coin ishlash» bo‘limida coin to‘plang.", reply_markup=_earn_kb())
        return
    await state.set_state(OrderFlow.quantity)
    bal = "♾ Cheksiz" if unlimited else str(user["balance"])
    limit = mx if unlimited else min(mx, user["balance"] // price)
    await message.answer(
        f"{E('order')} <b>Obunachi buyurtma</b>\n\n1 ta obunachi: <b>{'0 (VIP/Admin)' if unlimited else price}</b> {E('coin')}\n"
        f"Balansingiz: <b>{bal}</b> {E('coin')}\n\n"
        f"Nechta obunachi kerak? Son yuboring ({mn} — {limit}):", reply_markup=_cancel_kb())


@router.callback_query(F.data == "oc:no")
async def cancel(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb.answer("Bekor qilindi.")
    await cb.message.answer("❌ Buyurtma bekor qilindi.")


@router.message(OrderFlow.quantity, not_menu)
async def got_quantity(message: Message, state: FSMContext, user: dict, cfg: Config) -> None:
    raw = (message.text or "").replace(" ", "")
    if not raw.isdigit():
        await message.answer("❌ Iltimos, faqat son yuboring.", reply_markup=_cancel_kb())
        return
    qty = int(raw)
    price, mn, mx = settings.int("price_per_sub"), settings.int("min_order"), settings.int("max_order")
    if qty < mn or qty > mx:
        await message.answer(f"❌ Son {mn} dan {mx} gacha bo‘lishi kerak.", reply_markup=_cancel_kb())
        return
    unlimited = is_unlimited(cfg, user)
    cost = 0 if unlimited else qty * price
    if not unlimited and user["balance"] < cost:
        await state.clear()
        await message.answer(
            f"{E('warn')} <b>Coin yetarli emas.</b>\nKerak: <b>{cost}</b> {E('coin')}, "
            f"sizda: <b>{user['balance']}</b> {E('coin')}.\n\nCoin ishlash bo‘limiga o‘ting.",
            reply_markup=_earn_kb())
        return
    await state.update_data(qty=qty)
    await state.set_state(OrderFlow.link)
    await message.answer(
        f"{E('link')} Endi kanal yoki guruhingiz havolasini yuboring.\n\n"
        f"• <code>@username</code> yoki <code>https://t.me/username</code>\n"
        f"• yopiq bo‘lsa — chat ID (<code>-100...</code>) yoki kanalingizdan biror postni shu yerga <b>forward</b> qiling\n\n"
        f"{E('warn')} Bot shu kanal/guruhda <b>admin</b> bo‘lishi kerak (a’zolarni ko‘rish va taklif qilish huquqi bilan).",
        reply_markup=_cancel_kb())


@router.message(OrderFlow.link, not_menu)
async def got_link(message: Message, state: FSMContext, bot: Bot, user: dict, cfg: Config) -> None:
    ref = None
    origin = getattr(message, "forward_origin", None)
    if origin is not None and getattr(origin, "chat", None) is not None:
        ref = origin.chat.id
    elif message.text:
        ref = parse_chat_ref(message.text)
    if ref == INVITE:
        await message.answer(
            "❌ Yopiq taklif havolasi (t.me/+...) bo‘yicha kanalni aniqlab bo‘lmaydi.\n"
            "Kanaldan biror postni forward qiling yoki chat ID (<code>-100...</code>) yuboring.",
            reply_markup=_cancel_kb())
        return
    if ref is None:
        await message.answer("❌ Havola tushunarsiz. <code>@username</code>, t.me havolasi, ID yoki forward yuboring.",
                             reply_markup=_cancel_kb())
        return
    try:
        target = await resolve_target(bot, user["id"], ref, require_user_admin=user["id"] not in cfg.admin_ids)
    except OrderError as e:
        await message.answer(str(e), reply_markup=_cancel_kb())
        return
    data = await state.get_data()
    qty = data["qty"]
    unlimited = is_unlimited(cfg, user)
    price = settings.int("price_per_sub")
    cost = 0 if unlimited else qty * price
    await state.update_data(target=target.__dict__)
    await state.set_state(OrderFlow.confirm)
    await message.answer(
        f"{E('check')} <b>Buyurtmani tasdiqlang</b>\n\n{E('megaphone')} {escape(target.title)}\n"
        f"{E('id')} <code>{target.chat_id}</code>\n{E('box')} Obunachi: <b>{qty}</b> ta\n"
        f"{E('coin')} Narx: <b>{'bepul (VIP/Admin)' if unlimited else cost}</b>",
        reply_markup=kb([ib("check", "Tasdiqlash", cb="oc:yes", style="success"),
                         ib("cross", "Bekor qilish", cb="oc:no", style="danger")]))


@router.callback_query(OrderFlow.confirm, F.data == "oc:yes")
async def confirm(cb: CallbackQuery, state: FSMContext, bot: Bot, db, user: dict, cfg: Config, worker) -> None:
    data = await state.get_data()
    await state.clear()
    if "target" not in data:
        await cb.answer("Sessiya tugagan, qaytadan boshlang.", show_alert=True)
        return
    target = Target(**data["target"])
    try:
        res = await orders_svc.create_order(
            db, owner_id=user["id"], target=target, quantity=data["qty"],
            price=settings.int("price_per_sub"), unlimited=is_unlimited(cfg, user),
            referral_reward=settings.int("referral_reward"))
    except orders_svc.InsufficientCoins as e:
        await cb.answer()
        await cb.message.answer(
            f"{E('warn')} <b>Coin yetarli emas.</b> Kerak: {e.cost}, sizda: {e.balance}.",
            reply_markup=_earn_kb())
        return
    except orders_svc.ActiveOrderExists:
        await cb.answer()
        await cb.message.answer("❌ Bu kanal/guruh uchun faol buyurtma allaqachon mavjud. "
                                "Avval uni yakunlang yoki «Buyurtmalarim» dan bekor qiling.")
        return
    await cb.answer("Buyurtma qabul qilindi!")
    o = res.order
    note = "" if settings.get("tasks_channel_id") else "\n\n<i>Vazifalar kanali hali sozlanmagan — post kanal sozlangach chiqadi.</i>"
    await cb.message.answer(
        f"{E('check')} <b>Buyurtma #{o['id']} qabul qilindi!</b>\n\n{E('megaphone')} {escape(o['chat_title'])}\n"
        f"{E('box')} {o['quantity']} ta obunachi · yechildi: {o['cost']} {E('coin')}\n"
        f"Balans: {'♾' if o['is_free'] else res.balance} {E('coin')}\n\n"
        f"Buyurtmangiz vazifalar kanaliga joylanadi.{note}")
    worker.wake()
    if res.referrer_id:
        try:
            await bot.send_message(
                res.referrer_id,
                f"{E('gift')} Taklif qilgan do‘stingiz birinchi buyurtmasini berdi!\n"
                f"Sizga <b>+{res.referral_reward} {E('coin')}</b> berildi.")
        except TelegramAPIError:
            pass
