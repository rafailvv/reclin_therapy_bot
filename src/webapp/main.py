import logging
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from aiogram import Bot
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .auth import get_telegram_user
from ..config import settings
from ..db import async_session
from ..models import User
from ..services.invite import create_one_time_invite

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI()
app.mount("/static", StaticFiles(directory="src/webapp/static"), name="static")
templates = Jinja2Templates(directory="src/webapp/templates")
bot = Bot(token=settings.bot_token)


@app.middleware("http")
async def private_responses(request: Request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if "X-Telegram-Init-Data" not in request.headers:
        return templates.TemplateResponse("bootstrap.html", {"request": request})
    uid = get_telegram_user(request)["id"]
    logger.info("Handling index GET for user %s", uid)

    async with async_session() as sess:
        user = await sess.scalar(
            select(User).where(User.telegram_id == uid)
        )

    # Если пользователя нет или он не заполнил fio или specialization — показываем форму
    if not user or user.fio is None or user.specialization is None:
        logger.info(
            "User %s incomplete (%s); returning registration form",
            uid,
            f"fio={user.fio!r}, specialization={user.specialization!r}" if user else "no user",
        )
        return templates.TemplateResponse(
            "form.html",
            {"request": request}
        )

    # Иначе — показываем страницу успеха с invite_link
    logger.info("User %s fully registered; returning success template", uid)
    return templates.TemplateResponse(
        "success.html",
        {
            "request": request,
            "invite_link": user.invite_link
        }
    )


@app.post("/register")
async def register(request: Request, telegram_user: dict = Depends(get_telegram_user)):
    try:
        data = await request.json()
    except ValueError as exc:
        raise HTTPException(400, "Invalid registration data") from exc
    if not isinstance(data, dict):
        raise HTTPException(400, "Invalid registration data")
    tg_id = telegram_user["id"]
    if str(data.get("telegram_id", tg_id)) != str(tg_id):
        raise HTTPException(403, "Telegram user mismatch")

    await bot.unban_chat_member(chat_id=settings.chat_id, user_id=tg_id)

    # 1) Создаём новую одноразовую ссылку
    invite = await create_one_time_invite(bot)

    # 2) UPSERT: вставляем или обновляем все поля, включая новую invite_link
    stmt = pg_insert(User).values(
        telegram_id      = tg_id,
        username         = telegram_user.get("username"),
        fio              = data.get("fio"),
        specialization   = data.get("specialization"),
        email            = data.get("email"),
        invite_link      = invite,
    ).on_conflict_do_update(
        index_elements=[User.telegram_id],
        set_ = {
            "fio"            : data.get("fio"),
            "specialization" : data.get("specialization"),
            "email"          : data.get("email"),
            "invite_link"    : invite,
        }
    ).returning(User.invite_link)

    # 3) Выполняем запрос и возвращаем новую ссылку
    async with async_session() as sess:
        result     = await sess.execute(stmt)
        new_link   = result.scalar_one()
        await sess.commit()

    return {"link": new_link}