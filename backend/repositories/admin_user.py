from __future__ import annotations

from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.admin_user import ROLE_ADMIN, AdminUser


async def get_admin_by_username(session: AsyncSession, username: str) -> Optional[AdminUser]:
    res = await session.execute(select(AdminUser).where(AdminUser.username == username))
    return res.scalar_one_or_none()


async def get_admin_by_id(session: AsyncSession, admin_id) -> Optional[AdminUser]:
    res = await session.execute(select(AdminUser).where(AdminUser.id == admin_id))
    return res.scalar_one_or_none()


async def list_admins(session: AsyncSession) -> List[AdminUser]:
    res = await session.execute(select(AdminUser).order_by(AdminUser.username.asc()))
    return list(res.scalars().all())


async def create_admin(
    session: AsyncSession,
    *,
    username: str,
    password_hash: str,
    nome: str,
    ativo: bool = True,
    role: str = ROLE_ADMIN,
    requires_reset: bool = True,
    permissions: Optional[dict[str, Any]] = None,
) -> AdminUser:
    admin = AdminUser(
        username=username,
        password_hash=password_hash,
        nome=nome,
        ativo=ativo,
        role=role,
        requires_reset=requires_reset,
        permissions=permissions or {},
    )
    session.add(admin)
    await session.flush()
    return admin


async def set_admin_ativo(session: AsyncSession, admin_id, ativo: bool) -> Optional[AdminUser]:
    admin = await get_admin_by_id(session, admin_id)
    if not admin:
        return None
    admin.ativo = ativo
    await session.flush()
    return admin


async def update_admin_password_hash(
    session: AsyncSession,
    admin_id,
    password_hash: str,
) -> Optional[AdminUser]:
    admin = await get_admin_by_id(session, admin_id)
    if not admin:
        return None
    admin.password_hash = password_hash
    await session.flush()
    return admin


async def set_admin_requires_reset(session: AsyncSession, admin_id, requires_reset: bool) -> Optional[AdminUser]:
    admin = await get_admin_by_id(session, admin_id)
    if not admin:
        return None
    admin.requires_reset = requires_reset
    await session.flush()
    return admin


async def update_admin_role_and_permissions(
    session: AsyncSession,
    admin_id,
    *,
    role: str,
    permissions: dict[str, Any],
) -> Optional[AdminUser]:
    admin = await get_admin_by_id(session, admin_id)
    if not admin:
        return None
    admin.role = role
    admin.permissions = permissions
    await session.flush()
    return admin
