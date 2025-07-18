import asyncio
import datetime as dt

from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums.parse_mode import ParseMode

# switch to absolute imports so that `__main__` can resolve them
from src.config    import settings
from src.handlers  import start, admin
from src.db        import engine, Base
from src.import_users import import_users_from_excel
from src.scheduler import setup_scheduler

async def main():
    # await import_users_from_excel("tmp59q9jhov.xlsx")
    # 1) Create Bot & Dispatcher
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp  = Dispatcher()

    # 2) on_startup: create tables AND start your scheduler
    async def on_startup():
        # create tables (no Alembic, MVP)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # now hook up APScheduler → inside this call you must do scheduler.start()
        setup_scheduler(bot)

    dp.startup.register(on_startup)

    # 3) hook up your routers
    dp.include_router(start.router)
    dp.include_router(admin.router)

    # 4) start long‑polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
