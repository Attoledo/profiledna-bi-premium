from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
from jose import JWTError, jwt

from backend.config import get_settings


JWT_ALG = "HS256"
CSRF_COOKIE_NAME = "csrf_token"
ACCESS_COOKIE_NAME = "access_token"


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def create_access_token(subject: str, expires_minutes: int = 480) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=expires_minutes)

    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALG)


def decode_access_token(token: str) -> Optional[str]:
    """
    Retorna o 'sub' (admin_id) se token for válido; caso contrário, None.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[JWT_ALG])
        sub = payload.get("sub")
        return str(sub) if sub else None
    except JWTError:
        return None
    except Exception:
        return None


def new_csrf_token() -> str:
    """
    Token CSRF (double submit cookie).
    """
    return secrets.token_urlsafe(32)
