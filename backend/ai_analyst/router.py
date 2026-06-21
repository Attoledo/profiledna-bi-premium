# /srv/profiledna/backend/ai_analyst/router.py
from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, FileSystemLoader, PrefixLoader
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ai_analyst.agent import (
    DanaAgent,
    DanaAgentConfigurationError,
    DanaAgentDisabledError,
    DanaAgentError,
)
from backend.ai_analyst.context_builder import DanaContextRequest, build_analysis_context
from backend.ai_analyst.models import AIInteractionLog
from backend.ai_analyst.services import DanaQuestionInput
from backend.config import get_settings
from backend.database import get_db
from backend.repositories.admin_user import get_admin_by_id
from backend.repositories.cliente import get_cliente_by_id, list_clientes
from backend.services.auth_admin import ACCESS_COOKIE_NAME, decode_access_token


router = APIRouter(prefix="/admin/ai", tags=["admin-ai"])

templates = Jinja2Templates(directory="backend/templates")
templates.env.loader = ChoiceLoader(
    [
        FileSystemLoader("backend/templates"),
        PrefixLoader(
            {
                "ai_analyst": FileSystemLoader("backend/ai_analyst/templates"),
            }
        ),
    ]
)

MAX_AGENT_CONVERSATION_HISTORY = 6


class AIChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    attempt_id: str | None = None
    filters_active: dict[str, Any] | None = None
    comparative: bool = False
    selected_participant_ids: list[str] = Field(default_factory=list)
    docsia_enabled: bool = False
    comparative_enabled: bool = False
    search_scope_enabled: bool = False
    bi_context: str | None = None


class AIChatResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    response: str
    question_sanitized: str
    prompt_version: str
    model_used: str
    tokens_input: int
    tokens_output: int
    cost_usd: str
    duration_ms: int
    query_mode: str
    analysis_scope: dict[str, Any]
    filters_active: dict[str, Any]


def _safe_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except Exception:
        return None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "on", "yes", "y"}


def _parse_json_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _parse_json_list_of_str(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    raw = str(value).strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(item) for item in parsed if str(item).strip()]
    except Exception:
        pass
    return [part.strip() for part in raw.split(",") if part.strip()]


def _ensure_ai_enabled() -> None:
    settings = get_settings()
    if not bool(settings.AI_ENABLED):
        raise HTTPException(status_code=404, detail="Modulo de IA desabilitado")


async def _resolve_attempt_cliente_id(
    db: AsyncSession,
    attempt_id: str | None,
) -> str | None:
    attempt_uuid = _safe_uuid(attempt_id)
    if not attempt_uuid:
        return None

    result = await db.execute(
        select(AIInteractionLog.attempt_id).where(AIInteractionLog.attempt_id == attempt_uuid).limit(1)
    )
    interaction_attempt_id = result.scalar_one_or_none()
    if interaction_attempt_id:
        result_cliente = await db.execute(
            select(AIInteractionLog.cliente_id)
            .where(AIInteractionLog.attempt_id == attempt_uuid)
            .order_by(AIInteractionLog.created_at.desc())
            .limit(1)
        )
        cliente_id = result_cliente.scalar_one_or_none()
        if cliente_id:
            return str(cliente_id)

    from backend.models.attempt import Attempt

    result_attempt = await db.execute(
        select(Attempt.cliente_id).where(Attempt.id == attempt_uuid).limit(1)
    )
    attempt_cliente_id = result_attempt.scalar_one_or_none()
    if attempt_cliente_id:
        return str(attempt_cliente_id)

    return None


async def _resolve_effective_cliente_id(
    db: AsyncSession,
    *,
    cliente_id: str | None,
    attempt_id: str | None,
) -> str | None:
    cliente_text = _clean_text(cliente_id)
    if cliente_text:
        return cliente_text

    return await _resolve_attempt_cliente_id(db, attempt_id)


async def _require_cliente_context(
    db: AsyncSession,
    cliente_id: str,
) -> Any:
    cliente_text = _clean_text(cliente_id)
    if not cliente_text:
        raise HTTPException(status_code=400, detail="Cliente não informado para a análise DANA")

    cliente_pk = _safe_uuid(cliente_text) or cliente_text
    cliente = await get_cliente_by_id(db, cliente_pk)
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return cliente


async def get_current_admin_ai(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    token = request.cookies.get(ACCESS_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Admin não autenticado")

    admin_id = decode_access_token(token)
    if not admin_id:
        raise HTTPException(status_code=401, detail="Token admin inválido")

    admin = await get_admin_by_id(db, admin_id)
    if not admin or not admin.ativo:
        raise HTTPException(status_code=401, detail="Admin não autenticado")

    return admin


def _serialize_decimal(value: Decimal) -> str:
    return format(value, "f")


def _serialize_history_row(row: AIInteractionLog) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "admin_user_id": str(row.admin_user_id),
        "cliente_id": str(row.cliente_id),
        "attempt_id": str(row.attempt_id) if row.attempt_id else None,
        "question_sanitized": row.question_sanitized,
        "response_text": row.response_text,
        "prompt_version": row.prompt_version,
        "model_used": row.model_used,
        "tokens_input": row.tokens_input,
        "tokens_output": row.tokens_output,
        "cost_usd": _serialize_decimal(row.cost_usd),
        "duration_ms": row.duration_ms,
        "analysis_scope": row.analysis_scope or {},
        "filters_active": row.filters_active or {},
        "report_sections_used": row.report_sections_used or [],
        "docsia_documents_used": row.docsia_documents_used or [],
        "docsia_chunks_used": row.docsia_chunks_used or [],
        "bi_context_used": row.bi_context_used or {},
        "query_mode": row.query_mode,
        "tools_called": row.tools_called or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _build_agent_conversation_history(
    items: list[AIInteractionLog],
    *,
    limit: int = MAX_AGENT_CONVERSATION_HISTORY,
) -> tuple[dict[str, Any], ...]:
    if not items:
        return ()

    selected = list(items[:limit])
    selected.reverse()

    normalized: list[dict[str, Any]] = []

    for item in selected:
        question_sanitized = _clean_text(item.question_sanitized)
        response_text = _clean_text(item.response_text)

        if not question_sanitized and not response_text:
            continue

        normalized.append(
            {
                "question_sanitized": question_sanitized or "",
                "response_text": response_text or "",
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
        )

    return tuple(normalized)


async def _list_history_items(
    db: AsyncSession,
    *,
    cliente_id: str,
    attempt_id: str | None = None,
    limit: int = 20,
) -> list[AIInteractionLog]:
    cliente_pk = _safe_uuid(cliente_id) or cliente_id

    query = (
        select(AIInteractionLog)
        .where(AIInteractionLog.cliente_id == cliente_pk)
        .order_by(AIInteractionLog.created_at.desc())
        .limit(limit)
    )

    attempt_uuid = _safe_uuid(attempt_id)
    if attempt_uuid:
        query = (
            select(AIInteractionLog)
            .where(
                AIInteractionLog.cliente_id == cliente_pk,
                AIInteractionLog.attempt_id == attempt_uuid,
            )
            .order_by(AIInteractionLog.created_at.desc())
            .limit(limit)
        )

    result = await db.execute(query)
    return list(result.scalars().all())


def _build_query_payload(
    *,
    term: str | None,
    cliente_id: str | None,
    rodada_id: str | None,
    setor_id: str | None,
    cargo: str | None,
    tipo_aplicacao: str | None,
    status: str | None,
    date_from: str | None,
    date_to: str | None,
    attempt_id: str | None,
    only_completed: bool,
) -> dict[str, Any]:
    return {
        "term": _clean_text(term) or "",
        "cliente_id": _clean_text(cliente_id) or "",
        "rodada_id": _clean_text(rodada_id) or "",
        "setor_id": _clean_text(setor_id) or "",
        "cargo": _clean_text(cargo) or "",
        "tipo_aplicacao": _clean_text(tipo_aplicacao) or "",
        "status": _clean_text(status) or "",
        "date_from": _clean_text(date_from) or "",
        "date_to": _clean_text(date_to) or "",
        "attempt_id": _clean_text(attempt_id) or "",
        "only_completed": bool(only_completed),
    }


def _build_analysis_redirect_url(
    *,
    cliente_id: str | None,
    attempt_id: str | None,
) -> str:
    cliente_text = _clean_text(cliente_id)
    if not cliente_text:
        return "/admin/ai/analysis-inteligente"

    target = f"/admin/ai/analysis-inteligente?cliente_id={cliente_text}"
    attempt_text = _clean_text(attempt_id)
    if attempt_text:
        target += f"&attempt_id={attempt_text}"
    return target


async def _run_dana_agent(
    *,
    db: AsyncSession,
    admin: Any,
    cliente: Any,
    body: AIChatRequest,
) -> AIChatResponse:
    agent = DanaAgent()

    conversation_items = await _list_history_items(
        db,
        cliente_id=str(cliente.id),
        attempt_id=body.attempt_id,
        limit=MAX_AGENT_CONVERSATION_HISTORY,
    )
    conversation_history = _build_agent_conversation_history(
        conversation_items,
        limit=MAX_AGENT_CONVERSATION_HISTORY,
    )

    try:
        result = await agent.run(
            DanaQuestionInput(
                question=body.question,
                cliente_id=str(cliente.id),
                admin_user_id=str(admin.id),
                attempt_id=body.attempt_id,
                filters_active=body.filters_active,
                comparative=body.comparative,
                selected_participant_ids=tuple(body.selected_participant_ids),
                docsia_enabled=body.docsia_enabled,
                comparative_enabled=body.comparative_enabled,
                search_scope_enabled=body.search_scope_enabled,
                conversation_history=conversation_history,
            ),
            db=db,
        )
        await db.commit()
    except DanaAgentDisabledError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DanaAgentConfigurationError as exc:
        await db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DanaAgentError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Falha interna ao processar a interação com a DANA.",
        ) from exc

    return AIChatResponse(
        response=result.response_text,
        question_sanitized=result.question_sanitized,
        prompt_version=result.prompt_version,
        model_used=result.model_used,
        tokens_input=result.tokens_input,
        tokens_output=result.tokens_output,
        cost_usd=_serialize_decimal(result.cost_usd),
        duration_ms=result.duration_ms,
        query_mode=result.query_mode,
        analysis_scope=result.analysis_scope,
        filters_active=result.filters_active,
    )


@router.get("/health")
async def ai_health():
    _ensure_ai_enabled()
    settings = get_settings()
    return {
        "status": "ok",
        "module": "DANA",
        "ai_enabled": settings.AI_ENABLED,
        "model": settings.OPENAI_MODEL,
    }


@router.get("/analysis-inteligente", response_class=HTMLResponse)
async def ai_analysis_inteligente(
    request: Request,
    cliente_id: str | None = Query(None),
    attempt_id: str | None = Query(None),
    term: str | None = Query(None),
    rodada_id: str | None = Query(None),
    setor_id: str | None = Query(None),
    cargo: str | None = Query(None),
    tipo_aplicacao: str | None = Query(None),
    status: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    only_completed: bool = Query(False),
    limit_messages: int = Query(20, ge=1, le=100),
    admin=Depends(get_current_admin_ai),
    db: AsyncSession = Depends(get_db),
):
    _ensure_ai_enabled()

    effective_cliente_id = await _resolve_effective_cliente_id(
        db,
        cliente_id=cliente_id,
        attempt_id=attempt_id,
    )

    context_payload = await build_analysis_context(
        db=db,
        request=DanaContextRequest(
            cliente_id=effective_cliente_id,
            attempt_id=attempt_id,
            term=term,
            rodada_id=rodada_id,
            setor_id=setor_id,
            cargo=cargo,
            tipo_aplicacao=tipo_aplicacao,
            status=status,
            date_from=date_from,
            date_to=date_to,
            only_completed=only_completed,
        ),
    )

    messages: list[AIInteractionLog] = []
    cliente_scope_id = (
        context_payload.get("scope", {}).get("cliente_id")
        if isinstance(context_payload, dict)
        else None
    )
    attempt_scope_id = (
        context_payload.get("scope", {}).get("attempt_id")
        if isinstance(context_payload, dict)
        else None
    )

    if cliente_scope_id:
        messages = await _list_history_items(
            db,
            cliente_id=str(cliente_scope_id),
            attempt_id=str(attempt_scope_id) if attempt_scope_id else None,
            limit=limit_messages,
        )

    query_payload = _build_query_payload(
        term=term,
        cliente_id=cliente_id,
        rodada_id=rodada_id,
        setor_id=setor_id,
        cargo=cargo,
        tipo_aplicacao=tipo_aplicacao,
        status=status,
        date_from=date_from,
        date_to=date_to,
        attempt_id=attempt_id,
        only_completed=only_completed,
    )

    return templates.TemplateResponse(
        "ai_analyst/analysis_inteligente_dana.html",
        {
            "request": request,
            "admin": admin,
            "context_payload": context_payload,
            "query": query_payload,
            "messages": messages,
            "csrf_token": request.cookies.get("csrf_token"),
        },
    )


@router.get("/panel", response_class=HTMLResponse)
async def ai_panel(
    request: Request,
    cliente_id: str = Query(...),
    admin=Depends(get_current_admin_ai),
    db: AsyncSession = Depends(get_db),
):
    _ensure_ai_enabled()
    cliente = await _require_cliente_context(db, cliente_id)
    target = f"/admin/ai/analysis-inteligente?cliente_id={cliente.id}"
    return RedirectResponse(url=target, status_code=307)


@router.get("/messages", response_class=HTMLResponse)
async def ai_messages(
    request: Request,
    cliente_id: str = Query(...),
    attempt_id: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    admin=Depends(get_current_admin_ai),
    db: AsyncSession = Depends(get_db),
):
    _ensure_ai_enabled()
    cliente = await _require_cliente_context(db, cliente_id)

    items = await _list_history_items(
        db,
        cliente_id=str(cliente.id),
        attempt_id=attempt_id,
        limit=limit,
    )

    return templates.TemplateResponse(
        "ai_analyst/chat_messages.html",
        {
            "request": request,
            "admin": admin,
            "cliente": cliente,
            "cliente_id": str(cliente.id),
            "attempt_id": attempt_id,
            "messages": items,
        },
    )


@router.get("/history")
async def ai_history(
    cliente_id: str = Query(...),
    attempt_id: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    admin=Depends(get_current_admin_ai),
    db: AsyncSession = Depends(get_db),
):
    _ensure_ai_enabled()
    cliente = await _require_cliente_context(db, cliente_id)

    items = await _list_history_items(
        db,
        cliente_id=str(cliente.id),
        attempt_id=attempt_id,
        limit=limit,
    )

    return {
        "cliente_id": str(cliente.id),
        "attempt_id": attempt_id,
        "count": len(items),
        "items": [_serialize_history_row(item) for item in items],
    }


@router.post("/chat", response_model=AIChatResponse)
async def ai_chat(
    request: Request,
    cliente_id: str = Query(""),
    csrf_token_form: str | None = Form(None, alias="csrf_token"),
    question_form: str | None = Form(None, alias="question"),
    attempt_id_form: str | None = Form(None, alias="attempt_id"),
    filters_active_form: str | None = Form(None, alias="filters_active"),
    comparative_form: str | None = Form(None, alias="comparative"),
    selected_participant_ids_form: str | None = Form(None, alias="selected_participant_ids"),
    docsia_enabled_form: str | None = Form(None, alias="docsia_enabled"),
    comparative_enabled_form: str | None = Form(None, alias="comparative_enabled"),
    search_scope_enabled_form: str | None = Form(None, alias="search_scope_enabled"),
    admin=Depends(get_current_admin_ai),
    db: AsyncSession = Depends(get_db),
):
    _ensure_ai_enabled()

    effective_cliente_id = await _resolve_effective_cliente_id(
        db,
        cliente_id=cliente_id,
        attempt_id=attempt_id_form,
    )
    is_ecosystem_mode = not bool(effective_cliente_id)

    cliente = None if is_ecosystem_mode else await _require_cliente_context(db, effective_cliente_id)

    content_type = (request.headers.get("content-type") or "").lower()
    is_form_submission = (
        "application/x-www-form-urlencoded" in content_type
        or "multipart/form-data" in content_type
    )

    body: AIChatRequest | None = None

    if is_form_submission:
        cookie_csrf = request.cookies.get("csrf_token")
        effective_csrf_token = _clean_text(csrf_token_form)

        if not cookie_csrf or not effective_csrf_token or cookie_csrf != effective_csrf_token:
            raise HTTPException(status_code=403, detail="CSRF validation failed.")

        effective_question_form = _clean_text(question_form)
        effective_attempt_id_form = _clean_text(attempt_id_form)

        if not effective_question_form:
            target = _build_analysis_redirect_url(
                cliente_id=str(cliente.id),
                attempt_id=effective_attempt_id_form,
            )
            return RedirectResponse(url=target, status_code=303)

        try:
            body = AIChatRequest(
                question=effective_question_form,
                attempt_id=effective_attempt_id_form,
                filters_active=_parse_json_dict(filters_active_form),
                comparative=_parse_bool(comparative_form),
                selected_participant_ids=_parse_json_list_of_str(selected_participant_ids_form),
                docsia_enabled=_parse_bool(docsia_enabled_form),
                comparative_enabled=_parse_bool(comparative_enabled_form),
                search_scope_enabled=_parse_bool(search_scope_enabled_form),
            )
        except ValidationError:
            target = _build_analysis_redirect_url(
                cliente_id=str(cliente.id),
                attempt_id=effective_attempt_id_form,
            )
            return RedirectResponse(url=target, status_code=303)
    else:
        try:
            raw_json = await request.json()
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail="Payload JSON inválido para o chat da DANA",
            ) from exc

        if not isinstance(raw_json, dict):
            raise HTTPException(
                status_code=422,
                detail="Payload JSON inválido para o chat da DANA",
            )

        try:
            body = AIChatRequest(**raw_json)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail="Payload invalido para o chat da DANA",
            ) from exc

    if is_ecosystem_mode:
        all_clientes = await list_clientes(db)
        if not all_clientes:
            raise HTTPException(
                status_code=400,
                detail="Nenhum cliente cadastrado. Cadastre um cliente para ativar a DANA.",
            )
        cliente = all_clientes[0]
        effective_cliente_id = str(cliente.id)
        body = AIChatRequest(
            question=(
                "[MODO ECOSSISTEMA — atue como CPO Global do ecossistema completo, "
                "sem cliente específico selecionado. Analise médias e padrões gerais "
                "da base de dados consolidada.]\n\n" + body.question
            ),
            attempt_id=body.attempt_id,
            filters_active=body.filters_active,
            comparative=body.comparative,
            selected_participant_ids=list(body.selected_participant_ids),
            docsia_enabled=body.docsia_enabled,
            comparative_enabled=body.comparative_enabled,
            search_scope_enabled=body.search_scope_enabled,
            bi_context=body.bi_context,
        )

    _bi_ctx_raw = _clean_text(body.bi_context)
    if _bi_ctx_raw:
        _bi_block = (
            "════════════════════════════════════════════════════════════\n"
            "DADOS ATUAIS DA TELA DO ADMINISTRADOR\n"
            "(VERDADE ABSOLUTA DO BANCO DE DADOS — NÃO QUESTIONE ESTES VALORES):\n\n"
            + _bi_ctx_raw
            + "\n\n"
            "USE ESTES NÚMEROS DIRETAMENTE NA SUA RESPOSTA. NÃO AFIRME DESCONHECIMENTO.\n"
            "════════════════════════════════════════════════════════════"
        )
        body = AIChatRequest(
            question=(
                _bi_block
                + "\n\n\n"
                + body.question
            ),
            attempt_id=body.attempt_id,
            filters_active=body.filters_active,
            comparative=body.comparative,
            selected_participant_ids=list(body.selected_participant_ids),
            docsia_enabled=body.docsia_enabled,
            comparative_enabled=body.comparative_enabled,
            search_scope_enabled=body.search_scope_enabled,
            bi_context=None,
        )

    response = await _run_dana_agent(
        db=db,
        admin=admin,
        cliente=cliente,
        body=body,
    )

    if is_form_submission:
        target = _build_analysis_redirect_url(
            cliente_id=effective_cliente_id,
            attempt_id=body.attempt_id,
        )
        return RedirectResponse(url=target, status_code=303)

    return response
