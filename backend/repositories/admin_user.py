from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.admin_user import AdminUser


async def get_admin_by_username(session: AsyncSession, username: str) -> Optional[AdminUser]:
    res = await session.execute(select(AdminUser).where(AdminUser.username == username))
    return res.scalar_one_or_none()


async def get_admin_by_id(session: AsyncSession, admin_id) -> Optional[AdminUser]:
    res = await session.execute(select(AdminUser).where(AdminUser.id == admin_id))
    return res.scalar_one_or_none()
