import asyncio
import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from database import connect_db, close_db
from services.i18n import load_translations
from handlers.user import router as user_router
from handlers.buy import router as buy_router
from handlers.sell import router as sell_router
from handlers.admin import router as admin_router

logging.basicConfig(
level=logging.INFO,
format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("usdt_p2p_bot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
PORT = int(os.getenv("PORT", "10000"))

async def health_check(request):
return web.json_response(
{
"status": "ok",
"service": "USDT P2P AZ",
}
)

async def start_health_server():
app = web.Application()
app.router.add_get("/", health_check)
app.router.add_get("/health", health_check)

runner = web.AppRunner(app)
await runner.setup()

site = web.TCPSite(
    runner,
    host="0.0.0.0",
    port=PORT,
)
await site.start()

logger.info("Health server started on port %s", PORT)
return runner

async def main():
if not BOT_TOKEN:
raise RuntimeError(
"BOT_TOKEN Render Environment Variables bölməsində təyin edilməyib."
)

# Tərcümə fayllarını yoxla və yüklə.
load_translations()

# PostgreSQL bağlantısını qur.
await connect_db()

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(
        parse_mode=ParseMode.HTML,
    ),
)

dp = Dispatcher(storage=MemoryStorage())

# Bütün bot bölmələrini birləşdir.
dp.include_router(admin_router)
dp.include_router(buy_router)
dp.include_router(sell_router)
dp.include_router(user_router)

health_runner = None

try:
    health_runner = await start_health_server()

    # Render-də webhook əvəzinə polling istifadə olunur.
    await bot.delete_webhook(drop_pending_updates=False)

    logger.info("USDT P2P AZ bot işə düşür.")
    await dp.start_polling(bot)

finally:
    if health_runner is not None:
        await health_runner.cleanup()

    await bot.session.close()
    await close_db()

    logger.info("Bot dayandırıldı.")

if name == "main":
try:
asyncio.run(main())
except KeyboardInterrupt:
logger.info("Bot dayandırıldı.")
except Exception:
logger.exception("Bot başladılarkən xəta baş verdi.")
raise
