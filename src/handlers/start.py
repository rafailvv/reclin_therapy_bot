import logging
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import update, select
from sqlalchemy.exc import IntegrityError
from ..config import settings
from ..services.invite import create_one_time_invite
from ..db import async_session
from ..models import User, BotMessage
from ..scheduler import scheduler, cleanup_unregistered  # see next section

router = Router()

# Стандартные сообщения (используются если нет сохраненных в БД)
DEFAULT_WELCOME_TEXT = (
    "🩺 <b>Как пользоваться чатом по терапии</b>\n"
    "Добро пожаловать!\n"
    "Вы находитесь в профессиональном чате для врачей и ординаторов терапевтических специальностей. "
    "Здесь можно задавать вопросы, делиться опытом и получать полезные материалы.\n\n"
    "Чат разделён на вкладки:\n"
    "● 📌 <b>ВАЖНОЕ, АНОНСЫ</b> — объявления о прямых эфирах, расписание, новости.\n"
    "● 🤝 <b>Прошу совета у коллег</b> — задавайте вопросы экспертам и другим участникам сообщества.\n"
    "● 📚 <b>Эфиры и материалы</b> — записи трансляций, памятки, гайды и другие полезные материалы.\n\n"
    "🔧 По техническим вопросам: @reclin2022"
)

DEFAULT_GIFT_TEXT = (
    "🎁 <b>Хотим сразу поделиться с тобой стартовым набором полезных материалов:</b>\n"
    "📌 Памятка «под стекло» по артериальной гипертензии — <a href='https://disk.yandex.ru/d/aCHhf7g7i_KHgw'>Скачать</a>\n"
    "📌 Памятки «под стекло» по диарее и запору — <a href='https://disk.yandex.ru/d/Qf_sd_zUepxUPw'>Скачать</a>\n"
    "📌 Шаблоны осмотров при НАЖБП и гастрите — <a href='https://disk.yandex.ru/d/0cGXx48hKweI8A'>Скачать</a>\n"
    "📌 Таблица с лекарственными препаратами по клинреку «Гастрит» — <a href='https://disk.yandex.ru/d/C4drU9y2DZEQuA'>Скачать</a>\n\n"
    "💬 Больше полезных материалов тебя ждёт в нашем чате — оставайся с нами!"
)


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
        
        # Если копирование не удалось, отправляем стандартное сообщение
        await bot.send_message(chat_id, DEFAULT_WELCOME_TEXT, reply_markup=reply_markup, parse_mode="HTML")
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
        
        # Если копирование не удалось или нет сохраненного сообщения - отправляем стандартное с кнопками
        await bot.send_message(chat_id, DEFAULT_GIFT_TEXT, reply_markup=reply_markup, parse_mode="HTML")
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
                # fio/specialization/email — оставляем None
            )
            sess.add(new_user)
            await sess.commit()

            # 3) Планируем проверку через 5 дней (для теста — 10 секунд)
            run_date = datetime.utcnow() + timedelta(days=5)
            scheduler.add_job(
                func=cleanup_unregistered,
                trigger=IntervalTrigger(days=5, start_date=run_date),
                args=[msg.from_user.id],
                id=f"remind_spec_{msg.from_user.id}",
                replace_existing=True,
            )

            # 4) Формируем клавиатуру — для новых пользователей это прямая ссылка
            button = InlineKeyboardButton(
                text="Подключиться к чату",
                url=invite_link
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[[button]])

            # 5) Отправляем сообщение с подарком
            await send_gift_message(msg.bot, msg.chat.id, reply_markup=kb)
