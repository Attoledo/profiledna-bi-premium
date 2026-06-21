# /srv/profiledna/backend/ai_analyst/tools.py
from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from html import unescape
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.bi.services import (
    BIServiceFilters,
    build_bi_comparison_dimension_table,
    build_bi_service_payload,
)
from backend.models.attempt import Attempt
from backend.models.result import ComputedResult, ReportSnapshot
from backend.repositories.cliente import get_cliente_by_id


TOOL_GET_ATTEMPT_CONTEXT = "get_attempt_context"
TOOL_GET_REPORT_CONTEXT = "get_report_context"
TOOL_GET_BI_OVERVIEW = "get_bi_overview"
TOOL_GET_BI_CLIENTE = "get_bi_cliente"
TOOL_COMPARE_BI_SNAPSHOTS = "compare_bi_snapshots"

ALLOWED_TOOL_NAMES = {
    TOOL_GET_ATTEMPT_CONTEXT,
    TOOL_GET_REPORT_CONTEXT,
    TOOL_GET_BI_OVERVIEW,
    TOOL_GET_BI_CLIENTE,
    TOOL_COMPARE_BI_SNAPSHOTS,
}


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": TOOL_GET_ATTEMPT_CONTEXT,
        "description": (
            "Retorna contexto consolidado de um participante a partir do resultado final oficial. "
            "Não retorna respostas A/B brutas."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "attempt_id": {
                    "type": "string",
                    "description": "ID do attempt do participante.",
                }
            },
            "required": ["attempt_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": TOOL_GET_REPORT_CONTEXT,
        "description": (
            "Retorna metadados e conteúdo do snapshot oficial do relatório final do participante."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "attempt_id": {
                    "type": "string",
                    "description": "ID do attempt do participante.",
                }
            },
            "required": ["attempt_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": TOOL_GET_BI_OVERVIEW,
        "description": (
            "Retorna payload consolidado de BI no escopo do cliente atual, com filtros opcionais."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "rodada_id": {"type": ["string", "null"]},
                "setor_id": {"type": ["string", "null"]},
                "cargo": {"type": ["string", "null"]},
                "tipo_aplicacao": {"type": ["string", "null"]},
                "status": {"type": ["string", "null"]},
                "only_completed": {"type": ["boolean", "null"]},
            },
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": TOOL_GET_BI_CLIENTE,
        "description": (
            "Retorna o BI consolidado do cliente atual com filtros opcionais, sempre respeitando "
            "o cliente_id do contexto da sessão."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "rodada_id": {"type": ["string", "null"]},
                "setor_id": {"type": ["string", "null"]},
                "cargo": {"type": ["string", "null"]},
                "tipo_aplicacao": {"type": ["string", "null"]},
                "status": {"type": ["string", "null"]},
                "only_completed": {"type": ["boolean", "null"]},
            },
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": TOOL_COMPARE_BI_SNAPSHOTS,
        "description": (
            "Compara dois recortes oficiais de BI do mesmo cliente atual, gerando tabela delta "
            "por dimensão."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "left": {
                    "type": "object",
                    "properties": {
                        "rodada_id": {"type": ["string", "null"]},
                        "setor_id": {"type": ["string", "null"]},
                        "cargo": {"type": ["string", "null"]},
                        "tipo_aplicacao": {"type": ["string", "null"]},
                        "status": {"type": ["string", "null"]},
                        "only_completed": {"type": ["boolean", "null"]},
                    },
                    "required": [],
                    "additionalProperties": False,
                },
                "right": {
                    "type": "object",
                    "properties": {
                        "rodada_id": {"type": ["string", "null"]},
                        "setor_id": {"type": ["string", "null"]},
                        "cargo": {"type": ["string", "null"]},
                        "tipo_aplicacao": {"type": ["string", "null"]},
                        "status": {"type": ["string", "null"]},
                        "only_completed": {"type": ["boolean", "null"]},
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
            "required": ["left", "right"],
            "additionalProperties": False,
        },
    },
]


class DanaToolError(ValueError):
    """
    Erro controlado das tools da DANA.
    """


def _clean_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _serialize_bi_payload(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}

    if is_dataclass(payload):
        serialized = asdict(payload)
        if isinstance(serialized, dict):
            return serialized
        raise DanaToolError("Payload de BI dataclass nao serializavel no runtime atual.")

    if isinstance(payload, dict):
        return payload

    if hasattr(payload, "model_dump"):
        serialized = payload.model_dump(mode="json")
        if isinstance(serialized, dict):
            return serialized
        raise DanaToolError("Payload de BI model_dump nao serializavel no runtime atual.")

    if hasattr(payload, "dict"):
        serialized = payload.dict()
        if isinstance(serialized, dict):
            return serialized
        raise DanaToolError("Payload de BI dict() nao serializavel no runtime atual.")

    raise DanaToolError("Payload de BI nao serializavel no runtime atual.")


def _build_bi_filters(
    *,
    cliente_id: str,
    rodada_id: str | None = None,
    setor_id: str | None = None,
    cargo: str | None = None,
    tipo_aplicacao: str | None = None,
    status: str | None = None,
    only_completed: bool | None = None,
) -> BIServiceFilters:
    return BIServiceFilters(
        cliente_id=cliente_id,
        rodada_id=_clean_optional_text(rodada_id),
        setor_id=_clean_optional_text(setor_id),
        cargo=_clean_optional_text(cargo),
        tipo_aplicacao=_clean_optional_text(tipo_aplicacao),
        attempt_status=_clean_optional_text(status),
        only_completed=bool(only_completed),
    )


async def _ensure_cliente_exists(db: AsyncSession, cliente_id: str) -> None:
    cliente = await get_cliente_by_id(db, cliente_id)
    if not cliente:
        raise DanaToolError("Cliente não encontrado no contexto atual.")


async def _get_attempt_for_cliente(
    db: AsyncSession,
    *,
    attempt_id: str,
    cliente_id: str,
) -> Attempt:
    result = await db.execute(
        select(Attempt)
        .options(selectinload(Attempt.participant))
        .where(
            Attempt.id == attempt_id,
            Attempt.cliente_id == cliente_id,
        )
    )
    attempt = result.scalar_one_or_none()
    if not attempt:
        raise DanaToolError(
            "Attempt não encontrado ou fora do escopo do cliente atual."
        )
    return attempt


async def _get_computed_result_for_attempt(
    db: AsyncSession,
    *,
    attempt_id: str,
) -> ComputedResult | None:
    result = await db.execute(
        select(ComputedResult).where(ComputedResult.attempt_id == attempt_id)
    )
    return result.scalar_one_or_none()


async def _get_report_snapshot_for_attempt(
    db: AsyncSession,
    *,
    attempt_id: str,
) -> ReportSnapshot | None:
    result = await db.execute(
        select(ReportSnapshot).where(ReportSnapshot.attempt_id == attempt_id)
    )
    return result.scalar_one_or_none()


def _computed_result_payload(computed_result: ComputedResult | None) -> dict[str, Any]:
    if computed_result is None:
        return {
            "has_computed_result": False,
            "scores": {},
            "bands": {},
            "top3": [],
            "top5": [],
            "bottom3": [],
            "interpretations": {},
            "premium_data": {},
        }

    top3 = list((computed_result.top3 or {}).get("top3", []))
    top5 = list((computed_result.top5 or {}).get("top5", []))
    bottom3 = list((computed_result.bottom3 or {}).get("bottom3", []))

    return {
        "has_computed_result": True,
        "scores": computed_result.scores or {},
        "bands": computed_result.bands or {},
        "top3": top3,
        "top5": top5,
        "bottom3": bottom3,
        "interpretations": computed_result.interpretations or {},
        "premium_data": computed_result.premium_data or {},
    }


def _clean_text_excerpt(value: str | None, limit: int = 600) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    if not cleaned:
        return None
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "..."


def _strip_html(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_section_html(html: str, section_number: int) -> str:
    pattern = re.compile(
        rf"<h3[^>]*>\s*{section_number}\.\s.*?</h3>(.*?)(?=<h3[^>]*>\s*\d+\.|$)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(html)
    if not match:
        return ""
    return match.group(1)


def _extract_first_paragraph_from_section(html: str, section_number: int, limit: int = 900) -> str | None:
    section_html = _extract_section_html(html, section_number)
    if not section_html:
        return None

    paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", section_html, flags=re.IGNORECASE | re.DOTALL)
    for paragraph in paragraphs:
        text_value = _clean_text_excerpt(_strip_html(paragraph), limit=limit)
        if text_value:
            return text_value
    return None


def _extract_titles_from_section(html: str, section_number: int, limit: int = 10) -> list[str]:
    section_html = _extract_section_html(html, section_number)
    if not section_html:
        return []

    titles = re.findall(r"<h4[^>]*>(.*?)</h4>", section_html, flags=re.IGNORECASE | re.DOTALL)
    cleaned: list[str] = []
    for item in titles:
        value = _clean_text_excerpt(_strip_html(item), limit=180)
        if value:
            cleaned.append(value)

    unique: list[str] = []
    for item in cleaned:
        if item not in unique:
            unique.append(item)

    return unique[:limit]


def _extract_identification_summary(html: str) -> dict[str, Any]:
    labels = {
        "Nome": "nome",
        "Empresa": "empresa",
        "Tipo de aplicação": "tipo_aplicacao",
        "Cargo": "cargo",
        "Data de conclusão": "data_conclusao",
    }

    summary: dict[str, Any] = {}

    for label, key in labels.items():
        pattern = re.compile(
            rf">{re.escape(label)}\s*<.*?<td[^>]*>(.*?)</td>",
            flags=re.IGNORECASE | re.DOTALL,
        )
        match = pattern.search(html)
        if not match:
            summary[key] = None
            continue
        summary[key] = _clean_text_excerpt(_strip_html(match.group(1)), limit=220)

    return summary


def _extract_nota_tecnica_resumida(html: str) -> list[str]:
    section_html = _extract_section_html(html, 9)
    if not section_html:
        return []

    paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", section_html, flags=re.IGNORECASE | re.DOTALL)
    cleaned: list[str] = []
    for paragraph in paragraphs:
        value = _clean_text_excerpt(_strip_html(paragraph), limit=500)
        if value:
            cleaned.append(value)

    return cleaned[:2]


def _report_snapshot_payload(report_snapshot: ReportSnapshot | None) -> dict[str, Any]:
    if report_snapshot is None:
        return {
            "has_report_snapshot": False,
            "pdf_path": None,
            "generated_at": None,
            "identificacao_resumida": {},
            "sintese_executiva": None,
            "top5": [],
            "bottom3": [],
            "competencias_pdi": [],
            "nota_tecnica_resumida": [],
        }

    html = report_snapshot.html_content or ""

    return {
        "has_report_snapshot": True,
        "pdf_path": report_snapshot.pdf_path,
        "generated_at": (
            report_snapshot.generated_at.isoformat()
            if report_snapshot.generated_at is not None
            else None
        ),
        "identificacao_resumida": _extract_identification_summary(html),
        "sintese_executiva": _extract_first_paragraph_from_section(html, 2, limit=1200),
        "top5": _extract_titles_from_section(html, 4, limit=5),
        "bottom3": _extract_titles_from_section(html, 5, limit=3),
        "competencias_pdi": _extract_titles_from_section(html, 6, limit=8),
        "nota_tecnica_resumida": _extract_nota_tecnica_resumida(html),
    }


async def get_attempt_context(
    db: AsyncSession,
    *,
    cliente_id: str,
    attempt_id: str,
) -> dict[str, Any]:
    """
    Tool: contexto consolidado do participante.
    """
    await _ensure_cliente_exists(db, cliente_id)

    attempt = await _get_attempt_for_cliente(
        db,
        attempt_id=attempt_id,
        cliente_id=cliente_id,
    )
    computed_result = await _get_computed_result_for_attempt(db, attempt_id=attempt_id)

    participant = getattr(attempt, "participant", None)

    return {
        "tool": TOOL_GET_ATTEMPT_CONTEXT,
        "cliente_id": cliente_id,
        "attempt_id": str(attempt.id),
        "attempt": {
            "id": str(attempt.id),
            "status": str(attempt.status),
            "progress": int(attempt.progress or 0),
            "cargo": attempt.cargo,
            "rodada_id": str(attempt.rodada_id) if attempt.rodada_id else None,
            "setor_id": str(attempt.setor_id) if attempt.setor_id else None,
            "data_inicio": (
                attempt.data_inicio.isoformat() if attempt.data_inicio else None
            ),
            "data_conclusao": (
                attempt.data_conclusao.isoformat() if attempt.data_conclusao else None
            ),
        },
        "participant": {
            "id": str(participant.id) if participant else None,
            "tipo_aplicacao": getattr(participant, "tipo_aplicacao", None),
            "empresa_nome": getattr(participant, "empresa_nome", None),
        },
        "computed_result": _computed_result_payload(computed_result),
    }


async def get_report_context(
    db: AsyncSession,
    *,
    cliente_id: str,
    attempt_id: str,
) -> dict[str, Any]:
    """
    Tool: snapshot oficial do relatório final.
    """
    await _ensure_cliente_exists(db, cliente_id)

    attempt = await _get_attempt_for_cliente(
        db,
        attempt_id=attempt_id,
        cliente_id=cliente_id,
    )
    report_snapshot = await _get_report_snapshot_for_attempt(db, attempt_id=attempt_id)

    return {
        "tool": TOOL_GET_REPORT_CONTEXT,
        "cliente_id": cliente_id,
        "attempt_id": str(attempt.id),
        "report_snapshot": _report_snapshot_payload(report_snapshot),
    }


async def get_bi_overview(
    db: AsyncSession,
    *,
    cliente_id: str,
    rodada_id: str | None = None,
    setor_id: str | None = None,
    cargo: str | None = None,
    tipo_aplicacao: str | None = None,
    status: str | None = None,
    only_completed: bool | None = None,
) -> dict[str, Any]:
    """
    Tool: BI overview no escopo do cliente atual.
    """
    await _ensure_cliente_exists(db, cliente_id)

    filters = _build_bi_filters(
        cliente_id=cliente_id,
        rodada_id=rodada_id,
        setor_id=setor_id,
        cargo=cargo,
        tipo_aplicacao=tipo_aplicacao,
        status=status,
        only_completed=only_completed,
    )
    payload = await build_bi_service_payload(db, filters=filters)

    return {
        "tool": TOOL_GET_BI_OVERVIEW,
        "cliente_id": cliente_id,
        "filters": {
            "rodada_id": rodada_id,
            "setor_id": setor_id,
            "cargo": cargo,
            "tipo_aplicacao": tipo_aplicacao,
            "status": status,
            "only_completed": bool(only_completed),
        },
        "payload": _serialize_bi_payload(payload),
    }


async def get_bi_cliente(
    db: AsyncSession,
    *,
    cliente_id: str,
    rodada_id: str | None = None,
    setor_id: str | None = None,
    cargo: str | None = None,
    tipo_aplicacao: str | None = None,
    status: str | None = None,
    only_completed: bool | None = None,
) -> dict[str, Any]:
    """
    Tool: BI do cliente atual.
    """
    await _ensure_cliente_exists(db, cliente_id)

    filters = _build_bi_filters(
        cliente_id=cliente_id,
        rodada_id=rodada_id,
        setor_id=setor_id,
        cargo=cargo,
        tipo_aplicacao=tipo_aplicacao,
        status=status,
        only_completed=only_completed,
    )
    payload = await build_bi_service_payload(db, filters=filters)

    return {
        "tool": TOOL_GET_BI_CLIENTE,
        "cliente_id": cliente_id,
        "filters": {
            "rodada_id": rodada_id,
            "setor_id": setor_id,
            "cargo": cargo,
            "tipo_aplicacao": tipo_aplicacao,
            "status": status,
            "only_completed": bool(only_completed),
        },
        "payload": _serialize_bi_payload(payload),
    }


async def compare_bi_snapshots(
    db: AsyncSession,
    *,
    cliente_id: str,
    left: dict[str, Any],
    right: dict[str, Any],
) -> dict[str, Any]:
    """
    Tool: comparação de dois recortes BI do mesmo cliente atual.
    """
    await _ensure_cliente_exists(db, cliente_id)

    left_filters = _build_bi_filters(
        cliente_id=cliente_id,
        rodada_id=_clean_optional_text(left.get("rodada_id")),
        setor_id=_clean_optional_text(left.get("setor_id")),
        cargo=_clean_optional_text(left.get("cargo")),
        tipo_aplicacao=_clean_optional_text(left.get("tipo_aplicacao")),
        status=_clean_optional_text(left.get("status")),
        only_completed=bool(left.get("only_completed")),
    )
    right_filters = _build_bi_filters(
        cliente_id=cliente_id,
        rodada_id=_clean_optional_text(right.get("rodada_id")),
        setor_id=_clean_optional_text(right.get("setor_id")),
        cargo=_clean_optional_text(right.get("cargo")),
        tipo_aplicacao=_clean_optional_text(right.get("tipo_aplicacao")),
        status=_clean_optional_text(right.get("status")),
        only_completed=bool(right.get("only_completed")),
    )

    left_payload = await build_bi_service_payload(db, filters=left_filters)
    right_payload = await build_bi_service_payload(db, filters=right_filters)
    comparison_dimension_rows = build_bi_comparison_dimension_table(
        left_payload,
        right_payload,
    )

    return {
        "tool": TOOL_COMPARE_BI_SNAPSHOTS,
        "cliente_id": cliente_id,
        "left_filters": left,
        "right_filters": right,
        "left_payload": _serialize_bi_payload(left_payload),
        "right_payload": _serialize_bi_payload(right_payload),
        "comparison_dimension_rows": comparison_dimension_rows,
    }


async def execute_tool_call(
    db: AsyncSession,
    *,
    tool_name: str,
    cliente_id: str,
    arguments: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Dispatcher principal de uma tool call individual.
    """
    safe_args = arguments or {}

    if tool_name not in ALLOWED_TOOL_NAMES:
        raise DanaToolError(f"Tool não autorizada: {tool_name}")

    if tool_name == TOOL_GET_ATTEMPT_CONTEXT:
        raw_attempt_id = safe_args.get("attempt_id")
        if not raw_attempt_id:
            raise DanaToolError("attempt_id é obrigatório para get_attempt_context.")
        return await get_attempt_context(
            db,
            cliente_id=cliente_id,
            attempt_id=str(raw_attempt_id),
        )

    if tool_name == TOOL_GET_REPORT_CONTEXT:
        raw_attempt_id = safe_args.get("attempt_id")
        if not raw_attempt_id:
            raise DanaToolError("attempt_id é obrigatório para get_report_context.")
        return await get_report_context(
            db,
            cliente_id=cliente_id,
            attempt_id=str(raw_attempt_id),
        )

    if tool_name == TOOL_GET_BI_OVERVIEW:
        return await get_bi_overview(
            db,
            cliente_id=cliente_id,
            rodada_id=_clean_optional_text(safe_args.get("rodada_id")),
            setor_id=_clean_optional_text(safe_args.get("setor_id")),
            cargo=_clean_optional_text(safe_args.get("cargo")),
            tipo_aplicacao=_clean_optional_text(safe_args.get("tipo_aplicacao")),
            status=_clean_optional_text(safe_args.get("status")),
            only_completed=bool(safe_args.get("only_completed")),
        )

    if tool_name == TOOL_GET_BI_CLIENTE:
        return await get_bi_cliente(
            db,
            cliente_id=cliente_id,
            rodada_id=_clean_optional_text(safe_args.get("rodada_id")),
            setor_id=_clean_optional_text(safe_args.get("setor_id")),
            cargo=_clean_optional_text(safe_args.get("cargo")),
            tipo_aplicacao=_clean_optional_text(safe_args.get("tipo_aplicacao")),
            status=_clean_optional_text(safe_args.get("status")),
            only_completed=bool(safe_args.get("only_completed")),
        )

    if tool_name == TOOL_COMPARE_BI_SNAPSHOTS:
        return await compare_bi_snapshots(
            db,
            cliente_id=cliente_id,
            left=dict(safe_args.get("left") or {}),
            right=dict(safe_args.get("right") or {}),
        )

    raise DanaToolError(f"Dispatcher não implementado para tool: {tool_name}")


async def execute_tool_calls(
    db: AsyncSession,
    *,
    cliente_id: str,
    tool_calls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Executa múltiplas tool calls em sequência, preservando rastreabilidade.

    Cada tool call é isolada em try/except: uma falha individual retorna um
    payload de erro estruturado e não interrompe as demais tools nem derruba
    o agente com HTTP 500.
    """
    results: list[dict[str, Any]] = []

    for call in tool_calls:
        tool_name = str(call.get("name") or "").strip()
        arguments = dict(call.get("arguments") or {})

        try:
            result = await execute_tool_call(
                db,
                tool_name=tool_name,
                cliente_id=cliente_id,
                arguments=arguments,
            )
        except DanaToolError as exc:
            result = {
                "error": True,
                "error_type": "DanaToolError",
                "message": str(exc),
                "tool": tool_name,
                "cliente_id": cliente_id,
                "fallback": "Contexto da tool indisponível. Responda com base nas informações já disponíveis.",
            }
        except Exception as exc:
            result = {
                "error": True,
                "error_type": type(exc).__name__,
                "message": "Falha interna ao executar a tool. Contexto parcial.",
                "tool": tool_name,
                "cliente_id": cliente_id,
                "fallback": "Contexto da tool indisponível. Responda com base nas informações já disponíveis.",
            }

        results.append(
            {
                "name": tool_name,
                "arguments": arguments,
                "result": result,
            }
        )

    return results
