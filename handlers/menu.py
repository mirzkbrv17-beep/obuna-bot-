"""/start va asosiy menyu tugmalari."""
from __future__ import annotations

from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import Config
from handlers import account, earn
from handlers.order import begin_order
from services.emoji import E
from services.keyboards import is_menu, main_menu
from services.users import register_referral

router = Router(name="menu")
router.message.filter(F.chat.type == "private")


def welcome(name: str) -> str:
    return (f"{E('crown')} <b>ABU SUB BOT</b>ga xush kelibsiz, {escape(name)}!\n\n"
            f"{E('order')} Kanal/guruhingizga <b>haqiqiy obunachi</b> buyurtma qiling\n"
            f"{E('earn')} Boshqalarning kanallariga obuna bo‘lib <b>coin</b> ishlang\n"
            f"{E('referral')} Do‘stlarni taklif qilib qo‘shimcha coin oling\n\n"
            f"Kerakli bo‘limni tanlang 👇")


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext, db, user: dict,
                    is_new: bool) -> None:
    await state.clear()
    args = command.args or ""
    if is_new and args.startswith("ref_") and args[4:].isdigit():
        await register_referral(db, user["id"], int(args[4:]))
    await message.answer(welcome(message.from_user.full_name), reply_markup=main_menu())


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Asosiy menyu 👇", reply_markup=main_menu())


@router.callback_query(F.data == "menu")
async def cb_menu(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb.answer()
    await cb.message.answer("Asosiy menyu 👇", reply_markup=main_menu())


@router.message(is_menu("order"))
async def m_order(message: Message, state: FSMContext, user: dict, cfg: Config) -> None:
    await begin_order(message, state, user, cfg)


@router.message(is_menu("earn"))
async def m_earn(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    await earn.show_earn(message, bot)


@router.message(is_menu("balance"))
async def m_balance(message: Message, state: FSMContext, user: dict, db, cfg: Config) -> None:
    await state.clear()
    await account.show_balance(message, user, db, cfg)


@router.message(is_menu("orders"))
async def m_orders(message: Message, state: FSMContext, user: dict, db) -> None:
    await state.clear()
    await account.show_orders(message, user, db)


@router.message(is_menu("referral"))
async def m_referral(message: Message, state: FSMContext, user: dict, db, bot: Bot) -> None:
    await state.clear()
    await account.show_referral(message, user, db, bot)


@router.message(is_menu("profile"))
async def m_profile(message: Message, state: FSMContext, user: dict, db, cfg: Config) -> None:
    await state.clear()
    await account.show_profile(message, user, db, cfg)
