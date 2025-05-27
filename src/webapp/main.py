import logging
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from aiogram import Bot

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


def get_telegram_user_id(request: Request) -> int:
    logger.debug("Extracting Telegram user id from request query params")
    uid = request.query_params.get("uid")
    if not uid:
        logger.warning("No uid provided in request")
        raise HTTPException(400, "no uid")
    logger.info("Received request from Telegram user %s", uid)
    return int(uid)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, uid: int = Depends(get_telegram_user_id)):
    logger.info("Handling index GET for user %s", uid)
    async with async_session() as sess:
        user = await sess.scalar(select(User).where(User.telegram_id == uid))
    if user:
        logger.info("User %s found; returning success template", uid)
        return templates.TemplateResponse(
            "success.html", {"request": request, "invite_link": user.invite_link}
        )
    logger.info("User %s not found; returning registration form", uid)
    return templates.TemplateResponse("form.html", {"request": request})


@app.post("/register")
async def register(request: Request):
    logger.info("Registration attempt")
    try:
        data = await request.json()
        tg_id = int(data.get("telegram_id", 0))
        logger.debug("Parsed registration data for user %s: %s", tg_id, data)
    except Exception as e:
        logger.error("Error parsing registration JSON: %s", e)
        raise HTTPException(400, "Invalid request payload")

    async with async_session() as sess:
        user_db = await sess.scalar(select(User).where(User.telegram_id == tg_id))
        if user_db:
            logger.info("User %s already registered; returning existing invite link", tg_id)
            return {"link": user_db.invite_link}

        logger.info("Creating one-time invite for new user %s", tg_id)
        invite = await create_one_time_invite(bot)
        new_user = User(
            telegram_id=tg_id,
            username=data.get("username"),
            fio=data.get("fio"),
            specialization=data.get("specialization"),
            email=data.get("email"),
            invite_link=invite,
        )
        sess.add(new_user)
        try:
            await sess.commit()
            logger.info("New user %s registered successfully", tg_id)
        except Exception as e:
            logger.error("Database commit failed for user %s: %s", tg_id, e)
            raise HTTPException(500, "Internal server error")

    return {"link": invite}
