# src/config.py
from typing import List
from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    bot_token:    str
    database_url: PostgresDsn
    chat_id:      int
    admin_ids:    List[int] = [429272623]
    webapp_url:   str

    model_config = SettingsConfigDict(
        env_file = ".env",
        env_file_encoding = "utf-8",
        extra = "ignore",    # <— ignore any POSTGRES_* vars
    )

settings = Settings()
