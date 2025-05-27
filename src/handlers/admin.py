import asyncio
import json
import logging
from datetime import datetime

from aiogram import Router, F, types
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import StateFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from sqlalchemy import select

from ..config import settings
from ..services.broadcast import broadcast
from ..db import async_session
from ..models import User
import pandas as pd
import tempfile

# Configure logging
logging.basicConfig(
    level=settings.log_level if hasattr(settings, 'log_level') else logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)

router = Router()

def is_admin(msg: types.Message) -> bool:
    return msg.from_user.id in settings.admin_ids

class BroadcastStates(StatesGroup):
    waiting_for_message = State()

@router.message(Command("broadcast"))
async def start_broadcast(msg: types.Message, state: FSMContext):
    if not is_admin(msg):
        logger.warning(f"Unauthorized broadcast attempt by {msg.from_user.id}")
        return
    await state.clear()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")]]
    )
    await msg.answer("Пришлите сообщение (с медиа или без) для рассылки.", reply_markup=kb)
    await state.set_state(BroadcastStates.waiting_for_message)
    logger.info(f"Broadcast initiated by {msg.from_user.id}")

@router.callback_query(F.data == "broadcast_cancel")
async def cancel_broadcast(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("Рассылка отменена.")
    await cb.answer()
    logger.info(f"Broadcast cancelled by {cb.from_user.id}")

@router.message(BroadcastStates.waiting_for_message)
async def collect_broadcast_content(msg: Message, state: FSMContext):
    await msg.bot.send_chat_action(msg.chat.id, "typing")
    logger.debug(f"Collecting broadcast content from {msg.from_user.id}, media_group_id={msg.media_group_id}")

    try:
        if msg.media_group_id:
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

        # Получаем список пользователей
        async with async_session() as sess:
            result = await sess.execute(select(User.telegram_id))
            tg_ids = result.scalars().all()
        logger.info(f"Broadcast to {len(tg_ids)} users started by {msg.from_user.id}")

        sent, failed = await broadcast(
            bot=msg.bot,
            tg_ids=tg_ids,
            caption=caption,
            caption_entities=json.dumps(caption_entities) if caption_entities else None,
            file_ids=json.dumps(file_list) if file_list else None,
        )

        await msg.answer(f"Рассылка завершена.\n✅ Отправлено: {sent}\n❌ Ошибок: {failed}")
        logger.info(f"Broadcast completed: sent={sent}, failed={failed}")
    except TelegramAPIError as e:
        logger.error(f"Telegram API error during broadcast: {e}")
        await msg.answer("Произошла ошибка при отправке рассылки.")
    except Exception as e:
        logger.exception("Unexpected error in broadcast handler")
        await msg.answer("Произошла непредвиденная ошибка.")
    finally:
        await state.clear()

async def process_media_group_later(group_id: str, state: FSMContext, msg: types.Message):
    """
    Асинхронная обработка всей media-группы.
    """
    await asyncio.sleep(1)  # Ждём, пока все части дойдут
    data = await state.get_data()
    messages = data.get("media_group", [])
    messages = sorted(messages, key=lambda m: m.message_id)
    file_list = []
    caption = messages[0].caption or ""
    caption_entities = [e.model_dump() for e in messages[0].caption_entities] if messages[0].caption_entities else None

    for m in messages:
        if m.photo:
            file_list.append({"type": "photo", "file_id": m.photo[-1].file_id})
        elif m.document:
            file_list.append({"type": "document", "file_id": m.document.file_id})
        elif m.video:
            file_list.append({"type": "video", "file_id": m.video.file_id})

    try:
        async with async_session() as sess:
            result = await sess.execute(select(User.telegram_id))
            tg_ids = result.scalars().all()
        logger.info(f"Broadcast media group {group_id} to {len(tg_ids)} users")

        sent, failed = await broadcast(
            bot=msg.bot,
            tg_ids=tg_ids,
            caption=caption,
            caption_entities=json.dumps(caption_entities) if caption_entities else None,
            file_ids=json.dumps(file_list),
        )

        await msg.answer(f"Рассылка завершена.\n✅ Отправлено: {sent}\n❌ Ошибок: {failed}")
        logger.info(f"Media group broadcast completed: sent={sent}, failed={failed}")
    except TelegramAPIError as e:
        logger.error(f"Telegram API error in media group: {e}")
    except Exception as e:
        logger.exception("Unexpected error in media group processing")
    finally:
        await state.clear()

@router.message(F.text == "/export")
async def cmd_export(msg: Message):
    if not is_admin(msg):
        logger.warning(f"Unauthorized export attempt by {msg.from_user.id}")
        return
    logger.info(f"User export requested by {msg.from_user.id}")

    try:
        async with async_session() as sess:
            result = await sess.execute(select(User))
            users = result.scalars().all()

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
                caption=f"Отчёт сформирован: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
            )
        logger.info(f"Export completed, file: {filename}")
    except Exception:
        logger.exception("Failed to export user data")
        await msg.answer("Не удалось сформировать отчет.")

@router.message(Command("info"))
async def cmd_info(msg: Message):
    """
    Выдаёт краткий список доступных команд и их назначение.
    """
    if not is_admin(msg):
        logger.warning(f"Unauthorized info request by {msg.from_user.id}")
        return

    text = (
        "<b>Доступные команды:</b>\n"
        "/broadcast — запустить рассылку. После команды пришлите текст или медиа.\n"
        "/export — экспорт списка пользователей в Excel.\n"
    )
    await msg.answer(text, parse_mode="HTML")
    logger.info(f"Info sent to {msg.from_user.id}")
