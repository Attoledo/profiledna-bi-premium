from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models.attempt import Attempt, Participant
from backend.models.result import ComputedResult, ReportSnapshot
from backend.reports.renderer import render_report_html


def _sync_db_url() -> str:
    """
    Script usa conexão SYNC (psycopg) por simplicidade/determinismo.
    Preferência:
      1) ALEMBIC_DATABASE_URL (SSOT migrações)
      2) converter DATABASE_URL asyncpg -> psycopg
    """
    settings = get_settings()
    sync_url = getattr(settings, "ALEMBIC_DATABASE_URL", None)
    if sync_url:
        return str(sync_url)

    url = str(settings.DATABASE_URL)
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    return url


def _ranking_payload(computed: ComputedResult) -> Dict[str, Any]:
    return {
        "top3": (computed.top3 or {}).get("top3", []),
        "top5": (computed.top5 or {}).get("top5", []),
        "bottom3": (computed.bottom3 or {}).get("bottom3", []),
    }


def _safe_datetime_str(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def _load_attempt(session: Session, attempt_id) -> Optional[Attempt]:
    return session.execute(
        select(Attempt).where(Attempt.id == attempt_id)
    ).scalar_one_or_none()


def _load_participant(session: Session, participant_id) -> Optional[Participant]:
    return session.execute(
        select(Participant).where(Participant.id == participant_id)
    ).scalar_one_or_none()


def _build_participant_payload(session: Session, attempt: Attempt) -> Dict[str, Any]:
    participant = _load_participant(session, attempt.participant_id)
    if not participant:
        return {}

    return {
        "id": str(participant.id),
        "nome": participant.nome or "",
        "sobrenome": participant.sobrenome or "",
        "email": participant.email or "",
        "empresa_nome": getattr(participant, "empresa_nome", None) or "",
        "tipo_aplicacao": participant.tipo_aplicacao or "",
    }


def _build_attempt_payload(attempt: Attempt) -> Dict[str, Any]:
    return {
        "id": str(attempt.id),
        "cargo": attempt.cargo or "",
        "status": attempt.status or "",
        "progress": int(attempt.progress or 0),
        "testdef_version": attempt.testdef_version or "",
        "data_inicio": _safe_datetime_str(attempt.data_inicio),
        "data_conclusao": _safe_datetime_str(attempt.data_conclusao),
    }


def _build_report_context(
    session: Session,
    *,
    attempt: Attempt,
    computed: ComputedResult,
) -> Dict[str, Any]:
    """
    Contexto mínimo canônico do relatório para uso em script/backfill.

    Mantém alinhamento com backend/services/submit.py:
      - participant/attempt reais
      - demais blocos novos com placeholders seguros
    """
    return {
        "token": "",
        "participant": _build_participant_payload(session, attempt),
        "attempt": _build_attempt_payload(attempt),
        "scores": computed.scores or {},
        "bands": computed.bands or {},
        "ranking": _ranking_payload(computed),
        "interpretations": computed.interpretations or {},
        "sintese_executiva": {},
        "paineis_area": [],
        "pdi_competencias": [],
        "gestor_rh": {},
        "nota_tecnica": {},
    }


def _ensure_snapshot_for_attempt(session: Session, attempt_id) -> bool:
    """
    Cria snapshot HTML idempotente (se não existir).
    Retorna True se criou, False se já existia ou não era possível.
    """
    existing = session.execute(
        select(ReportSnapshot).where(ReportSnapshot.attempt_id == attempt_id)
    ).scalar_one_or_none()
    if existing:
        return False

    computed = session.execute(
        select(ComputedResult).where(ComputedResult.attempt_id == attempt_id)
    ).scalar_one_or_none()
    if not computed:
        return False

    attempt = _load_attempt(session, attempt_id)
    if not attempt:
        return False

    context = _build_report_context(
        session,
        attempt=attempt,
        computed=computed,
    )
    html = render_report_html(context)

    snap = ReportSnapshot(
        attempt_id=attempt_id,
        html_content=html,
        pdf_path=None,  # SSOT: no submit/backfill HTML, pdf_path fica null
    )
    session.add(snap)
    return True


def backfill_html(limit: int, dry_run: bool) -> int:
    """
    Backfill idempotente: para todo ComputedResult existente, garante ReportSnapshot.
    - Não altera attempts/answers
    - Só cria report_snapshots ausentes
    - Implementação evita conflito de transação:
        * NUNCA executar session.execute() antes de session.begin() na mesma Session.
    """
    db_url = _sync_db_url()
    engine = create_engine(db_url, future=True)

    # 1) lista de attempt_ids (computed_results = fonte de verdade do "já calculado")
    with Session(engine) as session:
        q = (
            select(ComputedResult.attempt_id)
            .order_by(ComputedResult.attempt_id.desc())
            .limit(limit)
        )
        attempt_ids = [row[0] for row in session.execute(q).all()]

    scanned = 0
    would_create = 0
    created = 0

    # 2) para cada attempt: transação pequena e isolada
    for attempt_id in attempt_ids:
        scanned += 1

        if dry_run:
            # DRY RUN: checa existência sem begin
            with Session(engine) as session:
                exists = session.execute(
                    select(ReportSnapshot.id).where(ReportSnapshot.attempt_id == attempt_id)
                ).first()
                if not exists:
                    would_create += 1
            continue

        with Session(engine) as session:
            # IMPORTANTE: abrir begin ANTES de qualquer execute nesta session
            with session.begin():
                did = _ensure_snapshot_for_attempt(session, attempt_id)
                if did:
                    created += 1

    if dry_run:
        print(f"OK: backfill-html scanned={scanned} would_create={would_create}")
    else:
        print(f"OK: backfill-html scanned={scanned} created={created}")
    return 0


def generate_pdf_for_attempt(attempt_id: str, out_dir: str, dry_run: bool) -> int:
    """
    Gera PDF (lazy) a partir do snapshot HTML (SSOT):
      - Se report_snapshot não existir, tenta criar (idempotente) a partir de computed_results.
      - Se pdf_path já existir, não regenera.
      - Caso contrário, gera via WeasyPrint e atualiza pdf_path.
    """
    try:
        from weasyprint import HTML  # type: ignore
    except Exception as e:
        print(f"ERROR: WeasyPrint não disponível no ambiente: {e}", file=sys.stderr)
        return 2

    db_url = _sync_db_url()
    engine = create_engine(db_url, future=True)

    outp = Path(out_dir).resolve()
    outp.mkdir(parents=True, exist_ok=True)

    with Session(engine) as session:
        snap = session.execute(
            select(ReportSnapshot).where(ReportSnapshot.attempt_id == attempt_id)
        ).scalar_one_or_none()

        if not snap:
            if dry_run:
                print("DRY_RUN: snapshot não existe; seria criado antes do PDF.")
            else:
                with session.begin():
                    ok = _ensure_snapshot_for_attempt(session, attempt_id)
                    if not ok:
                        print("ERROR: não foi possível criar snapshot (computed_result ausente ou attempt ausente).", file=sys.stderr)
                        return 3
                snap = session.execute(
                    select(ReportSnapshot).where(ReportSnapshot.attempt_id == attempt_id)
                ).scalar_one()

        if snap.pdf_path:
            print(f"OK: pdf já existe (pdf_path={snap.pdf_path})")
            return 0

        pdf_filename = f"report_{attempt_id}.pdf"
        pdf_path = outp / pdf_filename

        if dry_run:
            print(f"DRY_RUN: geraria PDF em {pdf_path}")
            return 0

        HTML(string=snap.html_content, base_url=str(Path.cwd())).write_pdf(str(pdf_path))

        with session.begin():
            snap2 = session.execute(
                select(ReportSnapshot).where(ReportSnapshot.id == snap.id)
            ).scalar_one()
            snap2.pdf_path = str(pdf_path)
            session.add(snap2)

        print(f"OK: PDF gerado e cacheado em pdf_path={pdf_path}")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="ProfileDNA — utilitário SSOT: HTML snapshot + PDF lazy (WeasyPrint)")
    ap.add_argument("--dry-run", action="store_true", help="Não escreve nada no DB/disco; apenas simula.")
    ap.add_argument("--backfill-html", action="store_true", help="Cria report_snapshots ausentes (idempotente).")
    ap.add_argument("--limit", type=int, default=500, help="Limite de attempts (via computed_results) para backfill.")
    ap.add_argument("--attempt-id", type=str, default=None, help="Attempt ID (UUID) para gerar PDF.")
    ap.add_argument("--out-dir", type=str, default="volumes/reports", help="Diretório onde salvar PDFs.")

    args = ap.parse_args()

    if args.backfill_html:
        return backfill_html(limit=int(args.limit), dry_run=bool(args.dry_run))

    if args.attempt_id:
        return generate_pdf_for_attempt(args.attempt_id, args.out_dir, dry_run=bool(args.dry_run))

    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
