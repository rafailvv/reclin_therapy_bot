import asyncio
import json
import logging
import subprocess
import tempfile
import os
from datetime import datetime

from aiogram import Router, F, types
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import StateFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from ..config import settings
from ..services.broadcast import broadcast
from ..db import async_session
from ..models import User, BotMessage
import pandas as pd
import tempfile

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

router = Router()

def is_admin(msg: types.Message) -> bool:
    is_admin_user = msg.from_user.id in settings.admin_ids
    if not is_admin_user:
        logger.warning("Unauthorized user %s attempted admin command", msg.from_user.id)
    return is_admin_user


class BroadcastStates(StatesGroup):
    waiting_for_message = State()


class EditMessageStates(StatesGroup):
    waiting_for_welcome_message = State()
    waiting_for_gift_message = State()


@router.message(Command("backup"))
async def cmd_backup(msg: Message):
    """Создает бэкап базы данных"""
    if not is_admin(msg):
        return

    logger.info("Admin %s requested database backup", msg.from_user.id)
    
    try:
        # Проверяем наличие pg_dump
        pg_dump_check = subprocess.run(['which', 'pg_dump'], capture_output=True, text=True)
        if pg_dump_check.returncode != 0:
            await msg.answer("❌ pg_dump не найден. Убедитесь, что PostgreSQL клиент установлен.")
            logger.error("pg_dump not found")
            return
        
        # Проверяем версию pg_dump
        version_check = subprocess.run(['pg_dump', '--version'], capture_output=True, text=True)
        if version_check.returncode == 0:
            logger.info(f"pg_dump version: {version_check.stdout.strip()}")
        else:
            logger.warning("Could not get pg_dump version")
        
        # Создаем временный файл для бэкапа
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"backup_{timestamp}.sql"
        
        # Команда для создания бэкапа PostgreSQL
        # Извлекаем параметры подключения из DATABASE_URL
        db_url = str(settings.database_url)
        logger.info(f"Database URL: {db_url}")
        
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
            
            logger.info(f"Parsed DB params: host={host}, port={port}, user={username}, db={database}")
            
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
            env = os.environ.copy()
            if password:
                env['PGPASSWORD'] = password
            
            logger.info(f"Running backup command: {' '.join(backup_cmd)}")
            
            result = subprocess.run(
                backup_cmd,
                env=env,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                # Отправляем файл бэкапа
                await msg.answer_document(
                    FSInputFile(backup_filename),
                    filename=backup_filename,
                    caption=f"✅ Бэкап базы данных создан: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
                )
                logger.info("Database backup created successfully by admin %s", msg.from_user.id)
            else:
                error_msg = f"❌ Ошибка создания бэкапа:\n{result.stderr}\n\nКоманда: {' '.join(backup_cmd)}"
                await msg.answer(error_msg)
                logger.error("Backup failed: %s", result.stderr)
        else:
            await msg.answer(f"❌ Неподдерживаемый тип базы данных: {db_url[:20]}...")
            
    except Exception as e:
        await msg.answer(f"❌ Ошибка при создании бэкапа: {str(e)}")
        logger.error("Backup error: %s", str(e))


@router.message(Command("broadcast"))
async def start_broadcast(msg: types.Message, state: FSMContext):
    if msg.from_user.id not in settings.admin_ids:
        logger.warning("User %s attempted to start broadcast without permissions", msg.from_user.id)
        return

    logger.info("Admin %s started a broadcast session", msg.from_user.id)
    await state.clear()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")]]
    )
    await msg.answer("Пришлите сообщение (с медиа или без) для рассылки.", reply_markup=kb)
    await state.set_state(BroadcastStates.waiting_for_message)


@router.callback_query(F.data == "broadcast_cancel")
async def cancel_broadcast(cb: types.CallbackQuery, state: FSMContext):
    logger.info("Broadcast cancelled by admin %s", cb.from_user.id)
    await state.clear()
    await cb.message.edit_text("Рассылка отменена.")
    await cb.answer()


@router.message(BroadcastStates.waiting_for_message)
async def collect_broadcast_content(msg: types.Message, state: FSMContext):
    logger.debug("Collecting broadcast content from admin %s", msg.from_user.id)
    await msg.bot.send_chat_action(msg.chat.id, "typing")

    if msg.media_group_id:
        logger.debug("Message is part of media group %s", msg.media_group_id)
        data = await state.get_data()
        media_group = data.get("media_group", [])
        media_group.append(msg)
        await state.update_data(media_group=media_group)
        if len(media_group) == 1:
            asyncio.create_task(process_media_group_later(msg.media_group_id, state, msg))
        return

    file_list = []
    caption = msg.caption or msg.text or ""
    if msg.caption_entities:
        caption_entities = [ent.model_dump() for ent in msg.caption_entities]
    elif msg.entities:
        caption_entities = [ent.model_dump() for ent in msg.entities]
    else:
        caption_entities = None

    if msg.photo:
        file_list.append({"type": "photo", "file_id": msg.photo[-1].file_id})
    elif msg.document:
        file_list.append({"type": "document", "file_id": msg.document.file_id})
    elif msg.video:
        file_list.append({"type": "video", "file_id": msg.video.file_id})

    logger.info(
        "Preparing to broadcast message from admin %s with %d attachments",
        msg.from_user.id,
        len(file_list),
    )

    # Получаем список пользователей
    async with async_session() as sess:
        result = await sess.execute(select(User.telegram_id))
        tg_ids = result.scalars().all()
    logger.debug("Fetched %d user ids for broadcast", len(tg_ids))

    sent, failed = await broadcast(
        bot=msg.bot,
        tg_ids=tg_ids,
        caption=caption,
        caption_entities=json.dumps(caption_entities) if caption_entities else None,
        file_ids=json.dumps(file_list) if file_list else None,
    )

    logger.info("Broadcast completed by admin %s: sent=%s, failed=%s", msg.from_user.id, sent, failed)
    await msg.answer(f"Рассылка завершена.\n✅ Отправлено: {sent}\n❌ Ошибок: {failed}")
    await state.clear()


async def process_media_group_later(group_id: str, state: FSMContext, msg: types.Message):
    """
    Асинхронная обработка всей media-группы.
    """
    logger.debug("Starting delayed processing for media group %s", group_id)
    await asyncio.sleep(1)  # Ждём, пока все части дойдут
    data = await state.get_data()
    messages = data.get("media_group", [])
    messages = sorted(messages, key=lambda m: m.message_id)
    logger.debug("Collected %d messages in media group %s", len(messages), group_id)

    file_list = []
    caption = messages[0].caption or ""
    if messages[0].caption_entities:
        caption_entities = [e.model_dump() for e in messages[0].caption_entities]
    else:
        caption_entities = None

    for m in messages:
        if m.photo:
            file_list.append({"type": "photo", "file_id": m.photo[-1].file_id})
        elif m.document:
            file_list.append({"type": "document", "file_id": m.document.file_id})
        elif m.video:
            file_list.append({"type": "video", "file_id": m.video.file_id})

    # Получаем список пользователей
    async with async_session() as sess:
        result = await sess.execute(select(User.telegram_id))
        tg_ids = result.scalars().all()
    logger.debug("Fetched %d user ids for media group broadcast", len(tg_ids))

    sent, failed = await broadcast(
        bot=msg.bot,
        tg_ids=tg_ids,
        caption=caption,
        caption_entities=json.dumps(caption_entities) if caption_entities else None,
        file_ids=json.dumps(file_list),
    )

    logger.info("Media group broadcast completed: sent=%s, failed=%s", sent, failed)
    await msg.answer(f"Рассылка завершена.\n✅ Отправлено: {sent}\n❌ Ошибок: {failed}")
    await state.clear()


@router.message(Command("edit_welcome"))
async def start_edit_welcome(msg: Message, state: FSMContext):
    """Начинает процесс редактирования приветственного сообщения"""
    if not is_admin(msg):
        return

    logger.info("Admin %s started editing welcome message", msg.from_user.id)
    await state.clear()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="edit_cancel")]]
    )
    await msg.answer("Пришлите новое приветственное сообщение:", reply_markup=kb)
    await state.set_state(EditMessageStates.waiting_for_welcome_message)


@router.message(Command("edit_gift"))
async def start_edit_gift(msg: Message, state: FSMContext):
    """Начинает процесс редактирования сообщения с подарком"""
    if not is_admin(msg):
        return

    logger.info("Admin %s started editing gift message", msg.from_user.id)
    await state.clear()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="edit_cancel")]]
    )
    await msg.answer("Пришлите новое сообщение с подарком:", reply_markup=kb)
    await state.set_state(EditMessageStates.waiting_for_gift_message)


@router.callback_query(F.data == "edit_cancel")
async def cancel_edit(cb: CallbackQuery, state: FSMContext):
    logger.info("Message editing cancelled by admin %s", cb.from_user.id)
    await state.clear()
    await cb.message.edit_text("Редактирование отменено.")
    await cb.answer()


@router.message(EditMessageStates.waiting_for_welcome_message)
async def save_welcome_message(msg: Message, state: FSMContext):
    """Сохраняет message_id приветственного сообщения"""
    if not is_admin(msg):
        return

    async with async_session() as sess:
        # Ищем существующее сообщение
        existing_msg = await sess.scalar(
            select(BotMessage).where(BotMessage.message_type == "welcome")
        )
        
        if existing_msg:
            # Обновляем существующее
            existing_msg.message_id = msg.message_id
            existing_msg.from_chat_id = msg.chat.id
            existing_msg.updated_at = datetime.utcnow()
        else:
            # Создаем новое
            new_msg = BotMessage(
                message_type="welcome",
                message_id=msg.message_id,
                from_chat_id=msg.chat.id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            sess.add(new_msg)
        
        await sess.commit()

    await state.clear()
    await msg.answer("✅ Приветственное сообщение успешно сохранено!")
    logger.info("Welcome message saved by admin %s (message_id: %s, chat_id: %s)", msg.from_user.id, msg.message_id, msg.chat.id)


@router.message(EditMessageStates.waiting_for_gift_message)
async def save_gift_message(msg: Message, state: FSMContext):
    """Сохраняет message_id сообщения с подарком"""
    if not is_admin(msg):
        return

    async with async_session() as sess:
        # Ищем существующее сообщение
        existing_msg = await sess.scalar(
            select(BotMessage).where(BotMessage.message_type == "gift")
        )
        
        if existing_msg:
            # Обновляем существующее
            existing_msg.message_id = msg.message_id
            existing_msg.from_chat_id = msg.chat.id
            existing_msg.updated_at = datetime.utcnow()
        else:
            # Создаем новое
            new_msg = BotMessage(
                message_type="gift",
                message_id=msg.message_id,
                from_chat_id=msg.chat.id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            sess.add(new_msg)
        
        await sess.commit()

    await state.clear()
    await msg.answer("✅ Сообщение с подарком успешно сохранено!")
    logger.info("Gift message saved by admin %s (message_id: %s, chat_id: %s)", msg.from_user.id, msg.message_id, msg.chat.id)


@router.message(F.text == "/export")
async def cmd_export(msg: Message):
    if not is_admin(msg):
        return

    logger.info("Admin %s requested user export", msg.from_user.id)
    async with async_session() as sess:
        result = await sess.execute(select(User))
        users = result.scalars().all()

    logger.debug("Exporting %d users to Excel", len(users))
    # Преобразуем список ORM-объектов в список словарей
    data = [
        {
            "ID Telegram": u.telegram_id,
            "Имя пользователя": u.username,
            "ФИО": u.fio,
            "Специализация": u.specialization,
            "Email": u.email,
            "Дата регистрации (UTC)": u.registered_at,
        }
        for u in users
    ]

    df = pd.DataFrame(data)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"users_{timestamp}.xlsx"
    with tempfile.NamedTemporaryFile("wb", suffix=".xlsx", delete=False) as fp:
        df.to_excel(fp.name, index=False)
        await msg.answer_document(
            FSInputFile(fp.name),
            filename=filename,
            caption=f"Отчёт сформирован: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        )
    logger.info("User export sent to admin %s", msg.from_user.id)


@router.message(Command("info"))
async def cmd_info(msg: Message):
    """
    Выдаёт краткий список доступных команд и их назначение.
    """
    if not is_admin(msg):
        return

    logger.debug("Admin %s requested info command list", msg.from_user.id)
    text = (
        "<b>Доступные команды:</b>\n"
        "/broadcast — запустить рассылку. После команды пришлите текст или медиа.\n"
        "/export — экспорт списка пользователей в Excel.\n"
        "/edit_welcome — установить приветственное сообщение.\n"
        "/edit_gift — установить сообщение с подарком.\n"
    )
    await msg.answer(text, parse_mode="HTML")
    logger.info("Sent command list to admin %s", msg.from_user.id)
