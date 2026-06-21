from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.cliente import Cliente, RodadaAplicacao, SetorEmpresa


async def list_clientes(session: AsyncSession) -> List[Cliente]:
    res = await session.execute(select(Cliente).order_by(Cliente.criado_em.desc()))
    return list(res.scalars().all())


async def get_cliente_by_id(session: AsyncSession, cliente_id) -> Optional[Cliente]:
    res = await session.execute(select(Cliente).where(Cliente.id == cliente_id))
    return res.scalar_one_or_none()


async def list_rodadas_by_cliente(session: AsyncSession, cliente_id) -> List[RodadaAplicacao]:
    res = await session.execute(
        select(RodadaAplicacao)
        .where(RodadaAplicacao.cliente_id == cliente_id)
        .order_by(RodadaAplicacao.data_inicio.desc())
    )
    return list(res.scalars().all())


async def list_setores_by_cliente(session: AsyncSession, cliente_id) -> List[SetorEmpresa]:
    res = await session.execute(
        select(SetorEmpresa)
        .where(SetorEmpresa.cliente_id == cliente_id)
        .order_by(SetorEmpresa.nome.asc())
    )
    return list(res.scalars().all())
