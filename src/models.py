import datetime as dt
from sqlalchemy import String, DateTime, BigInteger
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fio: Mapped[str] = mapped_column(String(255))
    specialization: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255))
    invite_link: Mapped[str] = mapped_column(String(512))
    registered_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)



