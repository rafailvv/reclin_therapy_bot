# src/bot/scheduler.py
import logging
from datetime import timedelta, datetime

from aiogram.types import InlineKeyboardMarkup, WebAppInfo, InlineKeyboardButton
from apscheduler.jobstores.base import JobLookupError
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select, update
from src.db import async_session
from src.models import User
from src.config import settings
from aiogram.exceptions import TelegramBadRequest


scheduler = AsyncIOScheduler(jobstores={
    'default': SQLAlchemyJobStore(url='sqlite:///jobs.sqlite')
})

async def reschedule_reminders_on_start():
    async with async_session() as sess:
        result = await sess.execute(
            select(User).where(User.specialization == None)
        )
        users = result.scalars().all()

        for user in users:
            try:
                run_date = user.registered_at + timedelta(days=5)
                scheduler.add_job(
                    func=cleanup_unregistered,
                    trigger=IntervalTrigger(days=5, start_date=run_date),
                    args=[user.telegram_id],
                    id=f"remind_spec_{user.telegram_id}",
                    replace_existing=True,
                )
            except Exception as e:
                logging.warning(f"Не удалось пересоздать задачу для {user.telegram_id}: {e}")


async def cleanup_unregistered(telegram_id: int):
    """
    Runs every 5 days starting 5 days after /start:
     - if specialization still null → DM reminder
     - otherwise → remove this job (no more reminders)
    """
    async with async_session() as sess:
        user = await sess.scalar(
            select(User).where(User.telegram_id == telegram_id)
        )
        if not user:
            return

        if user.specialization:
            try:
                scheduler.remove_job(f"remind_spec_{telegram_id}")
            except JobLookupError:
                pass
            return

        # Otherwise, send the *reminder* message
        bot = Bot(token=settings.bot_token)
        try:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text="Заполнить специальность",
                        web_app=WebAppInfo(
                            url=f"{settings.webapp_url}/?uid={telegram_id}"
                        )
                    )
                ]]
            )
            await bot.send_message(
                chat_id=telegram_id,
                text=(
                    "Коллега, просим тебя внести специальность — "
                    "это нужно, чтобы мы с командой подбирали материалы, "
                    "которые действительно будут полезны именно тебе."
                ),
                reply_markup=kb
            )
        except TelegramBadRequest as e:
            logging.warning(f"Failed to send reminder to {telegram_id}: {e}")
        finally:
            await bot.session.close()


def setup_scheduler(bot: Bot):
    """
    Call this once at startup.  It both schedules your jobs
    *and* actually kicks the scheduler off.
    """
    # you can schedule other recurring or date‑based jobs here, e.g.:
    # scheduler.add_job(my_recurring, 'interval', hours=1, args=[…])

    # *** schedule your per-user cleanup jobs when /start runs ***
    # In your /start handler you did:
    #   scheduler.add_job(…, trigger='date', run_date=…, args=[user_id], id=…)
    #
    # so here we only need to start the scheduler itself:

    if not scheduler.running:
        scheduler.start()