# services/broadcast.py

import asyncio
import logging
from typing import Sequence
from aiogram import Bot
from aiogram.types import (
    Message, InputMediaPhoto, InputMediaDocument, InputMediaVideo, MessageEntity
)
import json

async def broadcast(
    bot: Bot,
    tg_ids: Sequence[int],
    *,
    caption: str = "",
    caption_entities: str | None = None,
    file_ids: str | None = None,
    throttle: float = 0.05,
) -> tuple[int, int]:
    """
    Рассылает сообщение с вложениями (если есть) и caption пользователям.
    :param bot: экземпляр бота
    :param tg_ids: список ID пользователей
    :param caption: текст сообщения или подпись к файлу
    :param caption_entities: сериализованные caption_entities
    :param file_ids: JSON-строка с массивом словарей: [{"type": "photo", "file_id": "..."}]
    """
    attachments = json.loads(file_ids) if file_ids else []
    entities = (
        [MessageEntity(**ent) for ent in json.loads(caption_entities)]
        if caption_entities
        else None
    )

    sent = 0
    failed = 0

    for uid in tg_ids:
        try:
            if attachments:
                if len(attachments) > 1:
                    media = []
                    for idx, att in enumerate(attachments):
                        media_type = att["type"]
                        file_id = att["file_id"]
                        is_first = idx == 0
                        caption_part = caption if is_first else None
                        ent = entities if is_first else None

                        if media_type == "photo":
                            media.append(InputMediaPhoto(media=file_id, caption=caption_part, caption_entities=ent, parse_mode=None))
                        elif media_type == "document":
                            media.append(InputMediaDocument(media=file_id, caption=caption_part, caption_entities=ent, parse_mode=None))
                        elif media_type == "video":
                            media.append(InputMediaVideo(media=file_id, caption=caption_part, caption_entities=ent, parse_mode=None))
                    await bot.send_media_group(chat_id=uid, media=media)
                else:
                    file = attachments[0]
                    typ, fid = file["type"], file["file_id"]
                    if typ == "photo":
                        await bot.send_photo(chat_id=uid, photo=fid, caption=caption, caption_entities=entities, parse_mode=None)
                    elif typ == "document":
                        await bot.send_document(chat_id=uid, document=fid, caption=caption, caption_entities=entities, parse_mode=None)
                    elif typ == "video":
                        await bot.send_video(chat_id=uid, video=fid, caption=caption, caption_entities=entities, parse_mode=None)
            else:
                await bot.send_message(chat_id=uid, text=caption, entities=entities, parse_mode=None)
            sent += 1
        except Exception as e:
            logging.warning(f"[broadcast] Не удалось отправить пользователю {uid}: {e}")
            failed += 1

        await asyncio.sleep(throttle)

    return sent, failed
