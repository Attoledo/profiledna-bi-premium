from __future__ import annotations

import csv
import io
import re
import unicodedata
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from xml.sax.saxutils import escape as xml_escape

from backend.bi.charts import build_bi_chart_bundle
from backend.bi.services import (
    BIServiceFilters,
    build_bi_comparison_dimension_table,
    build_bi_service_payload,
)
from backend.database import get_db
from backend.models.attempt import Attempt, Participant
from backend.models.result import ComputedResult, ReportSnapshot
from backend.repositories.admin_user import get_admin_by_id, get_admin_by_username
from backend.repositories.cliente import (
    create_cliente,
    create_rodada,
    create_setor,
    delete_cliente_if_empty,
    delete_rodada_if_empty,
    delete_setor_if_unused,
    get_cliente_by_id,
    get_rodada_by_id,
    get_setor_by_id,
    list_clientes,
    list_rodadas_by_cliente,
    list_setores_by_cliente,
    set_cliente_ativo,
    update_cliente,
    update_rodada,
    update_setor,
)
from backend.repositories.invite import (
    create_invite,
    get_invite_by_id,
    list_invites_by_rodada,
)
from backend.reports.pdf import ensure_pdf_cached
from backend.services.auth_admin import (
    ACCESS_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    create_access_token,
    decode_access_token,
    new_csrf_token,
    verify_password,
)
from backend.services.invite import generate_invite_token

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="backend/templates")


def _redirect_login() -> RedirectResponse:
    return RedirectResponse(url="/admin/login", status_code=303)


def _redirect_dashboard() -> RedirectResponse:
    return RedirectResponse(url="/admin/dashboard", status_code=303)


def _safe_uuid(value: str | None):
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except Exception:
        return None


def _safe_str(value: Any) -> str:
    if value is None:
        return "-"
    return str(value)


def _build_download_name_slug(
    nome: str | None,
    sobrenome: str | None,
    fallback: str,
    *,
    max_length: int = 80,
) -> str:
    raw = " ".join(
        part.strip()
        for part in [str(nome or ""), str(sobrenome or "")]
        if str(part or "").strip()
    ).strip()

    if not raw:
        raw = str(fallback or "").strip()

    normalized = unicodedata.normalize("NFKD", raw)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.lower().strip()
    ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text)
    ascii_text = re.sub(r"-{2,}", "-", ascii_text).strip("-")

    if not ascii_text:
        ascii_text = str(fallback or "").strip().lower()

    if max_length > 0:
        ascii_text = ascii_text[:max_length].strip("-")

    return ascii_text or str(fallback or "arquivo").strip().lower()


def _parse_date_or_datetime(value: str | None):
    raw = str(value or "").strip()
    if not raw:
        return None

    try:
        if "T" in raw or " " in raw:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return date.fromisoformat(raw)
    except Exception:
        pass

    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except Exception:
            continue

    return None


def _bool_label(value: bool) -> str:
    return "Sim" if bool(value) else "Não"


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _normalize_text_key(value: str | None) -> str:
    return str(value or "").strip().lower()


def _build_admin_error_html(message: str, status_code: int = 400) -> HTMLResponse:
    html = f"""
    <!doctype html>
    <html lang="pt-br">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <title>ProfileDNA — Admin</title>
      </head>
      <body style="font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; padding: 24px;">
        <div style="max-width: 760px; margin: 0 auto;">
          <div style="padding: 14px 16px; background: #fee2e2; border: 1px solid #ef4444; border-radius: 10px;">
            <strong>Erro:</strong> {message}
          </div>
          <p style="margin-top: 16px;">
            <a href="/admin/dashboard">Voltar ao dashboard</a>
          </p>
        </div>
      </body>
    </html>
    """
    return HTMLResponse(content=html, status_code=status_code)


async def _validate_csrf(request: Request) -> bool:
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    header_token = request.headers.get("x-csrf-token")

    try:
        form = await request.form()
    except Exception:
        form = None

    form_token = None
    if form is not None:
        form_token = form.get("csrf_token")

    provided = header_token or form_token
    return bool(cookie_token and provided and cookie_token == provided)


async def _require_admin_post(
    request: Request,
    admin,
) -> tuple[bool, RedirectResponse | HTMLResponse | None]:
    if isinstance(admin, RedirectResponse):
        return False, admin
    if not await _validate_csrf(request):
        return False, _build_admin_error_html("CSRF inválido ou ausente.", status_code=403)
    return True, None


def _report_status_payload(
    computed_result: ComputedResult | None,
    report_snapshot: ReportSnapshot | None,
    pdf_path: str | None,
) -> dict[str, Any]:
    has_pdf = bool(pdf_path and Path(pdf_path).exists())
    return {
        "has_computed_result": computed_result is not None,
        "has_snapshot_html": report_snapshot is not None and bool(report_snapshot.html_content),
        "has_pdf": has_pdf,
        "computed_result_label": "Disponível" if computed_result is not None else "Indisponível",
        "snapshot_html_label": "Disponível"
        if report_snapshot is not None and bool(report_snapshot.html_content)
        else "Indisponível",
        "pdf_label": "Disponível" if has_pdf else "Indisponível",
    }


def _build_bi_service_filters(
    *,
    cliente_id: str | None = None,
    rodada_id: str | None = None,
    setor_id: str | None = None,
    cargo: str | None = None,
    tipo_aplicacao: str | None = None,
    status: str | None = None,
    only_completed: bool = False,
) -> BIServiceFilters:
    return BIServiceFilters(
        cliente_id=_clean_optional_text(cliente_id),
        rodada_id=_clean_optional_text(rodada_id),
        setor_id=_clean_optional_text(setor_id),
        cargo=_clean_optional_text(cargo),
        tipo_aplicacao=_clean_optional_text(tipo_aplicacao),
        attempt_status=_clean_optional_text(status),
        only_completed=bool(only_completed),
    )


def _normalize_bi_option_list(items: Any) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in list(items or []):
        if isinstance(item, dict):
            value = item.get("value")
            if value is None:
                value = item.get("id")
            label = item.get("label")
            if label is None:
                label = item.get("nome")
            if label is None:
                label = value
            normalized.append(
                {
                    "value": "" if value is None else str(value),
                    "label": "" if label is None else str(label),
                }
            )
        else:
            normalized.append(
                {
                    "value": str(item),
                    "label": str(item),
                }
            )
    return normalized


def _normalize_bi_filter_options(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    return {
        "clientes": _normalize_bi_option_list(raw.get("clientes", [])),
        "rodadas": _normalize_bi_option_list(raw.get("rodadas", [])),
        "setores": _normalize_bi_option_list(raw.get("setores", [])),
        "cargos": _normalize_bi_option_list(raw.get("cargos", [])),
        "tipos_aplicacao": _normalize_bi_option_list(raw.get("tipos_aplicacao", [])),
        "statuses": _normalize_bi_option_list(raw.get("statuses", [])),
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _pick_dimension_band(row: dict[str, Any]) -> str:
    low_pct = _safe_float(row.get("low_pct"))
    mid_pct = _safe_float(row.get("mid_pct"))
    high_pct = _safe_float(row.get("high_pct"))

    best = max(
        [("Baixa", low_pct), ("Média", mid_pct), ("Alta", high_pct)],
        key=lambda x: x[1],
    )
    return best[0]


def _build_dimension_distribution_summary(row: dict[str, Any]) -> str:
    total = _safe_int(row.get("count", 0))
    low_count = _safe_int(row.get("low_count", 0))
    mid_count = _safe_int(row.get("mid_count", 0))
    high_count = _safe_int(row.get("high_count", 0))
    low_pct = _safe_float(row.get("low_pct", 0.0))
    mid_pct = _safe_float(row.get("mid_pct", 0.0))
    high_pct = _safe_float(row.get("high_pct", 0.0))
    area = str(row.get("area") or "Não informada")

    return (
        f"Área: {area}. "
        f"Total analisado nesta dimensão: N={total}. "
        f"Baixa: {low_count} participante(s) ({low_pct:.2f}%). "
        f"Média: {mid_count} participante(s) ({mid_pct:.2f}%). "
        f"Alta: {high_count} participante(s) ({high_pct:.2f}%)."
    )


def _build_dimension_manager_reading(row: dict[str, Any], *, dimension_label: str, band: str) -> str:
    average_score = row.get("average_score", row.get("average"))
    median_score = row.get("median_score", row.get("median"))

    average_label = "-" if average_score is None else f"{_safe_float(average_score):.2f}"
    median_label = "-" if median_score is None else f"{_safe_float(median_score):.2f}"

    distribution = _build_dimension_distribution_summary(row)

    band_explanation_map = {
        "Baixa": (
            "Isso indica que, no grupo atual, essa dimensão aparece com menor intensidade na maior parte dos participantes. "
            "Em termos gerenciais, tende a ser um aspecto menos dominante no comportamento coletivo."
        ),
        "Média": (
            "Isso indica que, no grupo atual, essa dimensão aparece de forma equilibrada e consistente. "
            "Ela está presente, mas sem concentração extrema, o que sugere estabilidade e variabilidade moderada entre as pessoas avaliadas."
        ),
        "Alta": (
            "Isso indica que, no grupo atual, essa dimensão aparece com forte presença na maior parte dos participantes. "
            "Em termos gerenciais, tende a ser um traço mais dominante no comportamento coletivo."
        ),
    }

    return (
        f"Dimensão: {dimension_label}. "
        f"Média do grupo: {average_label}. "
        f"Mediana: {median_label}. "
        f"Faixa predominante: {band}. "
        f"A média mostra a intensidade média da dimensão no grupo. "
        f"A mediana mostra o ponto central do grupo, reduzindo o efeito de extremos. "
        f"A faixa resume onde a maioria do grupo se concentra. "
        f"{band_explanation_map.get(band, 'A faixa predominante ajuda a entender onde o grupo se concentra nesta dimensão.')} "
        f"{distribution}"
    )


def _build_dimension_rows_from_payload(payload) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for row in list(getattr(payload, "dimension_table", []) or []):
        dimension_key = str(
            row.get("dimension_key")
            or row.get("dimension")
            or row.get("label")
            or "-"
        )
        dimension_label = str(
            row.get("dimension_label")
            or row.get("label")
            or row.get("title")
            or row.get("name")
            or dimension_key
        )
        area = str(row.get("area") or "-")

        average_score = row.get("average_score", row.get("average"))
        average_score_label = (
            row.get("average_score_label")
            or row.get("average_label")
            or row.get("media")
            or row.get("value")
            or "-"
        )

        median_score = row.get("median_score", row.get("median"))
        median_score_label = (
            row.get("median_score_label")
            or row.get("median_label")
            or ("-" if median_score is None else f"{_safe_float(median_score):.2f}")
        )

        band = row.get("band") or row.get("faixa") or _pick_dimension_band(row)
        distribution_summary = _build_dimension_distribution_summary(row)
        manager_reading = _build_dimension_manager_reading(
            row,
            dimension_label=dimension_label,
            band=band,
        )

        description = (
            row.get("description")
            or row.get("leitura")
            or manager_reading
        )

        rows.append(
            {
                "dimension_key": dimension_key,
                "dimension_label": dimension_label,
                "dimension": dimension_key,
                "label": dimension_label,
                "area": area,
                "average": average_score,
                "average_label": row.get("average_label") or average_score_label,
                "average_score": average_score,
                "average_score_label": average_score_label,
                "median": median_score,
                "median_label": row.get("median_label") or median_score_label,
                "median_score": median_score,
                "median_score_label": median_score_label,
                "value": row.get("value") or average_score_label,
                "media": row.get("media") or average_score_label,
                "band": band,
                "faixa": row.get("faixa") or band,
                "description": description,
                "leitura": row.get("leitura") or description,
                "distribution_summary": distribution_summary,
                "manager_reading": manager_reading,
                "count": _safe_int(row.get("count", 0)),
                "low_count": _safe_int(row.get("low_count", 0)),
                "mid_count": _safe_int(row.get("mid_count", 0)),
                "high_count": _safe_int(row.get("high_count", 0)),
                "low_pct": _safe_float(row.get("low_pct", 0.0)),
                "mid_pct": _safe_float(row.get("mid_pct", 0.0)),
                "high_pct": _safe_float(row.get("high_pct", 0.0)),
            }
        )

    return rows


def _build_area_rows_from_payload(payload) -> list[dict[str, Any]]:
    radar_area = getattr(payload, "radar_area", {}) or {}
    details = list(radar_area.get("details", []) or [])

    rows: list[dict[str, Any]] = []

    if details:
        for item in details:
            avg = item.get("average_score")
            avg_label = "—" if avg is None else f"{_safe_float(avg):.2f}"
            count_dimensions = _safe_int(item.get("count_dimensions", 0))
            area = str(item.get("area") or "-")
            has_score = avg is not None

            rows.append(
                {
                    "label": area,
                    "area": area,
                    "value": avg_label,
                    "average": avg,
                    "average_score": avg,
                    "count_dimensions": count_dimensions,
                    "description": (
                        f"{count_dimensions} dimensão(ões) na área"
                        + (f" · média {avg_label}" if has_score else " · sem score consolidado")
                    ),
                }
            )
        return rows

    labels = list(radar_area.get("labels", []) or [])
    datasets = list(radar_area.get("datasets", []) or [])
    data: list[Any] = []
    if datasets:
        first_dataset = datasets[0] or {}
        data = list(first_dataset.get("data", []) or [])

    for idx, label in enumerate(labels):
        raw_value = data[idx] if idx < len(data) else None
        value = "—" if raw_value is None else f"{_safe_float(raw_value):.2f}"
        rows.append(
            {
                "label": str(label),
                "area": str(label),
                "value": value,
                "average": raw_value,
                "average_score": raw_value,
                "count_dimensions": 0,
                "description": "Média consolidada da macroárea no recorte atual.",
            }
        )

    return rows


def _build_dimension_lookup_from_payload(payload) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}

    for row in list(getattr(payload, "dimension_table", []) or []):
        dimension_key = str(
            row.get("dimension_key")
            or row.get("dimension")
            or row.get("label")
            or ""
        ).strip()

        dimension_label = str(
            row.get("dimension_label")
            or row.get("label")
            or ""
        ).strip()

        for candidate in (dimension_key, dimension_label):
            normalized = _normalize_text_key(candidate)
            if normalized:
                lookup[normalized] = row

    return lookup


def _get_dimension_row_for_ranking_item(
    item: dict[str, Any],
    *,
    dimension_lookup: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if not dimension_lookup:
        return None

    candidates = [
        item.get("dimension_key"),
        item.get("dimension"),
        item.get("letter"),
        item.get("dimension_label"),
        item.get("title"),
        item.get("name"),
        item.get("label"),
    ]

    for candidate in candidates:
        normalized = _normalize_text_key(candidate)
        if not normalized:
            continue
        matched = dimension_lookup.get(normalized)
        if matched is not None:
            return matched

    return None


def _is_generic_ranking_description(value: str | None) -> bool:
    text = str(value or "").strip()
    if not text:
        return True

    lowered = text.lower()

    generic_markers = [
        "sem descrição gerencial disponível",
        "ocorrência(s)",
        "percentual no grupo",
        "n=",
        "baixa ",
        "média ",
        "alta ",
    ]

    return any(marker in lowered for marker in generic_markers)


def _build_ranking_display_label(item: dict[str, Any]) -> str:
    dimension_label = str(
        item.get("dimension_label")
        or item.get("title")
        or item.get("name")
        or item.get("label")
        or ""
    ).strip()

    dimension_key = str(
        item.get("dimension_key")
        or item.get("dimension")
        or item.get("letter")
        or ""
    ).strip()

    if dimension_label:
        return dimension_label

    if dimension_key:
        return dimension_key

    return "-"


def _build_ranking_description(
    item: dict[str, Any],
    *,
    count: int,
    pct: float,
    area: str,
    dimension_lookup: dict[str, dict[str, Any]] | None = None,
) -> str:
    direct_description = str(
        item.get("description")
        or item.get("leitura")
        or item.get("meaning")
        or ""
    ).strip()

    matched_dimension_row = _get_dimension_row_for_ranking_item(
        item,
        dimension_lookup=dimension_lookup,
    )

    enriched_description = ""
    if matched_dimension_row is not None:
        enriched_description = str(
            matched_dimension_row.get("description")
            or matched_dimension_row.get("leitura")
            or matched_dimension_row.get("meaning")
            or ""
        ).strip()

    if direct_description and not _is_generic_ranking_description(direct_description):
        return direct_description

    if enriched_description and not _is_generic_ranking_description(enriched_description):
        return enriched_description

    if direct_description:
        return direct_description

    return f"Área: {area} · {count} ocorrência(s) · {pct:.2f}%"


def _build_ranking_rows(
    raw_rows: list[dict[str, Any]] | None,
    *,
    dimension_lookup: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for item in list(raw_rows or []):
        dimension_key = str(
            item.get("dimension_key")
            or item.get("dimension")
            or item.get("letter")
            or item.get("label")
            or "-"
        ).strip()

        dimension_label = str(
            item.get("dimension_label")
            or item.get("title")
            or item.get("name")
            or item.get("label")
            or dimension_key
            or "-"
        ).strip()

        display_label = _build_ranking_display_label(item)

        count = _safe_int(item.get("count", item.get("value", 0)), default=0)
        pct = _safe_float(item.get("pct", 0.0), default=0.0)
        area = str(item.get("area") or "-").strip() or "-"

        description = _build_ranking_description(
            item,
            count=count,
            pct=pct,
            area=area,
            dimension_lookup=dimension_lookup,
        )

        rows.append(
            {
                "label": display_label,
                "dimension": dimension_key,
                "dimension_key": dimension_key,
                "dimension_label": dimension_label,
                "value": count,
                "count": count,
                "pct": pct,
                "pct_label": item.get("pct_label") or f"{pct:.2f}%",
                "area": area,
                "description": description,
                "leitura": item.get("leitura") or description,
                "meaning": item.get("meaning") or description,
            }
        )
    return rows


def _build_overview_cards(payload) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for card in list(getattr(payload, "overview_cards", []) or []):
        cards.append(
            {
                "label": str(card.get("title") or card.get("label") or "Indicador"),
                "value": card.get("value", "-"),
                "description": card.get("description") or card.get("subtitle"),
            }
        )
    return cards


def _extract_chart_dict(chart_bundle: dict[str, Any], key: str, fallback_title: str) -> dict[str, Any]:
    chart = chart_bundle.get(key) or {}
    if not isinstance(chart, dict):
        return {
            "title": fallback_title,
            "labels": [],
            "values": [],
            "items": [],
            "has_data": False,
        }
    return chart


def _build_query_url(path: str, params: dict[str, Any]) -> str:
    cleaned: dict[str, str] = {}
    for key, value in params.items():
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        cleaned[key] = text

    if not cleaned:
        return path
    return f"{path}?{urlencode(cleaned)}"


def _compose_endereco(
    *,
    cep: str | None,
    logradouro: str | None,
    numero: str | None,
    complemento: str | None,
    telefone: str | None,
) -> str | None:
    addr_parts: list[str] = []
    if logradouro:
        piece = logradouro
        if numero:
            piece += f", {numero}"
        if complemento:
            piece += f" ({complemento})"
        addr_parts.append(piece)
    if cep:
        addr_parts.append(f"CEP: {cep}")
    if telefone:
        addr_parts.append(f"Tel: {telefone}")
    composed = " — ".join(addr_parts)
    return composed or None


def _build_contextual_bi_overview_url(
    *,
    cliente_id: str | None,
    rodada_id: str | None,
    setor_id: str | None = None,
    cargo: str | None = None,
    tipo_aplicacao: str | None = None,
    status: str | None = None,
    only_completed: bool | None = None,
) -> str:
    return _build_query_url(
        "/admin/bi/overview",
        {
            "cliente_id": _clean_optional_text(cliente_id),
            "rodada_id": _clean_optional_text(rodada_id),
            "setor_id": _clean_optional_text(setor_id),
            "cargo": _clean_optional_text(cargo),
            "tipo_aplicacao": _clean_optional_text(tipo_aplicacao),
            "status": _clean_optional_text(status),
            "only_completed": "true" if only_completed else None,
        },
    )


def _build_contextual_comparativo_url(
    *,
    cliente_id: str | None,
    rodada_id: str | None,
    right_cliente_id: str | None = None,
    right_rodada_id: str | None = None,
) -> str:
    clean_cliente_id = _clean_optional_text(cliente_id)
    clean_right_cliente_id = _clean_optional_text(right_cliente_id) or clean_cliente_id

    return _build_query_url(
        "/admin/bi/comparativo",
        {
            "left_cliente_id": clean_cliente_id,
            "left_rodada_id": _clean_optional_text(rodada_id),
            "right_cliente_id": clean_right_cliente_id,
            "right_rodada_id": _clean_optional_text(right_rodada_id),
        },
    )


def _build_contextual_participants_url(
    *,
    cliente_id: str | None,
    rodada_id: str | None,
    setor_id: str | None = None,
    cargo: str | None = None,
    tipo_aplicacao: str | None = None,
    status: str | None = None,
) -> str:
    return _build_query_url(
        "/admin/participants",
        {
            "cliente_id": _clean_optional_text(cliente_id),
            "rodada_id": _clean_optional_text(rodada_id),
            "setor_id": _clean_optional_text(setor_id),
            "cargo": _clean_optional_text(cargo),
            "tipo_aplicacao": _clean_optional_text(tipo_aplicacao),
            "status": _clean_optional_text(status),
        },
    )


def _get_attempt_tipo_aplicacao(attempt: Attempt) -> str | None:
    direct_value = _clean_optional_text(getattr(attempt, "tipo_aplicacao", None))
    if direct_value:
        return direct_value

    participant = getattr(attempt, "participant", None)
    if participant is None:
        return None

    return _clean_optional_text(getattr(participant, "tipo_aplicacao", None))


def _build_distinct_attempt_values(
    attempts: list[Attempt],
) -> tuple[list[str], list[str], list[str]]:
    cargo_options = sorted(
        {
            str(getattr(item, "cargo", "") or "").strip()
            for item in attempts
            if str(getattr(item, "cargo", "") or "").strip()
        }
    )

    tipo_options = sorted(
        {
            str(_get_attempt_tipo_aplicacao(item) or "").strip()
            for item in attempts
            if str(_get_attempt_tipo_aplicacao(item) or "").strip()
        }
    )

    status_options = sorted(
        {
            str(getattr(item, "status", "") or "").strip()
            for item in attempts
            if str(getattr(item, "status", "") or "").strip()
        }
    )

    return cargo_options, tipo_options, status_options


async def _build_cliente_scoped_filter_options(
    db: AsyncSession,
    *,
    cliente,
    selected_rodada_id: str | None = None,
    selected_setor_id: str | None = None,
) -> dict[str, Any]:
    rodadas = await list_rodadas_by_cliente(db, cliente.id)
    setores = await list_setores_by_cliente(db, cliente.id)

    attempts_for_options = await _load_all_attempts(
        db,
        cliente_id=str(cliente.id),
        rodada_id=selected_rodada_id,
        setor_id=selected_setor_id,
        limit=5000,
    )

    cargo_options, tipo_options, status_options = _build_distinct_attempt_values(attempts_for_options)

    return {
        "clientes": [{"id": str(cliente.id), "nome": str(getattr(cliente, "nome", "") or "")}],
        "rodadas": [{"id": str(item.id), "nome": item.nome} for item in rodadas],
        "setores": [{"id": str(item.id), "nome": item.nome} for item in setores],
        "cargos": cargo_options,
        "tipos_aplicacao": tipo_options,
        "statuses": status_options,
    }


async def _build_bi_filter_options_for_route(
    db: AsyncSession,
    *,
    base_filter_options: dict[str, Any],
    cliente_id: str | None,
    rodada_id: str | None,
    setor_id: str | None = None,
) -> tuple[dict[str, Any], Any | None]:
    clean_cliente_id = _clean_optional_text(cliente_id)
    if not clean_cliente_id:
        return _normalize_bi_filter_options(base_filter_options), None

    cliente_pk = _safe_uuid(clean_cliente_id) or clean_cliente_id
    cliente = await get_cliente_by_id(db, cliente_pk)
    if cliente is None:
        return _normalize_bi_filter_options(base_filter_options), None

    filter_options = await _build_cliente_scoped_filter_options(
        db,
        cliente=cliente,
        selected_rodada_id=_clean_optional_text(rodada_id),
        selected_setor_id=_clean_optional_text(setor_id),
    )
    return _normalize_bi_filter_options(filter_options), cliente


def _build_bi_template_context_from_payload(
    payload,
    *,
    page_title: str,
    page_subtitle: str,
    cliente: Any | None = None,
) -> dict[str, Any]:
    raw_chart_bundle = build_bi_chart_bundle(payload)

    if raw_chart_bundle is None:
        chart_bundle: dict[str, Any] = {}
    elif isinstance(raw_chart_bundle, dict):
        chart_bundle = dict(raw_chart_bundle)
    else:
        chart_bundle = {}
        for key in (
            "overview_cards",
            "radar_area_chart",
            "status_pie_chart",
            "tipo_aplicacao_pie_chart",
            "setor_pie_chart",
            "cargo_pie_chart",
            "dimension_table",
            "top5_cards",
            "bottom3_cards",
            "filter_options",
            "filters_applied",
            "meta",
            "radar_chart",
            "status_chart",
            "top5_chart",
            "bottom3_chart",
        ):
            if hasattr(raw_chart_bundle, key):
                chart_bundle[key] = getattr(raw_chart_bundle, key)

    filters_applied = dict(getattr(payload, "filters_applied", {}) or {})
    filter_options = _normalize_bi_filter_options(
        getattr(payload, "filter_options", {}) or {}
    )

    overview_cards = _build_overview_cards(payload)
    dimension_rows = _build_dimension_rows_from_payload(payload)
    area_rows = _build_area_rows_from_payload(payload)

    dimension_lookup = _build_dimension_lookup_from_payload(payload)

    ranking_top = _build_ranking_rows(
        getattr(payload, "top5_frequency", []) or [],
        dimension_lookup=dimension_lookup,
    )
    ranking_bottom = _build_ranking_rows(
        getattr(payload, "bottom3_frequency", []) or [],
        dimension_lookup=dimension_lookup,
    )

    radar_chart = _extract_chart_dict(chart_bundle, "radar_area_chart", "Radar por área")
    status_chart = _extract_chart_dict(chart_bundle, "status_pie_chart", "Distribuição por status")
    top5_chart = _extract_chart_dict(chart_bundle, "top5_chart", "Top 5")
    bottom3_chart = _extract_chart_dict(chart_bundle, "bottom3_chart", "Bottom 3")

    filters = {
        "cliente_id": filters_applied.get("cliente_id") or "",
        "rodada_id": filters_applied.get("rodada_id") or "",
        "setor_id": filters_applied.get("setor_id") or "",
        "cargo": filters_applied.get("cargo") or "",
        "tipo_aplicacao": filters_applied.get("tipo_aplicacao") or "",
        "status": filters_applied.get("attempt_status") or "",
        "only_completed": bool(filters_applied.get("only_completed", False)),
    }

    participants_href = _build_contextual_participants_url(
        cliente_id=filters["cliente_id"],
        rodada_id=filters["rodada_id"],
        setor_id=filters["setor_id"],
        cargo=filters["cargo"],
        tipo_aplicacao=filters["tipo_aplicacao"],
        status=filters["status"],
    )

    comparativo_href = _build_contextual_comparativo_url(
        cliente_id=filters["cliente_id"],
        rodada_id=filters["rodada_id"],
    )

    context = {
        "page_title": page_title,
        "page_subtitle": page_subtitle,
        "filters": filters,
        "filter_options": filter_options,
        "overview_cards": overview_cards,
        "dimension_rows": dimension_rows,
        "area_rows": area_rows,
        "ranking_top": ranking_top,
        "ranking_bottom": ranking_bottom,
        "chart_bundle": chart_bundle,
        "radar_chart": radar_chart,
        "status_chart": status_chart,
        "top5_chart": top5_chart,
        "bottom3_chart": bottom3_chart,
        "service_payload": payload,
        "bi_meta": getattr(payload, "meta", {}) or {},
        "participants_href": participants_href,
        "comparativo_href": comparativo_href,
    }

    if cliente is not None:
        context["cliente"] = cliente

    return context


def _build_bi_comparativo_template_context(
    *,
    request: Request,
    csrf_token: str,
    comparison_title: str,
    comparison_filters: dict[str, Any],
    filter_options: dict[str, Any],
    left_payload,
    right_payload,
) -> dict[str, Any]:
    left_context = _build_bi_template_context_from_payload(
        left_payload,
        page_title="Lado A",
        page_subtitle="Recorte analítico A.",
    )
    right_context = _build_bi_template_context_from_payload(
        right_payload,
        page_title="Lado B",
        page_subtitle="Recorte analítico B.",
    )

    comparison_dimension_rows = build_bi_comparison_dimension_table(
        left_payload,
        right_payload,
    )

    return {
        "request": request,
        "csrf_token": csrf_token,
        "comparison_title": comparison_title,
        "filters": comparison_filters,
        "filter_options": filter_options,
        "left_context": left_context,
        "right_context": right_context,
        "left_overview_cards": left_context.get("overview_cards", []),
        "right_overview_cards": right_context.get("overview_cards", []),
        "left_dimension_rows": left_context.get("dimension_rows", []),
        "right_dimension_rows": right_context.get("dimension_rows", []),
        "left_area_rows": left_context.get("area_rows", []),
        "right_area_rows": right_context.get("area_rows", []),
        "left_ranking_top": left_context.get("ranking_top", []),
        "right_ranking_top": right_context.get("ranking_top", []),
        "left_ranking_bottom": left_context.get("ranking_bottom", []),
        "right_ranking_bottom": right_context.get("ranking_bottom", []),
        "left_chart_bundle": left_context.get("chart_bundle", {}),
        "right_chart_bundle": right_context.get("chart_bundle", {}),
        "left_radar_chart": left_context.get("radar_chart", {}),
        "right_radar_chart": right_context.get("radar_chart", {}),
        "left_status_chart": left_context.get("status_chart", {}),
        "right_status_chart": right_context.get("status_chart", {}),
        "left_top5_chart": left_context.get("top5_chart", {}),
        "right_top5_chart": right_context.get("top5_chart", {}),
        "left_bottom3_chart": left_context.get("bottom3_chart", {}),
        "right_bottom3_chart": right_context.get("bottom3_chart", {}),
        "comparison_dimension_rows": comparison_dimension_rows,
    }


def _normalize_attempt_status_label(value: str | None) -> str:
    raw = str(value or "").strip().lower()

    if raw in {"submitted", "finalizado", "completed", "complete"}:
        return "Finalizado"
    if raw in {"in_progress", "em_andamento", "andamento"}:
        return "Em andamento"
    if raw in {"pending", "pendente"}:
        return "Pendente"
    if raw in {"cancelled", "cancelado"}:
        return "Cancelado"

    return str(value or "Não informado").strip() or "Não informado"


def _normalize_tipo_aplicacao_label(value: str | None) -> str:
    raw = str(value or "").strip().lower()

    if raw == "empresa":
        return "Empresa"
    if raw == "pessoal":
        return "Pessoal"

    return str(value or "Não informado").strip() or "Não informado"


def _normalize_invite_status_label(value: str | None) -> str:
    raw = str(value or "").strip().lower()

    if raw == "pending":
        return "Pendente"
    if raw == "opened":
        return "Aberto"
    if raw == "completed":
        return "Concluído"
    if raw == "cancelled":
        return "Cancelado"
    if raw == "expired":
        return "Expirado"
    if raw == "used":
        return "Utilizado"

    return str(value or "Não informado").strip() or "Não informado"


def _format_datetime_label(value: Any) -> str:
    if value is None:
        return "Não informado"

    if isinstance(value, datetime):
        try:
            return value.strftime("%d/%m/%Y %H:%M")
        except Exception:
            return str(value)

    if isinstance(value, date):
        try:
            return value.strftime("%d/%m/%Y")
        except Exception:
            return str(value)

    return str(value)


def _extract_first_sentence(text: str | None) -> str:
    raw = str(text or "").strip()
    if not raw:
        return "Sem descrição disponível."

    normalized = " ".join(raw.split())
    for sep in (". ", ".\n", ";\n", "; ", "\n"):
        if sep in normalized:
            first = normalized.split(sep, 1)[0].strip()
            if first:
                if first.endswith("."):
                    return first
                return f"{first}."
    return normalized


def _normalize_band_key_label(value: Any) -> str:
    raw = str(value or "").strip().lower()

    if raw in {"baixa", "baixo", "low"}:
        return "Baixa"
    if raw in {"media", "média", "medio", "médio", "mid", "medium"}:
        return "Média"
    if raw in {"alta", "alto", "high"}:
        return "Alta"

    return str(value or "Não informada").strip() or "Não informada"


def _build_individual_ranking_item(
    letter: str,
    *,
    computed_result: ComputedResult | None,
) -> dict[str, Any]:
    safe_letter = str(letter or "").strip().upper()
    interpretations = (
        computed_result.interpretations
        if computed_result is not None and isinstance(computed_result.interpretations, dict)
        else {}
    )
    scores = (
        computed_result.scores
        if computed_result is not None and isinstance(computed_result.scores, dict)
        else {}
    )
    bands = (
        computed_result.bands
        if computed_result is not None and isinstance(computed_result.bands, dict)
        else {}
    )

    interp = interpretations.get(safe_letter, {}) if isinstance(interpretations, dict) else {}
    if not isinstance(interp, dict):
        interp = {}

    name = str(
        interp.get("name")
        or interp.get("label")
        or interp.get("title")
        or safe_letter
        or "-"
    ).strip()

    area = str(
        interp.get("area")
        or interp.get("macroarea")
        or "Não informada"
    ).strip() or "Não informada"

    raw_text = str(
        interp.get("text")
        or interp.get("description")
        or interp.get("meaning")
        or ""
    ).strip()

    summary_text = _extract_first_sentence(raw_text)

    raw_score = scores.get(safe_letter, interp.get("score", 0))
    score = _safe_int(raw_score, default=0)
    if score < 0:
        score = 0
    if score > 10:
        score = 10

    band_raw = bands.get(safe_letter, interp.get("band_key") or interp.get("band"))
    band_label = _normalize_band_key_label(band_raw)

    percentage = float(score * 10)
    if percentage < 0:
        percentage = 0.0
    if percentage > 100:
        percentage = 100.0

    return {
        "letter": safe_letter,
        "name": name,
        "display_name": f"{safe_letter} — {name}" if safe_letter and name else name or safe_letter or "-",
        "area": area,
        "score": score,
        "score_label": str(score),
        "percentage": percentage,
        "percentage_label": f"{percentage:.0f}%",
        "band": band_label,
        "description": raw_text or "Sem descrição disponível.",
        "summary": summary_text,
    }


def _build_individual_rankings_payload(
    computed_result: ComputedResult | None,
) -> dict[str, list[dict[str, Any]]]:
    rankings = _build_rankings(computed_result)

    return {
        "top3": [
            _build_individual_ranking_item(letter, computed_result=computed_result)
            for letter in rankings["top3"]
        ],
        "top5": [
            _build_individual_ranking_item(letter, computed_result=computed_result)
            for letter in rankings["top5"]
        ],
        "bottom3": [
            _build_individual_ranking_item(letter, computed_result=computed_result)
            for letter in rankings["bottom3"]
        ],
    }


def _build_participant_managerial_context(
    *,
    attempt: Attempt,
    participant: Participant | None,
    cliente: Any | None,
    rodada: Any | None,
    setor: Any | None,
) -> dict[str, Any]:
    participant_name = "Não informado"
    participant_email = "Não informado"
    participant_empresa = "Não informado"

    if participant is not None:
        nome = str(getattr(participant, "nome", "") or "").strip()
        sobrenome = str(getattr(participant, "sobrenome", "") or "").strip()
        participant_name = f"{nome} {sobrenome}".strip() or nome or "Não informado"
        participant_email = str(getattr(participant, "email", "") or "").strip() or "Não informado"
        participant_empresa = str(getattr(participant, "empresa_nome", "") or "").strip() or "Não informado"

    attempt_status_label = _normalize_attempt_status_label(getattr(attempt, "status", None))
    attempt_progress = _safe_int(getattr(attempt, "progress", 0), default=0)
    tipo_aplicacao_label = _normalize_tipo_aplicacao_label(_get_attempt_tipo_aplicacao(attempt))

    cliente_name = str(getattr(cliente, "nome", None) or "Não informado")
    rodada_name = str(getattr(rodada, "nome", None) or "Não informado")
    setor_name = str(getattr(setor, "nome", None) or "Não informado")
    cargo_name = str(getattr(attempt, "cargo", None) or "Não informado")

    data_inicio_label = _format_datetime_label(getattr(attempt, "data_inicio", None))
    data_conclusao_label = _format_datetime_label(getattr(attempt, "data_conclusao", None))

    return {
        "participant_name": participant_name,
        "participant_email": participant_email,
        "participant_empresa": participant_empresa,
        "tipo_aplicacao_label": tipo_aplicacao_label,
        "status_label": attempt_status_label,
        "progress_value": attempt_progress,
        "progress_label": f"{attempt_progress}%",
        "cargo_label": cargo_name,
        "cliente_label": cliente_name,
        "rodada_label": rodada_name,
        "setor_label": setor_name,
        "data_inicio_label": data_inicio_label,
        "data_conclusao_label": data_conclusao_label,
        "is_completed": _normalize_text_key(getattr(attempt, "status", None)) == "submitted",
    }


def _build_token_traceability_payload(
    *,
    attempt: Attempt,
    invite: Any | None,
) -> dict[str, Any]:
    attempt_id = str(getattr(attempt, "id", "") or "")
    invite_id = getattr(attempt, "invite_id", None)
    has_invite_link = invite_id is not None

    if not has_invite_link:
        return {
            "has_invite_link": False,
            "token_ok": False,
            "token_status_label": "Sem convite vinculado",
            "token_status_tone": "neutral",
            "invite_status_label": "Não aplicável",
            "opened_at_label": "Não aplicável",
            "traceability_note": (
                "Esta avaliação não possui vínculo com convite administrativo. "
                "Não há conferência de token de convite para exibir nesta tela."
            ),
        }

    if invite is None:
        return {
            "has_invite_link": True,
            "token_ok": False,
            "token_status_label": "Convite não localizado",
            "token_status_tone": "danger",
            "invite_status_label": "Indisponível",
            "opened_at_label": "Não informado",
            "traceability_note": (
                "Existe referência de convite nesta avaliação, mas o registro correspondente não foi localizado."
            ),
        }

    attempt_token_hash = str(getattr(attempt, "token_hash", "") or "").strip()
    invite_token_hash = str(getattr(invite, "token_hash", "") or "").strip()
    invite_attempt_id = str(getattr(invite, "attempt_id", "") or "").strip()

    token_hash_match = bool(attempt_token_hash and invite_token_hash and attempt_token_hash == invite_token_hash)
    invite_attempt_match = bool(invite_attempt_id and invite_attempt_id == attempt_id)

    token_ok = token_hash_match and invite_attempt_match

    if token_ok:
        token_status_label = "Token OK"
        token_status_tone = "success"
        traceability_note = (
            "A avaliação está coerente com o convite utilizado. "
            "O vínculo técnico confirma que o token usado pelo participante corresponde ao convite emitido."
        )
    elif token_hash_match and not invite_attempt_match:
        token_status_label = "Vínculo do convite divergente"
        token_status_tone = "warning"
        traceability_note = (
            "O hash do token confere, mas o vínculo do convite com a avaliação não está consistente."
        )
    elif not token_hash_match:
        token_status_label = "Divergência de token"
        token_status_tone = "danger"
        traceability_note = (
            "O token associado à avaliação não confere com o token hash do convite vinculado."
        )
    else:
        token_status_label = "Rastreabilidade pendente"
        token_status_tone = "warning"
        traceability_note = (
            "Ainda não foi possível confirmar a coerência completa entre convite e avaliação."
        )

    return {
        "has_invite_link": True,
        "token_ok": token_ok,
        "token_status_label": token_status_label,
        "token_status_tone": token_status_tone,
        "invite_status_label": _normalize_invite_status_label(getattr(invite, "status", None)),
        "opened_at_label": _format_datetime_label(getattr(invite, "usado_em", None)),
        "traceability_note": traceability_note,
    }


def _build_delivery_status_payload(
    *,
    attempt: Attempt,
    report_snapshot: ReportSnapshot | None,
    pdf_path: str | None,
) -> dict[str, Any]:
    is_completed = _normalize_text_key(getattr(attempt, "status", None)) == "submitted"
    has_pdf = bool(pdf_path and Path(pdf_path).exists())
    has_snapshot = report_snapshot is not None

    return {
        "is_completed": is_completed,
        "completion_label": "Finalizado" if is_completed else _normalize_attempt_status_label(getattr(attempt, "status", None)),
        "snapshot_label": "Disponível" if has_snapshot else "Indisponível",
        "pdf_label": "Disponível" if has_pdf else "Indisponível",
        "has_pdf": has_pdf,
        "has_snapshot": has_snapshot,
    }


def _attempt_matches_admin_participants_filters(
    attempt: Attempt,
    *,
    cargo: str | None,
    tipo_aplicacao: str | None,
    status: str | None,
) -> bool:
    cargo_filter = _clean_optional_text(cargo)
    tipo_filter = _clean_optional_text(tipo_aplicacao)
    status_filter = _clean_optional_text(status)

    attempt_cargo = _clean_optional_text(getattr(attempt, "cargo", None))
    attempt_tipo = _get_attempt_tipo_aplicacao(attempt)
    attempt_status = _clean_optional_text(getattr(attempt, "status", None))

    if cargo_filter and _normalize_text_key(attempt_cargo) != _normalize_text_key(cargo_filter):
        return False

    if tipo_filter and _normalize_text_key(attempt_tipo) != _normalize_text_key(tipo_filter):
        return False

    if status_filter and _normalize_text_key(attempt_status) != _normalize_text_key(status_filter):
        return False

    return True


def _build_admin_participant_row(
    attempt: Attempt,
    *,
    cliente: Any,
    rodada: Any | None,
    setor_lookup: dict[str, str],
    resolved_cliente_id: str,
    resolved_rodada_id: str,
) -> dict[str, str]:
    participant = getattr(attempt, "participant", None)

    nome = str(getattr(participant, "nome", "") or "").strip() if participant is not None else ""
    sobrenome = str(getattr(participant, "sobrenome", "") or "").strip() if participant is not None else ""

    participant_name = f"{nome} {sobrenome}".strip() or nome or "Não informado"

    setor_id = str(getattr(attempt, "setor_id", "") or "")
    setor_name = setor_lookup.get(setor_id, "Não informado")

    cliente_name = str(getattr(cliente, "nome", None) or "Não informado")
    rodada_name = str(getattr(rodada, "nome", None) or "Não informado")

    detail_url = _build_query_url(
        f"/admin/attempts/{attempt.id}",
        {
            "cliente_id": resolved_cliente_id,
            "rodada_id": resolved_rodada_id,
        },
    )

    status_label = _normalize_attempt_status_label(getattr(attempt, "status", None))
    tipo_label = _normalize_tipo_aplicacao_label(_get_attempt_tipo_aplicacao(attempt))
    cargo_label = str(getattr(attempt, "cargo", None) or "Não informado")

    return {
        "attempt_id": str(getattr(attempt, "id", "") or ""),
        "participant_id": str(getattr(participant, "id", "") or "") if participant is not None else "",
        "participant_name": participant_name,
        "participant": participant_name,
        "setor_name": setor_name,
        "setor": setor_name,
        "cliente_name": cliente_name,
        "cliente": cliente_name,
        "rodada_name": rodada_name,
        "rodada": rodada_name,
        "status": status_label,
        "tipo_aplicacao": tipo_label,
        "cargo": cargo_label,
        "detail_url": detail_url,
        "report_url": detail_url,
    }


async def _get_attempt_with_participant(
    db: AsyncSession,
    attempt_id: str,
) -> Attempt | None:
    attempt_uuid = _safe_uuid(attempt_id)
    if not attempt_uuid:
        return None

    res = await db.execute(
        select(Attempt)
        .options(selectinload(Attempt.participant))
        .where(Attempt.id == attempt_uuid)
    )
    return res.scalar_one_or_none()


async def _get_computed_result_by_attempt_id(
    db: AsyncSession,
    attempt_id: str,
) -> ComputedResult | None:
    attempt_uuid = _safe_uuid(attempt_id)
    if not attempt_uuid:
        return None

    res = await db.execute(
        select(ComputedResult).where(ComputedResult.attempt_id == attempt_uuid)
    )
    return res.scalar_one_or_none()


async def _get_report_snapshot_by_attempt_id(
    db: AsyncSession,
    attempt_id: str,
) -> ReportSnapshot | None:
    attempt_uuid = _safe_uuid(attempt_id)
    if not attempt_uuid:
        return None

    res = await db.execute(
        select(ReportSnapshot).where(ReportSnapshot.attempt_id == attempt_uuid)
    )
    return res.scalar_one_or_none()


async def _resolve_cliente_rodada_for_attempt(
    db: AsyncSession,
    attempt: Attempt,
    cliente_id: str | None,
    rodada_id: str | None,
):
    resolved_cliente_id = cliente_id or _safe_str(getattr(attempt, "cliente_id", None))
    resolved_rodada_id = rodada_id or _safe_str(getattr(attempt, "rodada_id", None))

    cliente = None
    rodada = None

    if resolved_cliente_id and resolved_cliente_id != "-":
        cliente = await get_cliente_by_id(db, _safe_uuid(resolved_cliente_id) or resolved_cliente_id)
        if cliente:
            rodadas = await list_rodadas_by_cliente(db, cliente.id)
            rodada = next(
                (r for r in rodadas if str(r.id) == str(resolved_rodada_id)),
                None,
            )

    return cliente, rodada, resolved_cliente_id, resolved_rodada_id


def _build_rankings(computed_result: ComputedResult | None) -> dict[str, list[str]]:
    if not computed_result:
        return {"top3": [], "top5": [], "bottom3": []}

    top3 = (computed_result.top3 or {}).get("top3", [])
    top5 = (computed_result.top5 or {}).get("top5", [])
    bottom3 = (computed_result.bottom3 or {}).get("bottom3", [])

    return {
        "top3": [str(x) for x in top3 if str(x).strip()],
        "top5": [str(x) for x in top5 if str(x).strip()],
        "bottom3": [str(x) for x in bottom3 if str(x).strip()],
    }


async def _load_all_attempts(
    session: AsyncSession,
    *,
    cliente_id: str | None = None,
    rodada_id: str | None = None,
    setor_id: str | None = None,
    limit: int = 5000,
) -> list[Attempt]:
    q = (
        select(Attempt)
        .options(selectinload(Attempt.participant))
        .order_by(Attempt.data_inicio.desc())
        .limit(limit)
    )

    if cliente_id:
        q = q.where(Attempt.cliente_id == (_safe_uuid(cliente_id) or cliente_id))
    if rodada_id:
        q = q.where(Attempt.rodada_id == (_safe_uuid(rodada_id) or rodada_id))
    if setor_id:
        q = q.where(Attempt.setor_id == (_safe_uuid(setor_id) or setor_id))

    res = await session.execute(q)
    return list(res.scalars().all())


async def _build_export_rows(
    session: AsyncSession,
    *,
    cliente_id: str | None = None,
    rodada_id: str | None = None,
    setor_id: str | None = None,
) -> list[dict[str, str]]:
    attempts = await _load_all_attempts(
        session,
        cliente_id=cliente_id,
        rodada_id=rodada_id,
        setor_id=setor_id,
    )

    rows: list[dict[str, str]] = []
    for attempt in attempts:
        participant: Participant | None = getattr(attempt, "participant", None)
        snapshot = await _get_report_snapshot_by_attempt_id(session, str(attempt.id))

        rows.append(
            {
                "attempt_id": _safe_str(attempt.id),
                "status": _safe_str(attempt.status),
                "progress": _safe_str(attempt.progress),
                "data_inicio": _safe_str(attempt.data_inicio),
                "data_conclusao": _safe_str(attempt.data_conclusao),
                "participant_nome": _safe_str(getattr(participant, "nome", "") or ""),
                "participant_sobrenome": _safe_str(getattr(participant, "sobrenome", "") or ""),
                "participant_email": _safe_str(getattr(participant, "email", "") or ""),
                "empresa_nome": _safe_str(getattr(participant, "empresa_nome", "") or ""),
                "tipo_aplicacao": _safe_str(_get_attempt_tipo_aplicacao(attempt) or ""),
                "cargo": _safe_str(getattr(attempt, "cargo", "") or ""),
                "cliente_id": _safe_str(attempt.cliente_id),
                "rodada_id": _safe_str(attempt.rodada_id),
                "setor_id": _safe_str(attempt.setor_id),
                "pdf_disponivel": _bool_label(bool(snapshot and getattr(snapshot, "pdf_path", None))),
            }
        )

    return rows


def _build_csv_bytes(rows: list[dict[str, str]]) -> bytes:
    headers = [
        "attempt_id",
        "status",
        "progress",
        "data_inicio",
        "data_conclusao",
        "participant_nome",
        "participant_sobrenome",
        "participant_email",
        "empresa_nome",
        "tipo_aplicacao",
        "cargo",
        "cliente_id",
        "rodada_id",
        "setor_id",
        "pdf_disponivel",
    ]

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def _xlsx_column_name(index: int) -> str:
    result = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _build_xlsx_bytes(rows: list[dict[str, str]]) -> bytes:
    headers = [
        "attempt_id",
        "status",
        "progress",
        "data_inicio",
        "data_conclusao",
        "participant_nome",
        "participant_sobrenome",
        "participant_email",
        "empresa_nome",
        "tipo_aplicacao",
        "cargo",
        "cliente_id",
        "rodada_id",
        "setor_id",
        "pdf_disponivel",
    ]

    all_rows: list[list[str]] = [headers]
    for row in rows:
        all_rows.append([_safe_str(row.get(header, "")) for header in headers])

    sheet_rows: list[str] = []
    for row_idx, row in enumerate(all_rows, start=1):
        cells: list[str] = []
        for col_idx, value in enumerate(row, start=1):
            cell_ref = f"{_xlsx_column_name(col_idx)}{row_idx}"
            escaped = xml_escape(_safe_str(value))
            cells.append(f'<c r="{cell_ref}" t="inlineStr"><is><t>{escaped}</t></is></c>')
        sheet_rows.append(f'<row r="{row_idx}">{"".join(cells)}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        f'{"".join(sheet_rows)}'
        "</sheetData>"
        "</worksheet>"
    )

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        '<sheet name="attempts" sheetId="1" r:id="rId1"/>'
        "</sheets>"
        "</workbook>"
    )

    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )

    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )

    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )

    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", root_rels_xml)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)

    return buffer.getvalue()


async def get_current_admin(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    token = request.cookies.get(ACCESS_COOKIE_NAME)
    if not token:
        return _redirect_login()

    admin_id = decode_access_token(token)
    if not admin_id:
        return _redirect_login()

    admin = await get_admin_by_id(db, admin_id)
    if not admin or not admin.ativo:
        return _redirect_login()

    return admin


@router.get("/login", response_class=HTMLResponse)
async def admin_login_get(request: Request):
    return templates.TemplateResponse(
        "admin/login.html",
        {"request": request, "error": None},
    )


@router.post("/login")
async def admin_login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    admin = await get_admin_by_username(db, username)

    if not admin or not verify_password(password, admin.password_hash) or not admin.ativo:
        return templates.TemplateResponse(
            "admin/login.html",
            {"request": request, "error": "Credenciais inválidas."},
            status_code=401,
        )

    token = create_access_token(subject=str(admin.id))
    csrf = new_csrf_token()

    resp = RedirectResponse(url="/admin/dashboard", status_code=303)

    resp.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/admin",
    )
    resp.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf,
        httponly=False,
        secure=True,
        samesite="lax",
        path="/admin",
    )

    return resp


@router.get("/logout")
async def admin_logout():
    resp = RedirectResponse(url="/admin/login", status_code=303)
    resp.delete_cookie(key=ACCESS_COOKIE_NAME, path="/admin")
    resp.delete_cookie(key=CSRF_COOKIE_NAME, path="/admin")
    return resp


@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    q: str | None = Query(None),
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return admin

    clientes = await list_clientes(db)

    query = str(q or "").strip().lower()
    if query:
        clientes = [c for c in clientes if query in str(getattr(c, "nome", "") or "").lower()]

    total_clientes = len(clientes)
    total_ativos = sum(1 for c in clientes if bool(getattr(c, "ativo", False)))

    try:
        _bi_filters = _build_bi_service_filters()
        _bi_payload = await build_bi_service_payload(db, filters=_bi_filters)
        bi_setor_distribution = _bi_payload.setor_distribution or []
        bi_top5_frequency = _bi_payload.top5_frequency or []
    except Exception:
        bi_setor_distribution = []
        bi_top5_frequency = []

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "clientes": clientes,
            "q": q or "",
            "total_clientes": total_clientes,
            "total_ativos": total_ativos,
            "csrf_token": request.cookies.get(CSRF_COOKIE_NAME),
            "setor_distribution": bi_setor_distribution,
            "top5_frequency": bi_top5_frequency,
        },
    )


@router.get("/bi/overview", response_class=HTMLResponse)
async def admin_bi_overview(
    request: Request,
    cliente_id: str | None = Query(None),
    rodada_id: str | None = Query(None),
    setor_id: str | None = Query(None),
    cargo: str | None = Query(None),
    tipo_aplicacao: str | None = Query(None),
    status: str | None = Query(None),
    only_completed: bool = Query(False),
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return admin

    filters = _build_bi_service_filters(
        cliente_id=cliente_id,
        rodada_id=rodada_id,
        setor_id=setor_id,
        cargo=cargo,
        tipo_aplicacao=tipo_aplicacao,
        status=status,
        only_completed=only_completed,
    )

    payload = await build_bi_service_payload(db, filters=filters)
    context = _build_bi_template_context_from_payload(
        payload,
        page_title="BI — Visão Geral",
        page_subtitle="Painel analítico consolidado do ProfileDNA com filtros operacionais, visão executiva e apoio à interpretação.",
        cliente=None,
    )

    scoped_filter_options, cliente = await _build_bi_filter_options_for_route(
        db,
        base_filter_options=context.get("filter_options", {}),
        cliente_id=cliente_id,
        rodada_id=rodada_id,
        setor_id=setor_id,
    )

    context["filter_options"] = scoped_filter_options
    if cliente is not None:
        context["cliente"] = cliente

    return templates.TemplateResponse(
        "admin/bi_overview.html",
        {
            "request": request,
            "csrf_token": request.cookies.get(CSRF_COOKIE_NAME),
            **context,
        },
    )


@router.get("/bi/cliente/{cliente_id}", response_class=HTMLResponse)
async def admin_bi_cliente(
    request: Request,
    cliente_id: str,
    rodada_id: str | None = Query(None),
    setor_id: str | None = Query(None),
    cargo: str | None = Query(None),
    tipo_aplicacao: str | None = Query(None),
    status: str | None = Query(None),
    only_completed: bool = Query(False),
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return admin

    cliente_pk = _safe_uuid(cliente_id) or cliente_id
    cliente = await get_cliente_by_id(db, cliente_pk)
    if not cliente:
        return _redirect_dashboard()

    filters = _build_bi_service_filters(
        cliente_id=str(cliente.id),
        rodada_id=rodada_id,
        setor_id=setor_id,
        cargo=cargo,
        tipo_aplicacao=tipo_aplicacao,
        status=status,
        only_completed=only_completed,
    )

    payload = await build_bi_service_payload(db, filters=filters)
    context = _build_bi_template_context_from_payload(
        payload,
        page_title="BI — Cliente",
        page_subtitle=f"Painel analítico consolidado do cliente {cliente.nome}.",
        cliente=cliente,
    )

    context["filter_options"] = _normalize_bi_filter_options(
        await _build_cliente_scoped_filter_options(
            db,
            cliente=cliente,
            selected_rodada_id=_clean_optional_text(rodada_id),
            selected_setor_id=_clean_optional_text(setor_id),
        )
    )

    return templates.TemplateResponse(
        "admin/bi_overview.html",
        {
            "request": request,
            "csrf_token": request.cookies.get(CSRF_COOKIE_NAME),
            **context,
        },
    )


@router.get("/bi/comparativo", response_class=HTMLResponse)
async def admin_bi_comparativo(
    request: Request,
    left_cliente_id: str | None = Query(None),
    left_rodada_id: str | None = Query(None),
    left_setor_id: str | None = Query(None),
    left_cargo: str | None = Query(None),
    left_tipo_aplicacao: str | None = Query(None),
    left_status: str | None = Query(None),
    left_only_completed: bool = Query(False),
    right_cliente_id: str | None = Query(None),
    right_rodada_id: str | None = Query(None),
    right_setor_id: str | None = Query(None),
    right_cargo: str | None = Query(None),
    right_tipo_aplicacao: str | None = Query(None),
    right_status: str | None = Query(None),
    right_only_completed: bool = Query(False),
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return admin

    left_cliente_id_clean = _clean_optional_text(left_cliente_id)
    right_cliente_id_clean = _clean_optional_text(right_cliente_id)

    if left_cliente_id_clean and not right_cliente_id_clean:
        right_cliente_id_clean = left_cliente_id_clean

    if left_cliente_id_clean and not _clean_optional_text(right_rodada_id):
        cliente_pk = _safe_uuid(left_cliente_id_clean) or left_cliente_id_clean
        same_cliente = await get_cliente_by_id(db, cliente_pk)
        if same_cliente is not None:
            same_cliente_rodadas = await list_rodadas_by_cliente(db, same_cliente.id)
            clean_left_rodada_id = _clean_optional_text(left_rodada_id)
            fallback_right = next(
                (
                    str(item.id)
                    for item in same_cliente_rodadas
                    if str(item.id) != str(clean_left_rodada_id or "")
                ),
                None,
            )
            if fallback_right:
                right_rodada_id = fallback_right
            elif clean_left_rodada_id:
                right_rodada_id = clean_left_rodada_id

    left_filters = _build_bi_service_filters(
        cliente_id=left_cliente_id_clean,
        rodada_id=left_rodada_id,
        setor_id=left_setor_id,
        cargo=left_cargo,
        tipo_aplicacao=left_tipo_aplicacao,
        status=left_status,
        only_completed=left_only_completed,
    )
    right_filters = _build_bi_service_filters(
        cliente_id=right_cliente_id_clean,
        rodada_id=right_rodada_id,
        setor_id=right_setor_id,
        cargo=right_cargo,
        tipo_aplicacao=right_tipo_aplicacao,
        status=right_status,
        only_completed=right_only_completed,
    )

    left_payload = await build_bi_service_payload(db, filters=left_filters)
    right_payload = await build_bi_service_payload(db, filters=right_filters)

    left_context = _build_bi_template_context_from_payload(
        left_payload,
        page_title="Lado A",
        page_subtitle="Recorte analítico A.",
    )
    right_context = _build_bi_template_context_from_payload(
        right_payload,
        page_title="Lado B",
        page_subtitle="Recorte analítico B.",
    )

    filter_options = left_context.get("filter_options") or right_context.get("filter_options") or {}

    if left_cliente_id_clean:
        cliente_pk = _safe_uuid(left_cliente_id_clean) or left_cliente_id_clean
        cliente = await get_cliente_by_id(db, cliente_pk)
        if cliente is not None:
            filter_options = _normalize_bi_filter_options(
                await _build_cliente_scoped_filter_options(
                    db,
                    cliente=cliente,
                    selected_rodada_id=None,
                    selected_setor_id=None,
                )
            )

    comparison_filters = {
        "left_cliente_id": left_cliente_id_clean or "",
        "left_rodada_id": _clean_optional_text(left_rodada_id) or "",
        "left_setor_id": _clean_optional_text(left_setor_id) or "",
        "left_cargo": _clean_optional_text(left_cargo) or "",
        "left_tipo_aplicacao": _clean_optional_text(left_tipo_aplicacao) or "",
        "left_status": _clean_optional_text(left_status) or "",
        "left_only_completed": bool(left_only_completed),
        "right_cliente_id": right_cliente_id_clean or "",
        "right_rodada_id": _clean_optional_text(right_rodada_id) or "",
        "right_setor_id": _clean_optional_text(right_setor_id) or "",
        "right_cargo": _clean_optional_text(right_cargo) or "",
        "right_tipo_aplicacao": _clean_optional_text(right_tipo_aplicacao) or "",
        "right_status": _clean_optional_text(right_status) or "",
        "right_only_completed": bool(right_only_completed),
    }

    context = _build_bi_comparativo_template_context(
        request=request,
        csrf_token=request.cookies.get(CSRF_COOKIE_NAME),
        comparison_title="BI — Comparativo",
        comparison_filters=comparison_filters,
        filter_options=filter_options,
        left_payload=left_payload,
        right_payload=right_payload,
    )

    return templates.TemplateResponse(
        "admin/bi_comparativo.html",
        context,
    )


@router.get("/participants", response_class=HTMLResponse)
async def admin_participants(
    request: Request,
    cliente_id: str = Query(...),
    rodada_id: str | None = Query(None),
    setor_id: str | None = Query(None),
    cargo: str | None = Query(None),
    tipo_aplicacao: str | None = Query(None),
    status: str | None = Query(None),
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return admin

    cliente_pk = _safe_uuid(cliente_id) or cliente_id
    cliente = await get_cliente_by_id(db, cliente_pk)
    if not cliente:
        return _redirect_dashboard()

    rodadas = await list_rodadas_by_cliente(db, cliente.id)
    setores = await list_setores_by_cliente(db, cliente.id)

    selected_rodada = None
    if _clean_optional_text(rodada_id):
        rodada_pk = _safe_uuid(rodada_id) or rodada_id
        possible_rodada = await get_rodada_by_id(db, rodada_pk)
        if possible_rodada and str(getattr(possible_rodada, "cliente_id", "")) == str(cliente.id):
            selected_rodada = possible_rodada

    selected_setor_id = _clean_optional_text(setor_id)
    selected_cargo = _clean_optional_text(cargo)
    selected_tipo_aplicacao = _clean_optional_text(tipo_aplicacao)
    selected_status = _clean_optional_text(status)

    attempts = await _load_all_attempts(
        db,
        cliente_id=str(cliente.id),
        rodada_id=str(getattr(selected_rodada, "id", "") or "") if selected_rodada else None,
        setor_id=selected_setor_id,
        limit=5000,
    )

    attempts = [
        attempt
        for attempt in attempts
        if _attempt_matches_admin_participants_filters(
            attempt,
            cargo=selected_cargo,
            tipo_aplicacao=selected_tipo_aplicacao,
            status=selected_status,
        )
    ]

    rodadas_lookup = {str(item.id): item for item in rodadas}
    setores_lookup = {str(item.id): str(item.nome) for item in setores}

    participants_rows = []
    for attempt in attempts:
        attempt_rodada = rodadas_lookup.get(str(getattr(attempt, "rodada_id", "") or ""))
        resolved_rodada_id = str(getattr(attempt_rodada, "id", "") or "")
        participants_rows.append(
            _build_admin_participant_row(
                attempt,
                cliente=cliente,
                rodada=attempt_rodada,
                setor_lookup=setores_lookup,
                resolved_cliente_id=str(cliente.id),
                resolved_rodada_id=resolved_rodada_id,
            )
        )

    participants_rows.sort(
        key=lambda row: (
            str(row.get("participant_name", "")).lower(),
            str(row.get("rodada_name", "")).lower(),
        )
    )

    attempts_for_options = await _load_all_attempts(
        db,
        cliente_id=str(cliente.id),
        rodada_id=str(getattr(selected_rodada, "id", "") or "") if selected_rodada else None,
        setor_id=selected_setor_id,
        limit=5000,
    )

    cargo_options, tipo_options, status_options = _build_distinct_attempt_values(attempts_for_options)

    filters = {
        "cliente_id": str(cliente.id),
        "rodada_id": str(getattr(selected_rodada, "id", "") or ""),
        "setor_id": selected_setor_id or "",
        "cargo": selected_cargo or "",
        "tipo_aplicacao": selected_tipo_aplicacao or "",
        "status": selected_status or "",
    }

    filter_options = {
        "rodadas": [{"id": str(item.id), "nome": item.nome} for item in rodadas],
        "setores": [{"id": str(item.id), "nome": item.nome} for item in setores],
        "cargos": cargo_options,
        "tipos_aplicacao": tipo_options,
        "statuses": status_options,
    }

    participants_bi_url = _build_contextual_bi_overview_url(
        cliente_id=str(cliente.id),
        rodada_id=str(getattr(selected_rodada, "id", "") or ""),
        setor_id=selected_setor_id,
        cargo=selected_cargo,
        tipo_aplicacao=selected_tipo_aplicacao,
        status=selected_status,
        only_completed=None,
    )

    participants_comparativo_url = _build_contextual_comparativo_url(
        cliente_id=str(cliente.id),
        rodada_id=str(getattr(selected_rodada, "id", "") or ""),
    )

    return templates.TemplateResponse(
        "admin/participants.html",
        {
            "request": request,
            "admin": admin,
            "csrf_token": request.cookies.get(CSRF_COOKIE_NAME),
            "cliente": cliente,
            "rodada": selected_rodada,
            "filters": filters,
            "filter_options": filter_options,
            "participants": participants_rows,
            "total_participants": len(participants_rows),
            "participants_bi_url": participants_bi_url,
            "participants_comparativo_url": participants_comparativo_url,
        },
    )


@router.post("/clientes")
async def admin_create_cliente(
    request: Request,
    nome: str = Form(...),
    razao_social: str | None = Form(None),
    cnpj: str | None = Form(None),
    cep: str | None = Form(None),
    logradouro: str | None = Form(None),
    numero: str | None = Form(None),
    complemento: str | None = Form(None),
    telefone: str | None = Form(None),
    setor_mercado: str | None = Form(None),
    responsavel: str | None = Form(None),
    setor_responsavel: str | None = Form(None),
    email_responsavel: str | None = Form(None),
    ativo: str | None = Form(None),
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    allowed, response = await _require_admin_post(request, admin)
    if not allowed:
        return response

    nome_clean = str(nome or "").strip()
    if not nome_clean:
        return _build_admin_error_html("Nome do cliente é obrigatório.", status_code=422)

    endereco_composto = _compose_endereco(
        cep=_clean_optional_text(cep),
        logradouro=_clean_optional_text(logradouro),
        numero=_clean_optional_text(numero),
        complemento=_clean_optional_text(complemento),
        telefone=_clean_optional_text(telefone),
    )

    await create_cliente(
        db,
        nome=nome_clean,
        razao_social=_clean_optional_text(razao_social),
        cnpj=_clean_optional_text(cnpj),
        endereco=endereco_composto,
        setor_mercado=_clean_optional_text(setor_mercado),
        responsavel=_clean_optional_text(responsavel),
        setor_responsavel=_clean_optional_text(setor_responsavel),
        email_responsavel=_clean_optional_text(email_responsavel),
        ativo=bool(ativo),
    )
    await db.commit()

    return RedirectResponse(url="/admin/clientes", status_code=303)


@router.post("/clientes/{cliente_id}/editar")
async def admin_update_cliente(
    request: Request,
    cliente_id: str,
    nome: str = Form(...),
    razao_social: str | None = Form(None),
    cnpj: str | None = Form(None),
    endereco: str | None = Form(None),
    setor_mercado: str | None = Form(None),
    responsavel: str | None = Form(None),
    setor_responsavel: str | None = Form(None),
    email_responsavel: str | None = Form(None),
    ativo: str | None = Form(None),
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    allowed, response = await _require_admin_post(request, admin)
    if not allowed:
        return response

    cliente_pk = _safe_uuid(cliente_id) or cliente_id
    cliente = await get_cliente_by_id(db, cliente_pk)
    if not cliente:
        return _redirect_dashboard()

    nome_clean = str(nome or "").strip()
    if not nome_clean:
        return _build_admin_error_html("Nome do cliente é obrigatório.", status_code=422)

    await update_cliente(
        db,
        cliente=cliente,
        nome=nome_clean,
        razao_social=_clean_optional_text(razao_social),
        cnpj=_clean_optional_text(cnpj),
        endereco=_clean_optional_text(endereco),
        setor_mercado=_clean_optional_text(setor_mercado),
        responsavel=_clean_optional_text(responsavel),
        setor_responsavel=_clean_optional_text(setor_responsavel),
        email_responsavel=_clean_optional_text(email_responsavel),
        ativo=bool(ativo),
    )
    await db.commit()

    return RedirectResponse(url=f"/admin/clientes/{cliente.id}", status_code=303)


@router.post("/clientes/{cliente_id}/status")
async def admin_set_cliente_status(
    request: Request,
    cliente_id: str,
    ativo: str = Form(...),
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    allowed, response = await _require_admin_post(request, admin)
    if not allowed:
        return response

    cliente_pk = _safe_uuid(cliente_id) or cliente_id
    cliente = await get_cliente_by_id(db, cliente_pk)
    if not cliente:
        return _redirect_dashboard()

    ativo_bool = str(ativo).strip().lower() in {"1", "true", "on", "sim", "yes"}
    await set_cliente_ativo(db, cliente=cliente, ativo=ativo_bool)
    await db.commit()

    return RedirectResponse(url=f"/admin/clientes/{cliente.id}", status_code=303)


@router.post("/clientes/{cliente_id}/excluir")
async def admin_delete_cliente(
    request: Request,
    cliente_id: str,
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    allowed, response = await _require_admin_post(request, admin)
    if not allowed:
        return response

    cliente_pk = _safe_uuid(cliente_id) or cliente_id
    cliente = await get_cliente_by_id(db, cliente_pk)
    if not cliente:
        return _redirect_dashboard()

    deleted = await delete_cliente_if_empty(db, cliente=cliente)
    if not deleted:
        return _build_admin_error_html(
            "Não é possível excluir este cliente porque ele possui rodadas, setores, convites ou attempts vinculados.",
            status_code=409,
        )

    await db.commit()
    return _redirect_dashboard()


@router.get("/clientes", response_class=HTMLResponse)
async def admin_clientes_list(
    request: Request,
    q: str | None = Query(None),
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return admin

    clientes = await list_clientes(db)

    query = str(q or "").strip().lower()
    if query:
        clientes = [
            c for c in clientes
            if query in str(getattr(c, "nome", "") or "").lower()
            or query in str(getattr(c, "cnpj", "") or "").lower()
        ]

    total_clientes = len(clientes)
    total_ativos = sum(1 for c in clientes if bool(getattr(c, "ativo", False)))

    return templates.TemplateResponse(
        "admin/clientes.html",
        {
            "request": request,
            "clientes": clientes,
            "q": q or "",
            "total_clientes": total_clientes,
            "total_ativos": total_ativos,
            "csrf_token": request.cookies.get(CSRF_COOKIE_NAME),
        },
    )


@router.get("/clientes/novo", response_class=HTMLResponse)
async def admin_cliente_novo(
    request: Request,
    admin=Depends(get_current_admin),
):
    if isinstance(admin, RedirectResponse):
        return admin

    return templates.TemplateResponse(
        "admin/cliente_novo.html",
        {
            "request": request,
            "csrf_token": request.cookies.get(CSRF_COOKIE_NAME),
        },
    )


@router.get("/clientes/{cliente_id}", response_class=HTMLResponse)
async def admin_cliente_detail(
    request: Request,
    cliente_id: str,
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return admin

    cliente_pk = _safe_uuid(cliente_id) or cliente_id
    cliente = await get_cliente_by_id(db, cliente_pk)
    if not cliente:
        return _redirect_dashboard()

    rodadas = await list_rodadas_by_cliente(db, cliente.id)
    setores = await list_setores_by_cliente(db, cliente.id)

    attempts = await _load_all_attempts(
        db,
        cliente_id=str(cliente.id),
        rodada_id=None,
        setor_id=None,
        limit=5000,
    )

    participants_total = len(attempts)
    participants_submitted_total = sum(
        1
        for attempt in attempts
        if _normalize_text_key(getattr(attempt, "status", None)) == "submitted"
    )
    participants_in_progress_total = sum(
        1
        for attempt in attempts
        if _normalize_text_key(getattr(attempt, "status", None)) == "in_progress"
    )

    participants_url = _build_contextual_participants_url(
        cliente_id=str(cliente.id),
        rodada_id=None,
    )

    participants_by_rodada_options = [
        {
            "id": str(rodada.id),
            "nome": str(rodada.nome or "-"),
            "url": _build_contextual_participants_url(
                cliente_id=str(cliente.id),
                rodada_id=str(rodada.id),
            ),
        }
        for rodada in rodadas
    ]

    return templates.TemplateResponse(
        "admin/cliente_detail.html",
        {
            "request": request,
            "csrf_token": request.cookies.get(CSRF_COOKIE_NAME),
            "cliente": cliente,
            "rodadas": rodadas,
            "setores": setores,
            "rodadas_count": len(rodadas),
            "setores_count": len(setores),
            "participants_total": participants_total,
            "participants_submitted_total": participants_submitted_total,
            "participants_in_progress_total": participants_in_progress_total,
            "participants_url": participants_url,
            "participants_by_rodada_options": participants_by_rodada_options,
        },
    )


@router.get("/bi/cliente/{cliente_id}/data")
async def admin_bi_cliente_data(
    cliente_id: str,
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return JSONResponse({"detail": "unauthorized"}, status_code=401)

    cliente_pk = _safe_uuid(cliente_id) or cliente_id
    cliente = await get_cliente_by_id(db, cliente_pk)
    if not cliente:
        return JSONResponse({"detail": "not_found"}, status_code=404)

    filters = _build_bi_service_filters(cliente_id=str(cliente.id))
    payload = await build_bi_service_payload(db, filters=filters)

    total_attempts = int(payload.meta.get("total_attempts") or 0)

    return JSONResponse(
        {
            "has_data": total_attempts > 0,
            "total_attempts": total_attempts,
            "radar_area": payload.radar_area,
            "dimension_table": payload.dimension_table,
            "top5_frequency": payload.top5_frequency,
            "bottom3_frequency": payload.bottom3_frequency,
        }
    )


@router.post("/clientes/{cliente_id}/setores")
async def admin_create_setor(
    request: Request,
    cliente_id: str,
    nome: str = Form(...),
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    allowed, response = await _require_admin_post(request, admin)
    if not allowed:
        return response

    cliente_pk = _safe_uuid(cliente_id) or cliente_id
    cliente = await get_cliente_by_id(db, cliente_pk)
    if not cliente:
        return _redirect_dashboard()

    nome_clean = str(nome or "").strip()
    if not nome_clean:
        return _build_admin_error_html("Nome do setor é obrigatório.", status_code=422)

    await create_setor(
        db,
        cliente_id=cliente.id,
        nome=nome_clean,
    )
    await db.commit()

    return RedirectResponse(url=f"/admin/clientes/{cliente.id}", status_code=303)


@router.post("/setores/{setor_id}/editar")
async def admin_update_setor(
    request: Request,
    setor_id: str,
    cliente_id: str = Form(...),
    nome: str = Form(...),
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    allowed, response = await _require_admin_post(request, admin)
    if not allowed:
        return response

    setor_pk = _safe_uuid(setor_id) or setor_id
    setor = await get_setor_by_id(db, setor_pk)
    if not setor:
        return _redirect_dashboard()

    cliente_pk = _safe_uuid(cliente_id) or cliente_id
    cliente = await get_cliente_by_id(db, cliente_pk)
    if not cliente:
        return _redirect_dashboard()

    nome_clean = str(nome or "").strip()
    if not nome_clean:
        return _build_admin_error_html("Nome do setor é obrigatório.", status_code=422)

    await update_setor(db, setor=setor, nome=nome_clean)
    await db.commit()

    return RedirectResponse(url=f"/admin/clientes/{cliente.id}", status_code=303)


@router.post("/setores/{setor_id}/excluir")
async def admin_delete_setor(
    request: Request,
    setor_id: str,
    cliente_id: str = Form(...),
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    allowed, response = await _require_admin_post(request, admin)
    if not allowed:
        return response

    setor_pk = _safe_uuid(setor_id) or setor_id
    setor = await get_setor_by_id(db, setor_pk)
    if not setor:
        return _redirect_dashboard()

    cliente_pk = _safe_uuid(cliente_id) or cliente_id
    cliente = await get_cliente_by_id(db, cliente_pk)
    if not cliente:
        return _redirect_dashboard()

    deleted = await delete_setor_if_unused(db, setor=setor)
    if not deleted:
        return _build_admin_error_html(
            "Não é possível excluir este setor porque ele possui convites ou attempts vinculados.",
            status_code=409,
        )

    await db.commit()
    return RedirectResponse(url=f"/admin/clientes/{cliente.id}", status_code=303)


@router.post("/clientes/{cliente_id}/rodadas")
async def admin_create_rodada(
    request: Request,
    cliente_id: str,
    nome: str = Form(...),
    data_inicio: str = Form(...),
    data_encerramento: str | None = Form(None),
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    allowed, response = await _require_admin_post(request, admin)
    if not allowed:
        return response

    cliente_pk = _safe_uuid(cliente_id) or cliente_id
    cliente = await get_cliente_by_id(db, cliente_pk)
    if not cliente:
        return _redirect_dashboard()

    nome_clean = str(nome or "").strip()
    if not nome_clean:
        return _build_admin_error_html("Nome da rodada é obrigatório.", status_code=422)

    data_inicio_parsed = _parse_date_or_datetime(data_inicio)
    if data_inicio_parsed is None:
        return _build_admin_error_html(
            "Data de início inválida. Use ISO-8601 ou DD/MM/AA.",
            status_code=422,
        )

    data_encerramento_parsed = (
        _parse_date_or_datetime(data_encerramento) if data_encerramento else None
    )

    if isinstance(data_inicio_parsed, datetime):
        data_inicio_final = data_inicio_parsed.date()
    else:
        data_inicio_final = data_inicio_parsed

    if isinstance(data_encerramento_parsed, datetime):
        data_encerramento_final = data_encerramento_parsed.date()
    else:
        data_encerramento_final = data_encerramento_parsed

    await create_rodada(
        db,
        cliente_id=cliente.id,
        nome=nome_clean,
        data_inicio=data_inicio_final,
        data_encerramento=data_encerramento_final,
        criado_por=admin.id,
    )
    await db.commit()

    return RedirectResponse(url=f"/admin/clientes/{cliente.id}", status_code=303)


@router.post("/rodadas/{rodada_id}/editar")
async def admin_update_rodada(
    request: Request,
    rodada_id: str,
    cliente_id: str = Form(...),
    nome: str = Form(...),
    data_inicio: str = Form(...),
    data_encerramento: str | None = Form(None),
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    allowed, response = await _require_admin_post(request, admin)
    if not allowed:
        return response

    cliente_pk = _safe_uuid(cliente_id) or cliente_id
    cliente = await get_cliente_by_id(db, cliente_pk)
    if not cliente:
        return _redirect_dashboard()

    rodada_pk = _safe_uuid(rodada_id) or rodada_id
    rodada = await get_rodada_by_id(db, rodada_pk)
    if not rodada:
        return _redirect_dashboard()

    nome_clean = str(nome or "").strip()
    if not nome_clean:
        return _build_admin_error_html("Nome da rodada é obrigatório.", status_code=422)

    data_inicio_parsed = _parse_date_or_datetime(data_inicio)
    if data_inicio_parsed is None:
        return _build_admin_error_html(
            "Data de início inválida. Use ISO-8601 ou DD/MM/AA.",
            status_code=422,
        )

    data_encerramento_parsed = (
        _parse_date_or_datetime(data_encerramento) if data_encerramento else None
    )

    if isinstance(data_inicio_parsed, datetime):
        data_inicio_final = data_inicio_parsed.date()
    else:
        data_inicio_final = data_inicio_parsed

    if isinstance(data_encerramento_parsed, datetime):
        data_encerramento_final = data_encerramento_parsed.date()
    else:
        data_encerramento_final = data_encerramento_parsed

    await update_rodada(
        db,
        rodada=rodada,
        nome=nome_clean,
        data_inicio=data_inicio_final,
        data_encerramento=data_encerramento_final,
    )
    await db.commit()

    return RedirectResponse(url=f"/admin/clientes/{cliente.id}", status_code=303)


@router.post("/rodadas/{rodada_id}/excluir")
async def admin_delete_rodada(
    request: Request,
    rodada_id: str,
    cliente_id: str = Form(...),
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    allowed, response = await _require_admin_post(request, admin)
    if not allowed:
        return response

    cliente_pk = _safe_uuid(cliente_id) or cliente_id
    cliente = await get_cliente_by_id(db, cliente_pk)
    if not cliente:
        return _redirect_dashboard()

    rodada_pk = _safe_uuid(rodada_id) or rodada_id
    rodada = await get_rodada_by_id(db, rodada_pk)
    if not rodada:
        return _redirect_dashboard()

    deleted = await delete_rodada_if_empty(db, rodada=rodada)
    if not deleted:
        return _build_admin_error_html(
            "Não é possível excluir esta rodada porque ela possui convites ou attempts vinculados.",
            status_code=409,
        )

    await db.commit()
    return RedirectResponse(url=f"/admin/clientes/{cliente.id}", status_code=303)


@router.get("/rodadas/{rodada_id}", response_class=HTMLResponse)
async def admin_rodada_detail(
    request: Request,
    rodada_id: str,
    cliente_id: str = Query(..., description="Cliente ID (contexto)"),
    setor_id: str | None = Query(None),
    created_invite_id: str | None = Query(None),
    created_invite_path: str | None = Query(None),
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return admin

    cliente_pk = _safe_uuid(cliente_id) or cliente_id
    cliente = await get_cliente_by_id(db, cliente_pk)
    if not cliente:
        return _redirect_dashboard()

    rodadas = await list_rodadas_by_cliente(db, cliente.id)
    rodada = next((r for r in rodadas if str(r.id) == str(rodada_id)), None)
    if not rodada:
        return RedirectResponse(url=f"/admin/clientes/{cliente.id}", status_code=303)

    setores = await list_setores_by_cliente(db, cliente.id)
    invites = await list_invites_by_rodada(db, rodada_id=rodada.id)
    attempts = await _load_all_attempts(
        db,
        cliente_id=str(cliente.id),
        rodada_id=str(rodada.id),
        setor_id=setor_id,
        limit=5000,
    )

    return templates.TemplateResponse(
        "admin/rodada_detail.html",
        {
            "request": request,
            "csrf_token": request.cookies.get(CSRF_COOKIE_NAME),
            "cliente": cliente,
            "rodada": rodada,
            "setores": setores,
            "invites": invites,
            "attempts": attempts,
            "setor_id": setor_id,
            "created_invite_id": created_invite_id,
            "created_invite_path": created_invite_path,
        },
    )


@router.post("/rodadas/{rodada_id}/invites", response_class=HTMLResponse)
async def admin_create_invite(
    request: Request,
    rodada_id: str,
    cliente_id: str = Form(...),
    setor_id: str | None = Form(None),
    cargo: str | None = Form(None),
    tipo_aplicacao: str = Form(...),
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    allowed, response = await _require_admin_post(request, admin)
    if not allowed:
        return response

    cliente_pk = _safe_uuid(cliente_id) or cliente_id
    cliente = await get_cliente_by_id(db, cliente_pk)
    if not cliente:
        return _redirect_dashboard()

    rodadas = await list_rodadas_by_cliente(db, cliente.id)
    rodada = next((r for r in rodadas if str(r.id) == str(rodada_id)), None)
    if not rodada:
        return RedirectResponse(url=f"/admin/clientes/{cliente.id}", status_code=303)

    tok = generate_invite_token()
    inv = await create_invite(
        db,
        token_hash=tok.token_hash,
        cliente_id=cliente.id,
        rodada_id=rodada.id,
        setor_id=(_safe_uuid(setor_id) if setor_id else None),
        cargo=(str(cargo).strip() or None) if cargo is not None else None,
        tipo_aplicacao=tipo_aplicacao,
        criado_por=admin.id,
    )
    await db.commit()

    created_path = f"/t/{tok.token}"

    redirect_query = urlencode(
        {
            "cliente_id": str(cliente.id),
            "created_invite_id": str(inv.id),
            "created_invite_path": created_path,
        }
    )
    return RedirectResponse(
        url=f"/admin/rodadas/{rodada.id}?{redirect_query}#convites",
        status_code=303,
    )


@router.get("/attempts/{attempt_id}", response_class=HTMLResponse)
async def admin_participant_detail(
    request: Request,
    attempt_id: str,
    cliente_id: str | None = Query(None),
    rodada_id: str | None = Query(None),
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return admin

    attempt = await _get_attempt_with_participant(db, attempt_id)
    if not attempt:
        return _redirect_dashboard()

    participant = getattr(attempt, "participant", None)
    computed_result = await _get_computed_result_by_attempt_id(db, attempt_id)
    report_snapshot = await _get_report_snapshot_by_attempt_id(db, attempt_id)

    cliente, rodada, resolved_cliente_id, resolved_rodada_id = await _resolve_cliente_rodada_for_attempt(
        db,
        attempt,
        cliente_id,
        rodada_id,
    )

    pdf_path: str | None = None
    if report_snapshot is not None:
        try:
            pdf_path = await ensure_pdf_cached(db, str(attempt.id))
        except Exception:
            pdf_path = report_snapshot.pdf_path

    rankings = _build_rankings(computed_result)
    ranking_details = _build_individual_rankings_payload(computed_result)
    report_status = _report_status_payload(computed_result, report_snapshot, pdf_path)

    setor = None
    attempt_setor_id = getattr(attempt, "setor_id", None)
    if attempt_setor_id is not None:
        setor = await get_setor_by_id(db, attempt_setor_id)

    invite = None
    invite_id = getattr(attempt, "invite_id", None)
    if invite_id is not None:
        invite = await get_invite_by_id(db, invite_id)

    participant_context = _build_participant_managerial_context(
        attempt=attempt,
        participant=participant,
        cliente=cliente,
        rodada=rodada,
        setor=setor,
    )

    token_traceability = _build_token_traceability_payload(
        attempt=attempt,
        invite=invite,
    )

    delivery_status = _build_delivery_status_payload(
        attempt=attempt,
        report_snapshot=report_snapshot,
        pdf_path=pdf_path,
    )

    pdf_url = _build_query_url(
        f"/admin/attempts/{attempt.id}/pdf",
        {
            "cliente_id": resolved_cliente_id,
            "rodada_id": resolved_rodada_id,
        },
    )

    premium_pdf_url = _build_query_url(
        f"/admin/attempts/{attempt.id}/pdf-premium",
        {
            "cliente_id": resolved_cliente_id,
            "rodada_id": resolved_rodada_id,
        },
    )

    cliente_url = (
        f"/admin/clientes/{resolved_cliente_id}"
        if resolved_cliente_id and resolved_cliente_id != "-"
        else "/admin/dashboard"
    )

    rodada_url = (
        _build_query_url(
            f"/admin/rodadas/{resolved_rodada_id}",
            {"cliente_id": resolved_cliente_id},
        )
        if resolved_cliente_id
        and resolved_cliente_id != "-"
        and resolved_rodada_id
        and resolved_rodada_id != "-"
        else cliente_url
    )

    csv_url = (
        _build_query_url(
            "/admin/exportar/csv",
            {
                "cliente_id": resolved_cliente_id,
                "rodada_id": resolved_rodada_id,
            },
        )
        if resolved_cliente_id and resolved_rodada_id
        else "/admin/exportar/csv"
    )

    xlsx_url = (
        _build_query_url(
            "/admin/exportar/xlsx",
            {
                "cliente_id": resolved_cliente_id,
                "rodada_id": resolved_rodada_id,
            },
        )
        if resolved_cliente_id and resolved_rodada_id
        else "/admin/exportar/xlsx"
    )

    participants_url = _build_contextual_participants_url(
        cliente_id=resolved_cliente_id,
        rodada_id=resolved_rodada_id if resolved_rodada_id != "-" else None,
    )

    bi_overview_url = _build_contextual_bi_overview_url(
        cliente_id=resolved_cliente_id,
        rodada_id=resolved_rodada_id if resolved_rodada_id != "-" else None,
    )

    comparativo_url = _build_contextual_comparativo_url(
        cliente_id=resolved_cliente_id,
        rodada_id=resolved_rodada_id if resolved_rodada_id != "-" else None,
    )

    dana_url = _build_query_url(
        "/admin/ai/analysis-inteligente",
        {
            "cliente_id": resolved_cliente_id if resolved_cliente_id != "-" else None,
            "attempt_id": str(attempt.id),
            "rodada_id": resolved_rodada_id if resolved_rodada_id != "-" else None,
        },
    )

    return templates.TemplateResponse(
        "admin/participant_detail.html",
        {
            "request": request,
            "admin": admin,
            "attempt": attempt,
            "participant": participant,
            "cliente": cliente,
            "rodada": rodada,
            "setor": setor,
            "invite": invite,
            "computed_result": computed_result,
            "report_snapshot": report_snapshot,
            "report_status": report_status,
            "delivery_status": delivery_status,
            "participant_context": participant_context,
            "token_traceability": token_traceability,
            "ranking_details": ranking_details,
            "top3": rankings["top3"],
            "top5": rankings["top5"],
            "bottom3": rankings["bottom3"],
            "pdf_url": pdf_url,
            "premium_pdf_url": premium_pdf_url,
            "cliente_url": cliente_url,
            "rodada_url": rodada_url,
            "csv_url": csv_url,
            "xlsx_url": xlsx_url,
            "participants_url": participants_url,
            "bi_overview_url": bi_overview_url,
            "comparativo_url": comparativo_url,
            "dana_url": dana_url,
            "resolved_cliente_id": resolved_cliente_id,
            "resolved_rodada_id": resolved_rodada_id,
        },
    )


@router.get("/attempts/{attempt_id}/pdf")
async def admin_participant_pdf(
    request: Request,
    attempt_id: str,
    cliente_id: str | None = Query(None),
    rodada_id: str | None = Query(None),
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return admin

    attempt = await _get_attempt_with_participant(db, attempt_id)
    if not attempt:
        return _redirect_dashboard()

    report_snapshot = await _get_report_snapshot_by_attempt_id(db, attempt_id)
    if report_snapshot is None:
        back_url = (
            _build_query_url(
                f"/admin/attempts/{attempt_id}",
                {
                    "cliente_id": cliente_id,
                    "rodada_id": rodada_id,
                },
            )
            if cliente_id or rodada_id
            else "/admin/dashboard"
        )
        return RedirectResponse(url=back_url, status_code=303)

    pdf_path = await ensure_pdf_cached(db, str(attempt.id))
    participant = getattr(attempt, "participant", None)
    filename_slug = _build_download_name_slug(
        getattr(participant, "nome", None) if participant is not None else None,
        getattr(participant, "sobrenome", None) if participant is not None else None,
        str(attempt.id),
    )
    filename = f"report_{filename_slug}.pdf"

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=filename,
    )


@router.get("/exportar/csv")
async def admin_export_csv(
    cliente_id: str | None = Query(None),
    rodada_id: str | None = Query(None),
    setor_id: str | None = Query(None),
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return admin

    rows = await _build_export_rows(
        db,
        cliente_id=cliente_id,
        rodada_id=rodada_id,
        setor_id=setor_id,
    )
    payload = _build_csv_bytes(rows)
    buffer = io.BytesIO(payload)

    return StreamingResponse(
        buffer,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="profiledna_attempts.csv"',
        },
    )


@router.get("/exportar/xlsx")
async def admin_export_xlsx(
    cliente_id: str | None = Query(None),
    rodada_id: str | None = Query(None),
    setor_id: str | None = Query(None),
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return admin

    rows = await _build_export_rows(
        db,
        cliente_id=cliente_id,
        rodada_id=rodada_id,
        setor_id=setor_id,
    )
    payload = _build_xlsx_bytes(rows)
    buffer = io.BytesIO(payload)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="profiledna_attempts.xlsx"',
        },
    )


@router.get("/attempts/{attempt_id}/pdf-premium")
async def admin_participant_pdf_premium(
    request: Request,
    attempt_id: str,
    cliente_id: str | None = Query(None),
    rodada_id: str | None = Query(None),
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return admin

    attempt = await _get_attempt_with_participant(db, attempt_id)
    if not attempt:
        return _redirect_dashboard()

    computed_result = await _get_computed_result_by_attempt_id(db, attempt_id)
    if computed_result is None:
        return _redirect_dashboard()

    from fastapi.responses import FileResponse
    from backend.repositories import result as repo_result_local
    from backend.reports.context_premium import build_premium_report_context
    from backend.reports.pdf_premium import ensure_premium_pdf_cached
    from backend.reports.renderer_premium import render_report_premium_html

    premium_snapshot = await repo_result_local.get_premium_report_snapshot_by_attempt_id(db, attempt.id)
    if premium_snapshot is None:
        premium_context = await build_premium_report_context(
            db,
            attempt=attempt,
            computed_result=computed_result,
        )
        premium_html = render_report_premium_html(premium_context)
        await repo_result_local.ensure_premium_report_snapshot(
            db,
            attempt.id,
            premium_html,
        )
        await db.commit()

    premium_pdf_path = await ensure_premium_pdf_cached(db, str(attempt.id))
    await db.commit()

    participant = getattr(attempt, "participant", None)
    filename_slug = _build_download_name_slug(
        getattr(participant, "nome", None) if participant is not None else None,
        getattr(participant, "sobrenome", None) if participant is not None else None,
        str(attempt.id),
    )
    filename = f"profiledna_premium_{filename_slug}.pdf"
    return FileResponse(
        path=premium_pdf_path,
        media_type="application/pdf",
        filename=filename,
    )
