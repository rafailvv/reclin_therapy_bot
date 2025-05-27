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

app = FastAPI()
app.mount("/static", StaticFiles(directory="src/webapp/static"), name="static")
templates = Jinja2Templates(directory="src/webapp/templates")
bot = Bot(token=settings.bot_token)

def get_telegram_user_id(request: Request) -> int:
    # Telegram WebApp передаёт initData, бэкенд должен валидировать подпись.
    # Для примера: берём id из query (?uid=123) — в реальном коде проверяйте hash!
    uid = request.query_params.get("uid")
    if not uid:
        raise HTTPException(400, "no uid")
    return int(uid)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, uid: int = Depends(get_telegram_user_id)):
    async with async_session() as sess:
        user = await sess.scalar(select(User).where(User.telegram_id == uid))
    if user:
        return templates.TemplateResponse("success.html", {"request": request, "invite_link": user.invite_link})
    return templates.TemplateResponse("form.html", {"request": request})

@app.post("/register")
async def register(request: Request):
    data = await request.json()
    tg_id = int(data["telegram_id"])
    async with async_session() as sess:
        # если есть запись, возвращаем готовую ссылку
        user_db = await sess.scalar(select(User).where(User.telegram_id == tg_id))
        if user_db:
            return {"link": user_db.invite_link}
        invite = await create_one_time_invite(bot)
        new_user = User(
            telegram_id=tg_id,
            username=data.get("username"),
            fio=data["fio"],
            specialization=data["specialization"],
            email=data["email"],
            invite_link=invite
        )
        sess.add(new_user)
        await sess.commit()
    return {"link": invite}
