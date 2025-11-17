# src/bot/scheduler.py
import logging
from datetime import timedelta, datetime

from aiogram.types import InlineKeyboardMarkup, WebAppInfo, InlineKeyboardButton
from apscheduler.jobstores.base import JobLookupError
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, update
from src.db import async_session
from src.models import User
from src.config import settings
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile


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


async def backup_reminder():
    """
    Автоматически создает и отправляет бэкап каждый день в 01:00
    """
    bot = Bot(token=settings.bot_token)
    try:
        # Проверяем наличие pg_dump
        import subprocess
        pg_dump_check = subprocess.run(['which', 'pg_dump'], capture_output=True, text=True)
        if pg_dump_check.returncode != 0:
            await bot.send_message(
                chat_id=429272623,
                text="❌ pg_dump не найден. Убедитесь, что PostgreSQL клиент установлен."
            )
            logging.error("pg_dump not found")
            return
        
        # Проверяем версию pg_dump
        version_check = subprocess.run(['pg_dump', '--version'], capture_output=True, text=True)
        if version_check.returncode == 0:
            logging.info(f"pg_dump version: {version_check.stdout.strip()}")
        else:
            logging.warning("Could not get pg_dump version")
        
        # Создаем бэкап
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"backup_{timestamp}.sql"
        
        # Команда для создания бэкапа PostgreSQL
        db_url = str(settings.database_url)
        logging.info(f"Database URL: {db_url}")
        
        # Парсим URL для получения параметров
        if db_url.startswith('postgresql://') or db_url.startswith('postgresql+asyncpg://'):
            # Убираем префикс postgresql:// или postgresql+asyncpg://
            url_without_prefix = db_url.replace('postgresql+asyncpg://', '').replace('postgresql://', '')
            
            # Разделяем на auth и host части
            if '@' in url_without_prefix:
                auth_part, host_part = url_without_prefix.split('@', 1)
            else:
                # Если нет @, значит нет пароля
                auth_part = url_without_prefix
                host_part = url_without_prefix
            
            # Парсим auth часть
            if ':' in auth_part:
                username, password = auth_part.split(':', 1)
            else:
                username = auth_part
                password = ""
            
            # Парсим host часть
            if '/' in host_part:
                host_port, database = host_part.rsplit('/', 1)
            else:
                host_port = host_part
                database = "postgres"
            
            # Парсим host и port
            if ':' in host_port:
                host, port = host_port.split(':', 1)
            else:
                host = host_port
                port = "5432"
            
            logging.info(f"Parsed DB params: host={host}, port={port}, user={username}, db={database}")
            
            # Создаем бэкап
            backup_cmd = [
                'pg_dump',
                f'--host={host}',
                f'--port={port}',
                f'--username={username}',
                f'--dbname={database}',
                '--no-password',
                '--format=custom',
                '--file=' + backup_filename
            ]
            
            # Устанавливаем переменную окружения для пароля
            import os
            env = os.environ.copy()
            if password:
                env['PGPASSWORD'] = password
            
            logging.info(f"Running backup command: {' '.join(backup_cmd)}")
            
            result = subprocess.run(
                backup_cmd,
                env=env,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                # Отправляем файл бэкапа админу
                await bot.send_document(
                    chat_id=429272623,  # ID админа
                    document=FSInputFile(backup_filename),
                    filename=backup_filename,
                    caption=f"🔄 Автоматический бэкап базы данных: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
                )
                logging.info("Automatic database backup created and sent successfully")
            else:
                await bot.send_message(
                    chat_id=429272623,
                    text=f"❌ Ошибка создания автоматического бэкапа:\n{result.stderr}\n\nКоманда: {' '.join(backup_cmd)}"
                )
                logging.error("Automatic backup failed: %s", result.stderr)
        else:
            await bot.send_message(
                chat_id=429272623,
                text=f"❌ Неподдерживаемый тип базы данных: {db_url[:20]}..."
            )
            
    except Exception as e:
        await bot.send_message(
            chat_id=429272623,
            text=f"❌ Ошибка при создании автоматического бэкапа: {str(e)}"
        )
        logging.error("Automatic backup error: %s", str(e))
    finally:
        await bot.session.close()


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
                        text="Заполнить анкету",
                        web_app=WebAppInfo(
                            url=f"{settings.webapp_url}/?uid={telegram_id}"
                        )
                    )
                ]]
            )
            await bot.send_message(
                chat_id=telegram_id,
                text=(
                    "Коллега, напоминаем тебе о заполнении анкеты для участия в чате!"
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
    # Добавляем ежедневное автоматическое создание бэкапа в 01:00
    scheduler.add_job(
        func=backup_reminder,
        trigger=CronTrigger(hour=1, minute=0),  # Каждый день в 01:00
        id="daily_backup_reminder",
        replace_existing=True,
    )

    # *** schedule your per-user cleanup jobs when /start runs ***
    # In your /start handler you did:
    #   scheduler.add_job(…, trigger='date', run_date=…, args=[user_id], id=…)
    #
    # so here we only need to start the scheduler itself:

    if not scheduler.running:
        scheduler.start()