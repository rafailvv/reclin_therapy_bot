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
from ..models import User
from ..scheduler import scheduler, cleanup_unregistered  # see next section

router = Router()

WELCOME_TEXT = (
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

GIFT_TEXT = (
    "🎁 <b>Хотим сразу поделиться с тобой стартовым набором полезных материалов:</b>\n"
    "📌 Памятка «под стекло» по артериальной гипертензии — <a href='https://disk.yandex.ru/d/aCHhf7g7i_KHgw'>Скачать</a>\n"
    "📌 Памятки «под стекло» по диарее и запору — <a href='https://disk.yandex.ru/d/Qf_sd_zUepxUPw'>Скачать</a>\n"
    "📌 Шаблоны осмотров при НАЖБП и гастрите — <a href='https://disk.yandex.ru/d/0cGXx48hKweI8A'>Скачать</a>\n"
    "📌 Таблица с лекарственными препаратами по клинреку «Гастрит» — <a href='https://disk.yandex.ru/d/C4drU9y2DZEQuA'>Скачать</a>\n\n"
    "💬 Больше полезных материалов тебя ждёт в нашем чате — оставайся с нами!"
)

@router.message(F.text == "/start")
async def cmd_start(msg: Message):
    await msg.answer(WELCOME_TEXT)

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
            await msg.answer(GIFT_TEXT, reply_markup=kb)

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

            # 5) Отправляем GIFT_TEXT с клавиатурой
            await msg.answer(GIFT_TEXT, reply_markup=kb)
