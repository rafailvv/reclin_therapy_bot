import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from sqlalchemy import update, select
from sqlalchemy.exc import IntegrityError
from ..config import settings
from ..services.invite import create_one_time_invite
from ..db import async_session
from ..models import User, BotMessage
from ..scheduler import scheduler  # see next section

router = Router()

# Стандартные сообщения (используются если нет сохраненных в БД)
# DEFAULT_WELCOME_TEXT теперь берется из настроек .env файла

# DEFAULT_GIFT_TEXT теперь берется из настроек .env файла


async def copy_message_by_id(bot, chat_id: int, message_id: int, from_chat_id: int, reply_markup=None) -> bool:
    """Копирует сообщение по его ID из указанного чата"""
    try:
        await bot.copy_message(
            chat_id=chat_id,
            from_chat_id=from_chat_id,  # Копируем из сохраненного чата
            message_id=message_id,
            reply_markup=reply_markup
        )
        return True
    except Exception as e:
        logging.error(f"Failed to copy message {message_id} from chat {from_chat_id}: {e}")
        return False


async def send_welcome_message(bot, chat_id: int, reply_markup=None) -> bool:
    """Отправляет приветственное сообщение"""
    async with async_session() as sess:
        welcome_msg = await sess.scalar(
            select(BotMessage).where(BotMessage.message_type == "welcome")
        )
        
        if welcome_msg:
            # Пытаемся скопировать сохраненное сообщение
            success = await copy_message_by_id(bot, chat_id, welcome_msg.message_id, welcome_msg.from_chat_id, reply_markup=reply_markup)
            if success:
                return True
        
        # Если копирование не удалось, отправляем стандартное сообщение из настроек
        await bot.send_message(chat_id, settings.default_welcome_message, reply_markup=reply_markup, parse_mode="HTML")
        return True


async def send_gift_message(bot, chat_id: int, reply_markup=None) -> bool:
    """Отправляет сообщение с подарком"""
    async with async_session() as sess:
        gift_msg = await sess.scalar(
            select(BotMessage).where(BotMessage.message_type == "gift")
        )
        
        if gift_msg:
            # Пытаемся скопировать сохраненное сообщение
            success = await copy_message_by_id(bot, chat_id, gift_msg.message_id, gift_msg.from_chat_id, reply_markup=reply_markup)
            if success:
                return True
        
        # Если копирование не удалось или нет сохраненного сообщения - отправляем стандартное из настроек
        await bot.send_message(chat_id, settings.default_gift_message, reply_markup=reply_markup, parse_mode="HTML")
        return True


@router.message(F.text == "/start")
async def cmd_start(msg: Message):
    # Отправляем приветственное сообщение
    await send_welcome_message(msg.bot, msg.chat.id)

    # 1) Создаём новую одноразовую ссылку
    invite_link = await create_one_time_invite(msg.bot)

    # 2) Проверяем, есть ли в БД пользователь
    async with async_session() as sess:
        user_in_db = await sess.scalar(
            select(User).where(User.telegram_id == msg.from_user.id)
        )

        if user_in_db:
            # — уже был зарегистрирован: обновляем invite + registered_at
            await sess.execute(
                update(User)
                .where(User.telegram_id == msg.from_user.id)
                .values(invite_link=invite_link, registered_at=datetime.utcnow())
            )
            await sess.commit()

            # Для уже зареганного пользователя отправляем только кнопку WebApp
            button = InlineKeyboardButton(
                text="Подключиться к чату",
                web_app=WebAppInfo(url=f"{settings.webapp_url}/?uid={msg.from_user.id}")
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[[button]])
            
            # Отправляем сообщение с подарком
            await send_gift_message(msg.bot, msg.chat.id, reply_markup=kb)

        else:
            # — впервые: создаём «заглушку»
            new_user = User(
                telegram_id=msg.from_user.id,
                username=msg.from_user.username,
                invite_link=invite_link,
                # fio/email — оставляем None
            )
            sess.add(new_user)
            await sess.commit()

            # 3) Формируем клавиатуру — для новых пользователей это прямая ссылка
            button = InlineKeyboardButton(
                text="Подключиться к чату",
                url=invite_link
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[[button]])

            # 5) Отправляем сообщение с подарком
            await send_gift_message(msg.bot, msg.chat.id, reply_markup=kb)
