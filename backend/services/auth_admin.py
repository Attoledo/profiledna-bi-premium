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


def hash_password(plain_password: str) -> str:
    """
    Hash bcrypt (12 rounds, mesmo padrão usado em scripts/seed_ssot.py) para
    qualquer senha de admin antes de ela tocar o banco — usado tanto na
    criação de novos administradores quanto no reset de senha pela UI.
    """
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    """
    Gera o JWT de sessão do admin. Quando 'expires_minutes' não é informado
    explicitamente, o tempo de expiração vem de 'settings.ACCESS_TOKEN_EXPIRE_MINUTES'
    (config.py) — eliminando o hardcode fixo que antes ignorava essa configuração.
    """
    settings = get_settings()
    effective_expires_minutes = (
        expires_minutes if expires_minutes is not None else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=effective_expires_minutes)

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
