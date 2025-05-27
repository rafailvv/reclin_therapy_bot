import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums.parse_mode import ParseMode
from .config import settings
from .handlers import start, admin, webapp_entry
from .db import engine, Base

async def on_startup(bot: Bot):
    # создаём таблицы (без Alembic, для MVP)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def main():
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp  = Dispatcher()

    dp.startup.register(on_startup)

    # регистрируем роутеры
    dp.include_router(start.router)
    # dp.include_router(webapp_entry.router)
    dp.include_router(admin.router)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
