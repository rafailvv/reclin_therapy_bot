from aiogram import Router, F
from aiogram.types import (
    Message, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
)
from ..config import settings

router = Router()

WELCOME_TEXT = (
    "🩺 <b>Как пользоваться чатом по терапии</b>\n"
    "Добро пожаловать!\n"
    "Вы находитесь в профессиональном чате для врачей и ординаторов терапевтических специальностей. "
    "Здесь можно задавать вопросы, делиться опытом и получать полезные материалы.\n\n"
    "Чат разделён на вкладки:\n"
    "● 📌 <b>ВАЖНОЕ, АНОНСЫ</b> — объявления о прямых эфирах, расписание, новости.\n"
    "● 💬 <b>Общение</b> — свободное общение с коллегами, обсуждения.\n"
    "● 🤝 <b>Прошу совета у коллег</b> — задавайте вопросы экспертам и другим участникам сообщества.\n"
    "● 📚 <b>Эфиры и материалы</b> — записи трансляций, памятки, гайды и другие полезные материалы.\n\n"
    "🔧 По техническим вопросам: @reclin2022"
)

GIFT_TEXT = (
    "🎁 <b>Хотим сразу поделиться с тобой стартовым набором полезных материалов:</b>\n"
    "📌 Памятка «под стекло» по артериальной гипертензии — <a href='https://disk.yandex.ru/d/aCHhf7g7i_KHgw'>Скачать</a>\n"
    "📌 Памятки «под стекло» по диарее и запору — <a href='https://disk.yandex.ru/d/Qf_sd_zUepxUPw'>Скачать</a>\n"
    "📌 Шаблоны осмотров при НАЖБП и гастрите — <a href='https://disk.yandex.ru/d/0cGXx48hKweI8A'>Скачать</a>\n"
    "📌 Гайд: как оформить лист нетрудоспособности — <a href='https://disk.yandex.ru/d/0cGXx48hKweI8A'>Скачать</a>\n"
    "📌 Таблица с лекарственными препаратами по клинреку «Гастрит» — <a href='https://disk.yandex.ru/d/C4drU9y2DZEQuA'>Скачать</a>\n\n"
    "💬 Больше полезных материалов тебя ждёт в нашем чате — оставайся с нами!"
)

@router.message(F.text == "/start")
async def cmd_start(msg: Message):
    await msg.answer(WELCOME_TEXT)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="Подключиться к чату",
                web_app=WebAppInfo(url=f"{settings.webapp_url}/?uid={msg.from_user.id}")
            )
        ]]
    )
    await msg.answer(GIFT_TEXT, reply_markup=kb)
