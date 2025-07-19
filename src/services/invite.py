from aiogram import Bot
from src.config import settings

async def create_one_time_invite(bot: Bot) -> str:
    res = await bot.create_chat_invite_link(
        chat_id=settings.chat_id,
        # member_limit=1,
        creates_join_request=False
    )
    return res.invite_link
