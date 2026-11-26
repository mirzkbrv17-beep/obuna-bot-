"""Bot, Dispatcher, fon ishchilar va (Render uchun) health server."""
from __future__ import annotations

import asyncio
import logging

import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

import admin
from config import Config
from database import Database
from handlers import account, earn, events, menu, order
from handlers.middleware import UserMiddleware
from services.checker import SubscriptionChecker
from services.emoji import emoji
from services.fallback import EmojiFallbackMiddleware
from services.settings import settings
from services.tasks import PostWorker

log = logging.getLogger(__name__)


def build_dispatcher(db: Database, cfg: Config, worker: PostWorker) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.workflow_data.update(db=db, cfg=cfg, worker=worker)
    mw = UserMiddleware(db, cfg)
    dp.message.outer_middleware(mw)
    dp.callback_query.outer_middleware(mw)
    # tartib muhim: menyu tugmalari FSM holatlaridan oldin ishlashi kerak
    routers = (menu.router, admin.router, order.router, earn.router, account.router, events.router)
    for r in routers:
        r._parent_router = None   # routerlar modul darajasida: testlarda dispatcher qayta qurilishi uchun
    dp.include_routers(*routers)
    return dp


async def _health_server(port: int) -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="ABU SUB BOT ok"))
    app.router.add_get("/health", lambda r: web.Response(text="ok"))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    log.info("Health server: port %s", port)
    return runner


async def _keepalive(url: str) -> None:
    """Render bepul web servisi uxlab qolmasligi uchun o'zini 10 daqiqada bir pinglaydi."""
    async with aiohttp.ClientSession() as s:
        while True:
            await asyncio.sleep(600)
            try:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=20)):
                    pass
            except Exception as e:  # noqa: BLE001
                log.warning("keepalive xatosi: %s", e)


async def run(cfg: Config) -> None:
    db = Database(cfg.database_url)
    await db.connect()
    await db.migrate()
    settings.bind(db, cfg)
    await settings.load()
    await emoji.load(db)

    bot = Bot(cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML,
                                                           link_preview_is_disabled=True))
    bot.session.middleware(EmojiFallbackMiddleware())
    worker = PostWorker(bot, db)
    checker = SubscriptionChecker(bot, db, worker)
    dp = build_dispatcher(db, cfg, worker)

    runner = await _health_server(cfg.port)
    tasks = [asyncio.create_task(worker.run(), name="posts"),
             asyncio.create_task(checker.run(), name="checker")]
    if cfg.keepalive_url:
        tasks.append(asyncio.create_task(_keepalive(cfg.keepalive_url), name="keepalive"))
    try:
        me = await bot.get_me()
        log.info("Bot ishga tushdi: @%s", me.username)
        await bot.delete_webhook(drop_pending_updates=False)
        worker.wake()
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await runner.cleanup()
        await bot.session.close()
        await db.close()
