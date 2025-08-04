import datetime as dt
from sqlalchemy import String, DateTime, BigInteger
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username:    Mapped[str | None] = mapped_column(String(64),  nullable=True)
    fio:         Mapped[str | None] = mapped_column(String(255), nullable=True)
    specialization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email:       Mapped[str | None] = mapped_column(String(255), nullable=True)
    invite_link: Mapped[str]       = mapped_column(String(512), nullable=False)
    registered_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, nullable=False
    )


class BotMessage(Base):
    __tablename__ = "bot_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'welcome' или 'gift'
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)  # ID сообщения в Telegram
    from_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)  # ID чата-источника
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow, nullable=False
    )


