from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from backend.config import get_settings


class Base(DeclarativeBase):
    """
    Base declarativa para models SQLAlchemy (async).
    """
    pass


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """
    Engine singleton para evitar múltiplas pools.
    """
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.DATABASE_URL,
            pool_pre_ping=True,
            future=True,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """
    Session factory singleton.
    """
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _sessionmaker


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """
    Context manager async para obter sessão.
    Uso:
        async with get_session() as session:
            ...
    """
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        await session.close()


async def db_ping() -> bool:
    """
    Ping simples no DB para healthcheck.
    """
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency: fornece AsyncSession para Depends(get_db).

    Implementação compatível com o padrão do projeto:
    reaproveita get_session() (asynccontextmanager).
    """
    async with get_session() as session:
        yield session
