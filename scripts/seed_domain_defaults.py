from __future__ import annotations

import sys
from pathlib import Path

# Ensure /app (repo root inside container) is on PYTHONPATH
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


import asyncio
import uuid
from datetime import date

import bcrypt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.config import get_settings

DEFAULT_CLIENTE_NOME = "DEFAULT_CLIENTE"
DEFAULT_SETOR_NOME = "GERAL"
DEFAULT_RODADA_NOME = "DEFAULT_RODADA_V1"


async def _fetch_one_uuid(conn, sql: str, **params):
    res = await conn.execute(text(sql), params)
    row = res.first()
    return row[0] if row else None


async def main() -> None:
    settings = get_settings()

    # IMPORTANT: usa a mesma DATABASE_URL da app (asyncpg)
    engine = create_async_engine(settings.DATABASE_URL, future=True)

    async with engine.begin() as conn:
        # 1) ADMIN (necessário para RodadaAplicacao.criado_por NOT NULL)
        admin_id = await _fetch_one_uuid(
            conn,
            "select id from admin_users where username = :u limit 1",
            u=settings.ADMIN_USERNAME,
        )
        if not admin_id:
            pwd_hash = bcrypt.hashpw(
                settings.ADMIN_PASSWORD.encode("utf-8"),
                bcrypt.gensalt(),
            ).decode("utf-8")

            admin_id = uuid.uuid4()
            await conn.execute(
                text(
                    """
                    insert into admin_users (id, username, password_hash, nome, ativo)
                    values (:id, :u, :ph, :nome, true)
                    """
                ),
                {
                    "id": admin_id,
                    "u": settings.ADMIN_USERNAME,
                    "ph": pwd_hash,
                    "nome": "DEFAULT_ADMIN",
                },
            )

        # 2) CLIENTE default
        cliente_id = await _fetch_one_uuid(
            conn,
            "select id from clientes where nome = :n limit 1",
            n=DEFAULT_CLIENTE_NOME,
        )
        if not cliente_id:
            cliente_id = uuid.uuid4()
            await conn.execute(
                text(
                    """
                    insert into clientes (id, nome, setor_mercado, responsavel, email_responsavel, ativo)
                    values (:id, :nome, null, null, null, true)
                    """
                ),
                {"id": cliente_id, "nome": DEFAULT_CLIENTE_NOME},
            )

        # 3) SETOR default (FK cliente_id NOT NULL)
        setor_id = await _fetch_one_uuid(
            conn,
            """
            select id
            from setores_empresa
            where cliente_id = :cid and nome = :nome
            limit 1
            """,
            cid=cliente_id,
            nome=DEFAULT_SETOR_NOME,
        )
        if not setor_id:
            setor_id = uuid.uuid4()
            await conn.execute(
                text(
                    """
                    insert into setores_empresa (id, cliente_id, nome)
                    values (:id, :cid, :nome)
                    """
                ),
                {"id": setor_id, "cid": cliente_id, "nome": DEFAULT_SETOR_NOME},
            )

        # 4) RODADA default (FK cliente_id NOT NULL; criado_por NOT NULL)
        rodada_id = await _fetch_one_uuid(
            conn,
            """
            select id
            from rodadas_aplicacao
            where cliente_id = :cid and nome = :nome
            limit 1
            """,
            cid=cliente_id,
            nome=DEFAULT_RODADA_NOME,
        )
        if not rodada_id:
            rodada_id = uuid.uuid4()
            await conn.execute(
                text(
                    """
                    insert into rodadas_aplicacao
                      (id, cliente_id, nome, data_inicio, data_encerramento, criado_por)
                    values
                      (:id, :cid, :nome, :di, null, :cp)
                    """
                ),
                {
                    "id": rodada_id,
                    "cid": cliente_id,
                    "nome": DEFAULT_RODADA_NOME,
                    "di": date.today(),
                    "cp": admin_id,
                },
            )

    await engine.dispose()

    print("OK: seed_domain_defaults applied")
    print(f"  admin.username={settings.ADMIN_USERNAME}")
    print(f"  cliente.nome={DEFAULT_CLIENTE_NOME}")
    print(f"  setor.nome={DEFAULT_SETOR_NOME}")
    print(f"  rodada.nome={DEFAULT_RODADA_NOME}")


if __name__ == "__main__":
    asyncio.run(main())
