# /srv/profiledna/backend/ai_analyst/services.py
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping
from uuid import UUID

from backend.ai_analyst.prompts import PromptContext


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b", re.IGNORECASE)
CPF_RE = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}\-?\d{2}\b")
PHONE_RE = re.compile(
    r"(?:(?:\+?\d{1,3}\s*)?(?:\(?\d{2,3}\)?\s*)?(?:9?\d{4}\-?\d{4}))"
)
UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)

SAFE_EMPTY_QUESTION = "[PERGUNTA SANITIZADA SEM CONTEÚDO RELEVANTE]"

QUERY_MODE_PARTICIPANTE = "participante"
QUERY_MODE_GRUPO = "grupo"
QUERY_MODE_CLIENTE = "cliente"
QUERY_MODE_COMPARATIVO = "comparativo"

ALLOWED_QUERY_MODES = {
    QUERY_MODE_PARTICIPANTE,
    QUERY_MODE_GRUPO,
    QUERY_MODE_CLIENTE,
    QUERY_MODE_COMPARATIVO,
}

MAX_CONVERSATION_HISTORY_ITEMS = 6
MAX_HISTORY_RESPONSE_CHARS = 1600


@dataclass(frozen=True)
class DanaQuestionInput:
    """
    Entrada bruta da pergunta do gestor/admin para a DANA.
    """

    question: str
    cliente_id: str
    admin_user_id: str
    attempt_id: str | None = None
    filters_active: Mapping[str, Any] | None = None
    comparative: bool = False
    selected_participant_ids: tuple[str, ...] = ()
    docsia_enabled: bool = False
    comparative_enabled: bool = False
    search_scope_enabled: bool = False
    conversation_history: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True)
class DanaScopeContext:
    """
    Contexto estruturado, serializável e auditável da análise.
    Não deve conter PII desnecessária.
    """

    cliente_id: str
    admin_user_id: str
    attempt_id: str | None
    query_mode: str
    filters_active: dict[str, Any]
    selected_participant_ids: tuple[str, ...]
    comparative: bool
    docsia_enabled: bool
    comparative_enabled: bool
    search_scope_enabled: bool


@dataclass(frozen=True)
class DanaPreparedInput:
    """
    Resultado preparado para as próximas camadas do módulo.
    """

    question_raw: str
    question_sanitized: str
    scope: DanaScopeContext
    analysis_scope_payload: dict[str, Any]
    prompt_context: PromptContext
    conversation_history: list[dict[str, Any]]


def _strip_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _mask_uuids(text: str) -> str:
    return UUID_RE.sub("[ID REMOVIDO]", text)


def sanitize_question_text(text: str) -> str:
    """
    Sanitiza a pergunta antes de qualquer uso externo.

    Remove ou mascara PII e identificadores sensíveis comuns.
    Mantém o máximo possível da intenção analítica original.
    """
    cleaned = _strip_text(text)

    cleaned = EMAIL_RE.sub("[EMAIL REMOVIDO]", cleaned)
    cleaned = CPF_RE.sub("[CPF REMOVIDO]", cleaned)
    cleaned = PHONE_RE.sub("[TELEFONE REMOVIDO]", cleaned)
    cleaned = _mask_uuids(cleaned)

    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned if cleaned else SAFE_EMPTY_QUESTION


def _normalize_scalar(value: Any) -> Any:
    """
    Normaliza valores para JSON auditável.
    """
    if value is None:
        return None

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, (str, int, float, bool)):
        return value

    return str(value)


def _normalize_iterable(value: Iterable[Any]) -> list[Any]:
    return [_normalize_scalar(v) for v in value]


def normalize_filters_active(filters: Mapping[str, Any] | None) -> dict[str, Any]:
    """
    Gera um dicionário estável e serializável para auditoria.
    """
    if not filters:
        return {}

    normalized: dict[str, Any] = {}

    for key, value in filters.items():
        if isinstance(value, Mapping):
            nested: dict[str, Any] = {}
            for nk, nv in value.items():
                if isinstance(nv, (list, tuple, set)):
                    nested[str(nk)] = _normalize_iterable(nv)
                else:
                    nested[str(nk)] = _normalize_scalar(nv)
            normalized[str(key)] = nested
        elif isinstance(value, (list, tuple, set)):
            normalized[str(key)] = _normalize_iterable(value)
        else:
            normalized[str(key)] = _normalize_scalar(value)

    return normalized


def normalize_conversation_history(
    history: Iterable[Mapping[str, Any]] | None,
    *,
    limit: int = MAX_CONVERSATION_HISTORY_ITEMS,
    max_response_chars: int = MAX_HISTORY_RESPONSE_CHARS,
) -> list[dict[str, Any]]:
    """
    Normaliza um histórico curto de conversa para continuidade contextual.

    Regras:
    - mantém apenas os últimos `limit` itens;
    - sanitiza novamente as perguntas;
    - reduz e limpa respostas longas para não inflar tokens;
    - ignora itens sem conteúdo útil.
    """
    if not history:
        return []

    raw_items = list(history)
    if limit > 0:
        raw_items = raw_items[-limit:]

    normalized_items: list[dict[str, Any]] = []

    for raw in raw_items:
        if not isinstance(raw, Mapping):
            continue

        question_value = raw.get("question_sanitized")
        if not _strip_text(question_value):
            question_value = raw.get("question")

        question_sanitized = sanitize_question_text(_strip_text(question_value))
        response_text = _strip_text(raw.get("response_text"))
        created_at = _strip_text(raw.get("created_at")) or None

        if response_text:
            response_text = re.sub(r"\s+", " ", response_text).strip()
            if max_response_chars > 0 and len(response_text) > max_response_chars:
                response_text = response_text[: max_response_chars - 3].rstrip() + "..."

        if question_sanitized == SAFE_EMPTY_QUESTION and not response_text:
            continue

        normalized_items.append(
            {
                "question_sanitized": question_sanitized,
                "response_text": response_text,
                "created_at": created_at,
            }
        )

    return normalized_items


def infer_query_mode(
    *,
    attempt_id: str | None,
    comparative: bool,
    selected_participant_ids: Iterable[str] | None = None,
) -> str:
    """
    Infere o modo principal da consulta da DANA.
    """
    participant_ids = tuple(str(x) for x in (selected_participant_ids or ()) if _strip_text(x))

    if comparative:
        return QUERY_MODE_COMPARATIVO

    if _strip_text(attempt_id):
        return QUERY_MODE_PARTICIPANTE

    if len(participant_ids) > 1:
        return QUERY_MODE_GRUPO

    return QUERY_MODE_CLIENTE


def build_analysis_scope(
    *,
    cliente_id: str,
    admin_user_id: str,
    attempt_id: str | None,
    query_mode: str,
    filters_active: Mapping[str, Any] | None = None,
    selected_participant_ids: Iterable[str] | None = None,
    comparative: bool = False,
    docsia_enabled: bool = False,
    comparative_enabled: bool = False,
    search_scope_enabled: bool = False,
) -> dict[str, Any]:
    """
    Monta payload de escopo para auditoria e rastreabilidade.
    """
    safe_query_mode = query_mode if query_mode in ALLOWED_QUERY_MODES else QUERY_MODE_CLIENTE
    normalized_filters = normalize_filters_active(filters_active)
    normalized_participants = tuple(
        str(x) for x in (selected_participant_ids or ()) if _strip_text(x)
    )

    return {
        "cliente_id": _strip_text(cliente_id),
        "admin_user_id": _strip_text(admin_user_id),
        "attempt_id": _strip_text(attempt_id) or None,
        "query_mode": safe_query_mode,
        "filters_active": normalized_filters,
        "selected_participant_ids": list(normalized_participants),
        "comparative": bool(comparative),
        "docsia_enabled": bool(docsia_enabled),
        "comparative_enabled": bool(comparative_enabled),
        "search_scope_enabled": bool(search_scope_enabled),
    }


def build_prompt_context_from_scope(scope: DanaScopeContext) -> PromptContext:
    """
    Converte o escopo da consulta em PromptContext para prompts.py.
    """
    return PromptContext(
        ai_enabled=True,
        has_report_context=bool(scope.attempt_id) or scope.query_mode == QUERY_MODE_PARTICIPANTE,
        has_bi_context=True,
        has_docsia_context=bool(scope.docsia_enabled),
        has_comparative_context=bool(
            scope.comparative or scope.query_mode == QUERY_MODE_COMPARATIVO or scope.comparative_enabled
        ),
        has_search_scope=bool(scope.search_scope_enabled),
    )


def prepare_question_input(payload: DanaQuestionInput) -> DanaPreparedInput:
    """
    Pipeline principal de preparação da pergunta:
    - sanitiza texto;
    - infere modo da consulta;
    - normaliza filtros;
    - gera escopo auditável;
    - produz PromptContext para a camada de prompt/agente;
    - normaliza histórico curto de conversa.
    """
    question_raw = _strip_text(payload.question)
    question_sanitized = sanitize_question_text(question_raw)

    selected_participant_ids = tuple(
        str(x) for x in payload.selected_participant_ids if _strip_text(x)
    )

    query_mode = infer_query_mode(
        attempt_id=payload.attempt_id,
        comparative=payload.comparative,
        selected_participant_ids=selected_participant_ids,
    )

    normalized_filters = normalize_filters_active(payload.filters_active)

    scope = DanaScopeContext(
        cliente_id=_strip_text(payload.cliente_id),
        admin_user_id=_strip_text(payload.admin_user_id),
        attempt_id=_strip_text(payload.attempt_id) or None,
        query_mode=query_mode,
        filters_active=normalized_filters,
        selected_participant_ids=selected_participant_ids,
        comparative=bool(payload.comparative),
        docsia_enabled=bool(payload.docsia_enabled),
        comparative_enabled=bool(payload.comparative_enabled),
        search_scope_enabled=bool(payload.search_scope_enabled),
    )

    analysis_scope_payload = build_analysis_scope(
        cliente_id=scope.cliente_id,
        admin_user_id=scope.admin_user_id,
        attempt_id=scope.attempt_id,
        query_mode=scope.query_mode,
        filters_active=scope.filters_active,
        selected_participant_ids=scope.selected_participant_ids,
        comparative=scope.comparative,
        docsia_enabled=scope.docsia_enabled,
        comparative_enabled=scope.comparative_enabled,
        search_scope_enabled=scope.search_scope_enabled,
    )

    prompt_context = build_prompt_context_from_scope(scope)
    conversation_history = normalize_conversation_history(payload.conversation_history)

    return DanaPreparedInput(
        question_raw=question_raw,
        question_sanitized=question_sanitized,
        scope=scope,
        analysis_scope_payload=analysis_scope_payload,
        prompt_context=prompt_context,
        conversation_history=conversation_history,
    )
