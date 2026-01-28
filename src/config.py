# src/config.py
import os
from typing import List, Union, Any, Dict, Tuple
from pydantic import PostgresDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# Загружаем .env файл явно
load_dotenv()

class Settings(BaseSettings):
    bot_token:    str
    database_url: PostgresDsn
    chat_id:      int
    webapp_url:   str
    webapp_port:  int = 8000
    
    # Database configuration
    postgres_db:      str = "reclin_bot"
    postgres_user:    str = "postgres"
    postgres_password: str = "password"
    postgres_port:    int = 5435
    admin_ids:        List[int] = [429272623]

    @computed_field
    @property
    def default_welcome_message(self) -> str:
        return os.getenv('DEFAULT_WELCOME_MESSAGE', '')

    @computed_field
    @property
    def default_gift_message(self) -> str:
        return os.getenv('DEFAULT_GIFT_MESSAGE', '')

    model_config = SettingsConfigDict(
        env_file = ".env",
        env_file_encoding = "utf-8",
        extra = "ignore",    # <— ignore any POSTGRES_* vars
    )

settings = Settings()
