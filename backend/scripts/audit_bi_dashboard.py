"""
Auditoria matemática do BI — valida os dados reais do banco contra os gráficos do dashboard.

Uso (a partir de profiledna/):
    python3 backend/scripts/audit_bi_dashboard.py
"""

import asyncio
import os
import sys

# Allow imports relative to profiledna/ root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from dotenv import load_dotenv

# Try loading the runtime .env (Docker) and fall back to process env vars
_env_path = os.path.join(os.path.dirname(__file__), "../../runtime/.env")
load_dotenv(dotenv_path=_env_path, override=False)  # process env takes priority

# Rewrite Docker service name to localhost if needed
_db_url = os.environ.get("DATABASE_URL", "")
if "db:5432" in _db_url:
    os.environ["DATABASE_URL"] = _db_url.replace("db:5432", "localhost:5433")

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.bi.services import build_bi_service_payload


async def run_audit() -> None:
    db_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(db_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        print("\n" + "=" * 62)
        print("  AUDITORIA MATEMÁTICA DO BI — ProfileDNA Dashboard")
        print("=" * 62)

        payload = await build_bi_service_payload(session)

        # ── 1. DISTRIBUIÇÃO POR SETOR ────────────────────────────────
        print("\n[1] DISTRIBUIÇÃO POR SETOR (Doughnut Chart)")
        print("-" * 42)
        setor_dist = payload.setor_distribution or []
        total_setor = sum(int(row.get("count", 0)) for row in setor_dist)
        if setor_dist:
            for row in sorted(setor_dist, key=lambda r: -int(r.get("count", 0))):
                label = row.get("label") or row.get("setor") or row.get("name") or "?"
                count = int(row.get("count", 0))
                pct = (count / total_setor * 100) if total_setor else 0
                print(f"  {label:<30} {count:>5}  ({pct:.1f}%)")
            print(f"  {'TOTAL':<30} {total_setor:>5}")
        else:
            print("  (nenhum dado retornado)")

        # ── 2. TOP 5 FORÇAS — frequência ────────────────────────────
        print("\n[2] TOP 5 FORÇAS DOMINANTES (Barras Horizontais)")
        print("-" * 42)
        top5 = payload.top5_frequency or []
        if top5:
            for i, row in enumerate(top5[:5], 1):
                dim = row.get("dimension") or row.get("label") or row.get("name") or "?"
                count = int(row.get("count", 0))
                pct = float(row.get("pct") or row.get("percentage") or 0)
                print(f"  {i}. {dim:<28} {count:>5} registros  ({pct:.1f}%)")
        else:
            print("  (nenhum dado retornado)")

        # ── 3. OVERVIEW CARDS ────────────────────────────────────────
        print("\n[3] OVERVIEW CARDS")
        print("-" * 42)
        for card in payload.overview_cards or []:
            key = card.get("key") or card.get("label") or "?"
            val = card.get("value")
            print(f"  {key:<40} {val}")

        print("\n" + "=" * 62)
        print("  Auditoria concluída. Compare os valores acima com os")
        print("  gráficos renderizados no dashboard.")
        print("=" * 62 + "\n")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_audit())
