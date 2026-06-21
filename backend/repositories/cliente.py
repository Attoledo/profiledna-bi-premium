from __future__ import annotations

from datetime import date
from typing import List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.attempt import Attempt
from backend.models.cliente import Cliente, RodadaAplicacao, SetorEmpresa
from backend.models.invite import Invite


DEFAULT_CLIENTE_NOME = "DEFAULT_CLIENTE"
DEFAULT_RODADA_NOME = "DEFAULT_RODADA_V1"
DEFAULT_SETOR_NOME = "GERAL"


def _normalize_cnpj(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None

    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits or None


# ============================================================
# CLIENTE
# ============================================================

async def get_cliente_by_id(session: AsyncSession, cliente_id) -> Optional[Cliente]:
    res = await session.execute(
        select(Cliente).where(Cliente.id == cliente_id)
    )
    return res.scalar_one_or_none()


async def get_cliente_by_nome(session: AsyncSession, nome: str) -> Optional[Cliente]:
    res = await session.execute(
        select(Cliente).where(Cliente.nome == nome)
    )
    return res.scalar_one_or_none()


async def get_cliente_by_cnpj(session: AsyncSession, cnpj: str | None) -> Optional[Cliente]:
    normalized = _normalize_cnpj(cnpj)
    if not normalized:
        return None

    res = await session.execute(select(Cliente))
    for cliente in res.scalars().all():
        if _normalize_cnpj(cliente.cnpj) == normalized:
            return cliente
    return None


async def list_clientes(session: AsyncSession) -> List[Cliente]:
    res = await session.execute(
        select(Cliente).order_by(Cliente.criado_em.desc())
    )
    return list(res.scalars().all())


async def create_cliente(
    session: AsyncSession,
    *,
    nome: str,
    razao_social: Optional[str] = None,
    cnpj: Optional[str] = None,
    endereco: Optional[str] = None,
    setor_mercado: Optional[str] = None,
    responsavel: Optional[str] = None,
    setor_responsavel: Optional[str] = None,
    email_responsavel: Optional[str] = None,
    ativo: bool = True,
) -> Cliente:
    cliente = Cliente(
        nome=nome,
        razao_social=razao_social,
        cnpj=_normalize_cnpj(cnpj),
        endereco=endereco,
        setor_mercado=setor_mercado,
        responsavel=responsavel,
        setor_responsavel=setor_responsavel,
        email_responsavel=email_responsavel,
        ativo=ativo,
    )
    session.add(cliente)
    await session.flush()
    return cliente


async def update_cliente(
    session: AsyncSession,
    *,
    cliente: Cliente,
    nome: Optional[str] = None,
    razao_social: Optional[str] = None,
    cnpj: Optional[str] = None,
    endereco: Optional[str] = None,
    setor_mercado: Optional[str] = None,
    responsavel: Optional[str] = None,
    setor_responsavel: Optional[str] = None,
    email_responsavel: Optional[str] = None,
    ativo: Optional[bool] = None,
) -> Cliente:
    if nome is not None:
        cliente.nome = nome
    if razao_social is not None:
        cliente.razao_social = razao_social
    if cnpj is not None:
        cliente.cnpj = _normalize_cnpj(cnpj)
    if endereco is not None:
        cliente.endereco = endereco
    if setor_mercado is not None:
        cliente.setor_mercado = setor_mercado
    if responsavel is not None:
        cliente.responsavel = responsavel
    if setor_responsavel is not None:
        cliente.setor_responsavel = setor_responsavel
    if email_responsavel is not None:
        cliente.email_responsavel = email_responsavel
    if ativo is not None:
        cliente.ativo = ativo

    session.add(cliente)
    await session.flush()
    return cliente


async def set_cliente_ativo(
    session: AsyncSession,
    *,
    cliente: Cliente,
    ativo: bool,
) -> Cliente:
    cliente.ativo = ativo
    session.add(cliente)
    await session.flush()
    return cliente


async def cliente_has_dependencies(
    session: AsyncSession,
    *,
    cliente_id,
) -> bool:
    rodada_count = await session.scalar(
        select(func.count()).select_from(RodadaAplicacao).where(RodadaAplicacao.cliente_id == cliente_id)
    )
    if rodada_count and int(rodada_count) > 0:
        return True

    setor_count = await session.scalar(
        select(func.count()).select_from(SetorEmpresa).where(SetorEmpresa.cliente_id == cliente_id)
    )
    if setor_count and int(setor_count) > 0:
        return True

    invite_count = await session.scalar(
        select(func.count()).select_from(Invite).where(Invite.cliente_id == cliente_id)
    )
    if invite_count and int(invite_count) > 0:
        return True

    attempt_count = await session.scalar(
        select(func.count()).select_from(Attempt).where(Attempt.cliente_id == cliente_id)
    )
    if attempt_count and int(attempt_count) > 0:
        return True

    return False


async def delete_cliente_if_empty(
    session: AsyncSession,
    *,
    cliente: Cliente,
) -> bool:
    has_dependencies = await cliente_has_dependencies(session, cliente_id=cliente.id)
    if has_dependencies:
        return False

    await session.execute(
        delete(Cliente).where(Cliente.id == cliente.id)
    )
    await session.flush()
    return True


# ============================================================
# RODADA
# ============================================================

async def get_rodada_by_id(session: AsyncSession, rodada_id) -> Optional[RodadaAplicacao]:
    res = await session.execute(
        select(RodadaAplicacao).where(RodadaAplicacao.id == rodada_id)
    )
    return res.scalar_one_or_none()


async def get_rodada_by_nome(session: AsyncSession, nome: str) -> Optional[RodadaAplicacao]:
    res = await session.execute(
        select(RodadaAplicacao).where(RodadaAplicacao.nome == nome)
    )
    return res.scalar_one_or_none()


async def list_rodadas_by_cliente(session: AsyncSession, cliente_id) -> List[RodadaAplicacao]:
    res = await session.execute(
        select(RodadaAplicacao)
        .where(RodadaAplicacao.cliente_id == cliente_id)
        .order_by(RodadaAplicacao.data_inicio.desc())
    )
    return list(res.scalars().all())


async def create_rodada(
    session: AsyncSession,
    *,
    cliente_id,
    nome: str,
    data_inicio: date,
    data_encerramento: Optional[date],
    criado_por,
) -> RodadaAplicacao:
    rodada = RodadaAplicacao(
        cliente_id=cliente_id,
        nome=nome,
        data_inicio=data_inicio,
        data_encerramento=data_encerramento,
        criado_por=criado_por,
    )
    session.add(rodada)
    await session.flush()
    return rodada


async def update_rodada(
    session: AsyncSession,
    *,
    rodada: RodadaAplicacao,
    nome: Optional[str] = None,
    data_inicio: Optional[date] = None,
    data_encerramento: Optional[date] = None,
) -> RodadaAplicacao:
    if nome is not None:
        rodada.nome = nome
    if data_inicio is not None:
        rodada.data_inicio = data_inicio
    if data_encerramento is not None:
        rodada.data_encerramento = data_encerramento

    session.add(rodada)
    await session.flush()
    return rodada


async def rodada_has_dependencies(
    session: AsyncSession,
    *,
    rodada_id,
) -> bool:
    invite_count = await session.scalar(
        select(func.count()).select_from(Invite).where(Invite.rodada_id == rodada_id)
    )
    if invite_count and int(invite_count) > 0:
        return True

    attempt_count = await session.scalar(
        select(func.count()).select_from(Attempt).where(Attempt.rodada_id == rodada_id)
    )
    if attempt_count and int(attempt_count) > 0:
        return True

    return False


async def delete_rodada_if_empty(
    session: AsyncSession,
    *,
    rodada: RodadaAplicacao,
) -> bool:
    has_dependencies = await rodada_has_dependencies(session, rodada_id=rodada.id)
    if has_dependencies:
        return False

    await session.execute(
        delete(RodadaAplicacao).where(RodadaAplicacao.id == rodada.id)
    )
    await session.flush()
    return True


# ============================================================
# SETOR
# ============================================================

async def get_setor_by_id(session: AsyncSession, setor_id) -> Optional[SetorEmpresa]:
    res = await session.execute(
        select(SetorEmpresa).where(SetorEmpresa.id == setor_id)
    )
    return res.scalar_one_or_none()


async def get_setor_by_nome(session: AsyncSession, nome: str) -> Optional[SetorEmpresa]:
    res = await session.execute(
        select(SetorEmpresa).where(SetorEmpresa.nome == nome)
    )
    return res.scalar_one_or_none()


async def list_setores_by_cliente(session: AsyncSession, cliente_id) -> List[SetorEmpresa]:
    res = await session.execute(
        select(SetorEmpresa)
        .where(SetorEmpresa.cliente_id == cliente_id)
        .order_by(SetorEmpresa.nome.asc())
    )
    return list(res.scalars().all())


async def create_setor(
    session: AsyncSession,
    *,
    cliente_id,
    nome: str,
) -> SetorEmpresa:
    setor = SetorEmpresa(
        cliente_id=cliente_id,
        nome=nome,
    )
    session.add(setor)
    await session.flush()
    return setor


async def update_setor(
    session: AsyncSession,
    *,
    setor: SetorEmpresa,
    nome: Optional[str] = None,
) -> SetorEmpresa:
    if nome is not None:
        setor.nome = nome

    session.add(setor)
    await session.flush()
    return setor


async def setor_has_dependencies(
    session: AsyncSession,
    *,
    setor_id,
) -> bool:
    invite_count = await session.scalar(
        select(func.count()).select_from(Invite).where(Invite.setor_id == setor_id)
    )
    if invite_count and int(invite_count) > 0:
        return True

    attempt_count = await session.scalar(
        select(func.count()).select_from(Attempt).where(Attempt.setor_id == setor_id)
    )
    if attempt_count and int(attempt_count) > 0:
        return True

    return False


async def delete_setor_if_unused(
    session: AsyncSession,
    *,
    setor: SetorEmpresa,
) -> bool:
    has_dependencies = await setor_has_dependencies(session, setor_id=setor.id)
    if has_dependencies:
        return False

    await session.execute(
        delete(SetorEmpresa).where(SetorEmpresa.id == setor.id)
    )
    await session.flush()
    return True


# ============================================================
# COMPATIBILIDADE COM BOOTSTRAP / DEFAULT SEED
# ============================================================

async def get_default_cliente(session: AsyncSession) -> Cliente:
    cli = await get_cliente_by_nome(session, DEFAULT_CLIENTE_NOME)
    if not cli:
        raise ValueError(f"DEFAULT seed ausente: Cliente.nome='{DEFAULT_CLIENTE_NOME}'")
    return cli


async def get_default_rodada(session: AsyncSession) -> RodadaAplicacao:
    rd = await get_rodada_by_nome(session, DEFAULT_RODADA_NOME)
    if not rd:
        raise ValueError(f"DEFAULT seed ausente: RodadaAplicacao.nome='{DEFAULT_RODADA_NOME}'")
    return rd


async def get_default_setor(session: AsyncSession) -> SetorEmpresa:
    st = await get_setor_by_nome(session, DEFAULT_SETOR_NOME)
    if not st:
        raise ValueError(f"DEFAULT seed ausente: SetorEmpresa.nome='{DEFAULT_SETOR_NOME}'")
    return st
