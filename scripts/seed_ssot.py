from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import date
from typing import Optional

import bcrypt
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.ssot.validator import validate_ssot

# Importa models para garantir metadata consistente (SSOT + Alembic)
import backend.models  # noqa: F401

from backend.models.admin_user import AdminUser
from backend.models.cliente import Cliente, RodadaAplicacao, SetorEmpresa


@dataclass(frozen=True)
class SeedResult:
    admin_created: bool
    cliente_created: bool
    rodada_created: bool
    setor_created: bool


def _require_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


def _hash_password_bcrypt(plain: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(plain.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def _sync_db_url() -> str:
    """
    Seed usa conexão SYNC (psycopg) por simplicidade/determinismo.
    Preferência:
      1) ALEMBIC_DATABASE_URL (SSOT migrações)
      2) converter DATABASE_URL asyncpg -> psycopg
    """
    settings = get_settings()
    if getattr(settings, "ALEMBIC_DATABASE_URL", None):
        return str(settings.ALEMBIC_DATABASE_URL)

    url = settings.DATABASE_URL
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    return url


def _get_or_create_admin(session: Session, username: str, password_plain: str) -> tuple[AdminUser, bool]:
    admin = session.execute(select(AdminUser).where(AdminUser.username == username)).scalar_one_or_none()
    if admin:
        return admin, False

    admin = AdminUser(
        username=username,
        password_hash=_hash_password_bcrypt(password_plain),
        nome=username,
        ativo=True,
    )
    session.add(admin)
    session.flush()
    return admin, True


def _get_or_create_cliente(session: Session, nome: str) -> tuple[Cliente, bool]:
    cli = session.execute(select(Cliente).where(Cliente.nome == nome)).scalar_one_or_none()
    if cli:
        return cli, False

    cli = Cliente(
        nome=nome,
        setor_mercado=None,
        responsavel=None,
        email_responsavel=None,
        ativo=True,
    )
    session.add(cli)
    session.flush()
    return cli, True


def _get_or_create_rodada(
    session: Session,
    cliente_id,
    criado_por_admin_id,
    nome: str,
    data_inicio: date,
) -> tuple[RodadaAplicacao, bool]:
    rd = (
        session.execute(
            select(RodadaAplicacao).where(
                RodadaAplicacao.cliente_id == cliente_id,
                RodadaAplicacao.nome == nome,
            )
        )
        .scalar_one_or_none()
    )
    if rd:
        return rd, False

    rd = RodadaAplicacao(
        cliente_id=cliente_id,
        nome=nome,
        data_inicio=data_inicio,
        data_encerramento=None,
        criado_por=criado_por_admin_id,
    )
    session.add(rd)
    session.flush()
    return rd, True


def _get_or_create_setor(session: Session, cliente_id, nome: str) -> tuple[SetorEmpresa, bool]:
    st = (
        session.execute(
            select(SetorEmpresa).where(
                SetorEmpresa.cliente_id == cliente_id,
                SetorEmpresa.nome == nome,
            )
        )
        .scalar_one_or_none()
    )
    if st:
        return st, False

    st = SetorEmpresa(cliente_id=cliente_id, nome=nome)
    session.add(st)
    session.flush()
    return st, True


def run_seed() -> SeedResult:
    # 1) Validar SSOT/JSONs (STRICT)
    v = validate_ssot(strict=True)
    if not v.ok:
        raise RuntimeError(f"SSOT validation failed unexpectedly: missing={v.missing_files} invalid={v.invalid_json_files}")

    # 2) Credenciais admin via env (SSOT)
    username = _require_env("ADMIN_USERNAME")
    password = _require_env("ADMIN_PASSWORD")

    # 3) Bootstrap mínimo (determinístico; pode ser alterado depois no painel)
    # Não criamos novas env vars (SSOT). Usamos nomes fixos e documentados.
    cliente_nome = "DEFAULT_CLIENTE"
    rodada_nome = "DEFAULT_RODADA_V1"
    setor_nome = "GERAL"

    db_url = _sync_db_url()
    engine = create_engine(db_url, future=True)

    with Session(engine) as session:
        with session.begin():
            admin, admin_created = _get_or_create_admin(session, username, password)
            cliente, cliente_created = _get_or_create_cliente(session, cliente_nome)
            rodada, rodada_created = _get_or_create_rodada(
                session,
                cliente_id=cliente.id,
                criado_por_admin_id=admin.id,
                nome=rodada_nome,
                data_inicio=date.today(),
            )
            setor, setor_created = _get_or_create_setor(session, cliente_id=cliente.id, nome=setor_nome)

    return SeedResult(
        admin_created=admin_created,
        cliente_created=cliente_created,
        rodada_created=rodada_created,
        setor_created=setor_created,
    )


def main() -> None:
    res = run_seed()
    print("OK: seed_ssot concluído (idempotente).")
    print(
        f"admin_created={res.admin_created} "
        f"cliente_created={res.cliente_created} "
        f"rodada_created={res.rodada_created} "
        f"setor_created={res.setor_created}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: seed_ssot falhou: {e}", file=sys.stderr)
        raise
