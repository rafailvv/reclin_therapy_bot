"""Authenticate Telegram Mini App requests before database or Bot API access."""
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import HTTPException, Request
from ..config import settings

MAX_AGE_SECONDS = 24 * 60 * 60


def verify_init_data(raw: str, token: str, now: float | None = None) -> dict:
    try:
        if not raw or len(raw) > 16384:
            raise ValueError("missing initData")
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
        fields = dict(pairs)
        if len(fields) != len(pairs):
            raise ValueError("duplicate fields")
        supplied_hash = fields.pop("hash")
        check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
        secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, supplied_hash):
            raise ValueError("invalid signature")
        age = (time.time() if now is None else now) - int(fields["auth_date"])
        if age < -30 or age > MAX_AGE_SECONDS:
            raise ValueError("expired initData")
        user = json.loads(fields["user"])
        if not isinstance(user, dict) or type(user.get("id")) is not int or user["id"] <= 0:
            raise ValueError("invalid user")
        return user
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        raise HTTPException(401, "Откройте форму заново через кнопку в Telegram.") from exc


def get_telegram_user(request: Request) -> dict:
    return verify_init_data(request.headers.get("X-Telegram-Init-Data", ""), settings.bot_token)
