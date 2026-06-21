from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.result import ReportSnapshot

# Lock global (SSOT): evita gerar o mesmo PDF simultaneamente
_LOCKS: Dict[str, asyncio.Lock] = {}


def _get_lock(key: str) -> asyncio.Lock:
    if key not in _LOCKS:
        _LOCKS[key] = asyncio.Lock()
    return _LOCKS[key]


def _rewrite_static_urls_for_pdf(html: str) -> str:
    """
    WeasyPrint resolve URLs via base_url.
    Nosso HTML tem href="/static/css/app.css" (URL absoluta web).
    Para PDF offline (sem HTTP), reescrevemos para file:///app/backend/static/...
    """
    return html.replace(
        'href="/static/css/app.css"',
        'href="file:///app/backend/static/css/app.css"',
    )


async def ensure_pdf_cached(
    session: AsyncSession,
    attempt_id: str,
    reports_dir: str = "/app/volumes/reports",
) -> str:
    """
    SSOT: PDF lazy no primeiro download.
      - Lê ReportSnapshot (HTML) por attempt_id
      - Se pdf_path já existe, retorna
      - Caso contrário, gera PDF via WeasyPrint, salva em disco, atualiza pdf_path, retorna

    Retorna o caminho (pdf_path) persistido.
    """
    # 1) buscar snapshot
    res = await session.execute(
        select(ReportSnapshot).where(ReportSnapshot.attempt_id == attempt_id)
    )
    snap = res.scalar_one_or_none()
    if not snap:
        raise ValueError("ReportSnapshot inexistente para este attempt_id")

    if snap.pdf_path:
        return str(snap.pdf_path)

    lock = _get_lock(str(attempt_id))
    async with lock:
        # Re-check dentro do lock (concorrência)
        res2 = await session.execute(
            select(ReportSnapshot).where(ReportSnapshot.id == snap.id)
        )
        snap2 = res2.scalar_one()

        if snap2.pdf_path:
            return str(snap2.pdf_path)

        try:
            from weasyprint import HTML  # type: ignore
        except Exception as e:
            raise RuntimeError(f"WeasyPrint não disponível: {e}") from e

        out_dir = Path(reports_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        pdf_filename = f"report_{attempt_id}.pdf"
        pdf_path = out_dir / pdf_filename

        html = _rewrite_static_urls_for_pdf(str(snap2.html_content))
        HTML(string=html, base_url="file:///app/").write_pdf(str(pdf_path))

        snap2.pdf_path = str(pdf_path)
        session.add(snap2)

        return str(pdf_path)
