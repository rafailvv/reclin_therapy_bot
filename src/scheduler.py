# src/bot/scheduler.py
import logging

from aiogram.types import InlineKeyboardMarkup, WebAppInfo, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from sqlalchemy import select, update
from src.db import async_session
from src.models import User
from src.config import settings

scheduler = AsyncIOScheduler()


from aiogram.exceptions import TelegramBadRequest

async def cleanup_unregistered(telegram_id: int):
    """
    Runs 5 days after /start:
     - if fio or specialization still null → kick (ban + unban) & DM with a WebApp button
     - only if the user is still in chat
    """
    async with async_session() as sess:
        user = await sess.scalar(select(User).where(User.telegram_id == telegram_id))
        if not user:
            return

        if not user.fio or not user.specialization:
            bot = Bot(token=settings.bot_token)

            try:
                # Проверяем, состоит ли пользователь в чате
                member = await bot.get_chat_member(chat_id=settings.chat_id, user_id=telegram_id)
                if member.status in ("left", "kicked"):
                    return  # Уже не в чате — ничего не делаем

                # Кикаем: ban → unban
                await bot.ban_chat_member(chat_id=settings.chat_id, user_id=telegram_id)

                # Кнопка WebApp для повторного входа
                kb = InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(
                            text="Заполнить данные",
                            web_app=WebAppInfo(
                                url=f"{settings.webapp_url}/?uid={telegram_id}"
                            )
                        )
                    ]]
                )

                await bot.send_message(
                    chat_id=telegram_id,
                    text=(
                        "Вы были исключены из сообщества Терапия|Reclin. Чтобы подключиться повторно к сообществу, "
                        "заполните данные о вашем ФИО и специализации, нажав на кнопку ниже 👇"
                    ),
                    reply_markup=kb
                )

            except TelegramBadRequest as e:
                # Например, если пользователь запретил личку — игнорируем
                logging.warning(f"Failed to send message or kick user {telegram_id}: {e}")

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