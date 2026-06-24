from __future__ import annotations

import asyncio
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.result import PremiumReportSnapshot

# Detecta a raiz do backend dinamicamente (substitui o "/app" fixo de Docker
# por um caminho real do projeto local, evitando OSError em ambientes onde
# "/app" não existe ou é somente leitura).
BASE_DIR = Path(__file__).resolve().parent.parent


_LOCKS: dict[str, asyncio.Lock] = {}


def _get_lock(key: str) -> asyncio.Lock:
    if key not in _LOCKS:
        _LOCKS[key] = asyncio.Lock()
    return _LOCKS[key]


def _rewrite_static_urls_for_pdf(html: str) -> str:
    """
    Reescreve referências estáticas absolutas para leitura local do WeasyPrint.
    """
    return html.replace(
        'href="/static/css/app.css"',
        f'href="file://{BASE_DIR}/static/css/app.css"',
    )


async def ensure_premium_pdf_cached(
    session: AsyncSession,
    attempt_id: str,
    reports_dir: str = os.getenv(
        "PREMIUM_REPORTS_DIR", str(BASE_DIR / "volumes" / "reports" / "premium")
    ),
) -> str:
    """
    Geração lazy do PDF premium com persistência separada.

    Fluxo:
      - lê PremiumReportSnapshot por attempt_id
      - se pdf_path já existir, reutiliza
      - se não existir, gera PDF via WeasyPrint
      - persiste pdf_path premium separado
      - retorna caminho final do artefato premium
    """
    res = await session.execute(
        select(PremiumReportSnapshot).where(PremiumReportSnapshot.attempt_id == attempt_id)
    )
    snap = res.scalar_one_or_none()
    if not snap:
        raise ValueError("PremiumReportSnapshot inexistente para este attempt_id")

    if snap.pdf_path:
        return str(snap.pdf_path)

    lock = _get_lock(str(attempt_id))

    async with lock:
        res2 = await session.execute(
            select(PremiumReportSnapshot).where(PremiumReportSnapshot.id == snap.id)
        )
        snap2 = res2.scalar_one()

        if snap2.pdf_path:
            return str(snap2.pdf_path)

        try:
            from weasyprint import HTML  # type: ignore
        except Exception as exc:
            raise RuntimeError(f"WeasyPrint não disponível: {exc}") from exc

        out_dir = Path(reports_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        pdf_filename = f"premium_report_{attempt_id}.pdf"
        pdf_path = out_dir / pdf_filename

        html = _rewrite_static_urls_for_pdf(str(snap2.html_content))
        base_url = os.getenv("PDF_BASE_URL", f"file://{BASE_DIR}/")
        HTML(string=html, base_url=base_url).write_pdf(str(pdf_path))

        snap2.pdf_path = str(pdf_path)
        session.add(snap2)

        return str(pdf_path)
