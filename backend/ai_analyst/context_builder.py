from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ai_analyst.ingest.chunker import chunk_extracted_documents
from backend.ai_analyst.ingest.embeddings import build_embedding_records
from backend.ai_analyst.ingest.extractor import extract_docsia_documents
from backend.ai_analyst.ingest.indexer import build_index_from_embeddings
from backend.ai_analyst.search import search_docsia
from backend.bi.services import BIServiceFilters, build_bi_service_payload
from backend.models.attempt import Attempt, Participant
from backend.models.cliente import Cliente, RodadaAplicacao, SetorEmpresa
from backend.models.result import ComputedResult, ReportSnapshot


DOCSIA_RUNTIME_BASE = Path("/app/backend/ai_analyst/docsIA")
DOCSIA_HOST_BASE = Path("/srv/profiledna/backend/ai_analyst/docsIA")
DOCSIA_TOP_K_DEFAULT = 10


@dataclass(slots=True)
class DanaContextRequest:
    cliente_id: str | None = None
    attempt_id: str | None = None
    term: str | None = None
    rodada_id: str | None = None
    setor_id: str | None = None
    cargo: str | None = None
    tipo_aplicacao: str | None = None
    status: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    only_completed: bool = False
    limit_clientes: int = 20
    limit_participantes: int = 50


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_uuid(value: Any) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except Exception:
        return None


def _display_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _participant_display_name(participant: Participant | None) -> str:
    if participant is None:
        return "Participante não identificado"

    nome = _clean_text(getattr(participant, "nome", None))
    sobrenome = _clean_text(getattr(participant, "sobrenome", None))

    full_name = " ".join(part for part in [nome, sobrenome] if part)
    if full_name:
        return full_name

    email = _clean_text(getattr(participant, "email", None))
    if email:
        return email

    return f"Participante {getattr(participant, 'id', '-')}"


def _report_preview(html_content: Any, max_chars: int = 600) -> str | None:
    if html_content is None:
        return None
    text = str(html_content).strip()
    if not text:
        return None
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars].rstrip()}..."


def _cliente_display_name(cliente: Cliente | None) -> str | None:
    if cliente is None:
        return None

    nome = _clean_text(getattr(cliente, "nome", None))
    razao_social = _clean_text(getattr(cliente, "razao_social", None))

    return nome or razao_social or str(getattr(cliente, "id", "-"))


def _human_scope_label(
    *,
    cliente_display_name: str | None,
    participant_display_name: str | None,
) -> str:
    if cliente_display_name and participant_display_name:
        return f"{cliente_display_name} • {participant_display_name}"
    if cliente_display_name:
        return cliente_display_name
    if participant_display_name:
        return participant_display_name
    return "Escopo não definido"


def _json_safe(value: Any):
    """
    Serializa objetos heterogêneos do contexto DANA para estruturas JSON-safe.
    Compatível com Pydantic v1/v2, dataclasses simples, objetos com __dict__,
    UUID, datetime/date, Decimal, listas, tuplas, sets e dicts.
    """
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, uuid.UUID):
        return str(value)

    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]

    if is_dataclass(value):
        return _json_safe(asdict(value))

    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump(mode="json"))

    if hasattr(value, "dict"):
        return _json_safe(value.dict())

    if hasattr(value, "__dict__"):
        return {
            str(k): _json_safe(v)
            for k, v in vars(value).items()
            if not str(k).startswith("_")
        }

    return str(value)


async def _load_cliente(
    db: AsyncSession,
    *,
    cliente_id: str | None,
) -> Cliente | None:
    cliente_uuid = _safe_uuid(cliente_id)
    if not cliente_uuid:
        return None

    result = await db.execute(
        select(Cliente).where(Cliente.id == cliente_uuid)
    )
    return result.scalar_one_or_none()


async def _load_rodadas_cliente(
    db: AsyncSession,
    *,
    cliente_id: str | None,
) -> list[RodadaAplicacao]:
    cliente_uuid = _safe_uuid(cliente_id)
    if not cliente_uuid:
        return []

    result = await db.execute(
        select(RodadaAplicacao)
        .where(RodadaAplicacao.cliente_id == cliente_uuid)
        .order_by(RodadaAplicacao.nome.asc())
    )
    return list(result.scalars().all())


async def _load_setores_cliente(
    db: AsyncSession,
    *,
    cliente_id: str | None,
) -> list[SetorEmpresa]:
    cliente_uuid = _safe_uuid(cliente_id)
    if not cliente_uuid:
        return []

    result = await db.execute(
        select(SetorEmpresa)
        .where(SetorEmpresa.cliente_id == cliente_uuid)
        .order_by(SetorEmpresa.nome.asc())
    )
    return list(result.scalars().all())


async def build_cliente_header_context(
    db: AsyncSession,
    *,
    cliente_id: str | None,
) -> dict[str, Any]:
    """
    Carrega o cliente em contexto, já com nome humano e listas auxiliares
    para filtros complementares (rodadas e setores).
    """
    if not cliente_id:
        return {
            "has_cliente": False,
            "cliente_fixed": False,
            "display_name": None,
            "cliente": None,
            "rodadas": [],
            "setores": [],
        }

    cliente = await _load_cliente(db, cliente_id=cliente_id)
    if cliente is None:
        return {
            "has_cliente": False,
            "cliente_fixed": True,
            "display_name": None,
            "cliente": None,
            "rodadas": [],
            "setores": [],
        }

    rodadas = await _load_rodadas_cliente(db, cliente_id=cliente_id)
    setores = await _load_setores_cliente(db, cliente_id=cliente_id)

    cliente_payload = {
        "id": str(getattr(cliente, "id", "")),
        "nome": _clean_text(getattr(cliente, "nome", None)),
        "display_name": _cliente_display_name(cliente),
        "razao_social": _clean_text(getattr(cliente, "razao_social", None)),
        "cnpj": _clean_text(getattr(cliente, "cnpj", None)),
        "endereco": _clean_text(getattr(cliente, "endereco", None)),
        "setor_mercado": _clean_text(getattr(cliente, "setor_mercado", None)),
        "responsavel": _clean_text(getattr(cliente, "responsavel", None)),
        "setor_responsavel": _clean_text(getattr(cliente, "setor_responsavel", None)),
        "email_responsavel": _clean_text(getattr(cliente, "email_responsavel", None)),
        "ativo": bool(getattr(cliente, "ativo", False)),
        "criado_em": _display_datetime(getattr(cliente, "criado_em", None)),
    }

    rodadas_payload = [
        {
            "id": str(getattr(item, "id", "")),
            "nome": _clean_text(getattr(item, "nome", None)),
            "data_inicio": _display_datetime(getattr(item, "data_inicio", None)),
            "data_encerramento": _display_datetime(getattr(item, "data_encerramento", None)),
        }
        for item in rodadas
    ]

    setores_payload = [
        {
            "id": str(getattr(item, "id", "")),
            "nome": _clean_text(getattr(item, "nome", None)),
        }
        for item in setores
    ]

    return {
        "has_cliente": True,
        "cliente_fixed": True,
        "display_name": cliente_payload["display_name"],
        "cliente": cliente_payload,
        "rodadas": rodadas_payload,
        "setores": setores_payload,
    }


async def build_attempt_context(
    db: AsyncSession,
    *,
    attempt_id: str | None,
    cliente_id: str | None = None,
) -> dict[str, Any]:
    """
    Carrega o participante selecionado e seus artefatos oficiais:
    - attempt
    - computed_result
    - report_snapshot
    """
    attempt_uuid = _safe_uuid(attempt_id)
    cliente_uuid = _safe_uuid(cliente_id)

    if not attempt_uuid:
        return {
            "has_attempt": False,
            "display_name": None,
            "participant": None,
            "attempt": None,
            "computed_result": None,
            "report_snapshot": None,
        }

    attempt_stmt = select(Attempt).where(Attempt.id == attempt_uuid)
    if cliente_uuid:
        attempt_stmt = attempt_stmt.where(Attempt.cliente_id == cliente_uuid)

    attempt_result = await db.execute(attempt_stmt)
    attempt = attempt_result.scalar_one_or_none()

    if attempt is None:
        return {
            "has_attempt": False,
            "display_name": None,
            "participant": None,
            "attempt": None,
            "computed_result": None,
            "report_snapshot": None,
        }

    participant = None
    participant_id = getattr(attempt, "participant_id", None)
    if participant_id is not None:
        participant_result = await db.execute(
            select(Participant).where(Participant.id == participant_id)
        )
        participant = participant_result.scalar_one_or_none()

    computed_result_obj = None
    computed_result_result = await db.execute(
        select(ComputedResult).where(ComputedResult.attempt_id == attempt.id)
    )
    computed_result_obj = computed_result_result.scalar_one_or_none()

    report_snapshot_obj = None
    report_snapshot_result = await db.execute(
        select(ReportSnapshot).where(ReportSnapshot.attempt_id == attempt.id)
    )
    report_snapshot_obj = report_snapshot_result.scalar_one_or_none()

    participant_payload = {
        "id": str(getattr(participant, "id", "")) if participant is not None else None,
        "display_name": _participant_display_name(participant) if participant is not None else None,
        "nome": _clean_text(getattr(participant, "nome", None)) if participant is not None else None,
        "sobrenome": _clean_text(getattr(participant, "sobrenome", None)) if participant is not None else None,
        "email": _clean_text(getattr(participant, "email", None)) if participant is not None else None,
        "tipo_aplicacao": _clean_text(getattr(participant, "tipo_aplicacao", None)) if participant is not None else None,
        "empresa_nome": _clean_text(getattr(participant, "empresa_nome", None)) if participant is not None else None,
    }

    attempt_payload = {
        "id": str(getattr(attempt, "id", "")),
        "cliente_id": str(getattr(attempt, "cliente_id", "")) if getattr(attempt, "cliente_id", None) else None,
        "rodada_id": str(getattr(attempt, "rodada_id", "")) if getattr(attempt, "rodada_id", None) else None,
        "setor_id": str(getattr(attempt, "setor_id", "")) if getattr(attempt, "setor_id", None) else None,
        "cargo": _clean_text(getattr(attempt, "cargo", None)),
        "status": _clean_text(getattr(attempt, "status", None)),
        "progress": getattr(attempt, "progress", 0),
        "data_inicio": _display_datetime(getattr(attempt, "data_inicio", None)),
        "data_conclusao": _display_datetime(getattr(attempt, "data_conclusao", None)),
    }

    computed_result_payload = None
    if computed_result_obj is not None:
        computed_result_payload = {
            "id": str(getattr(computed_result_obj, "id", "")),
            "attempt_id": str(getattr(computed_result_obj, "attempt_id", "")),
            "scores": _json_safe(getattr(computed_result_obj, "scores", {})),
            "bands": _json_safe(getattr(computed_result_obj, "bands", {})),
            "top3": _json_safe(getattr(computed_result_obj, "top3", [])),
            "top5": _json_safe(getattr(computed_result_obj, "top5", [])),
            "bottom3": _json_safe(getattr(computed_result_obj, "bottom3", [])),
            "interpretations": _json_safe(getattr(computed_result_obj, "interpretations", {})),
            "premium_data": _json_safe(getattr(computed_result_obj, "premium_data", {})),
            "created_at": _display_datetime(getattr(computed_result_obj, "created_at", None)),
        }

    report_snapshot_payload = None
    if report_snapshot_obj is not None:
        html_content = getattr(report_snapshot_obj, "html_content", None)
        report_snapshot_payload = {
            "id": str(getattr(report_snapshot_obj, "id", "")),
            "attempt_id": str(getattr(report_snapshot_obj, "attempt_id", "")),
            "html_content": html_content,
            "preview": _report_preview(html_content),
            "created_at": _display_datetime(getattr(report_snapshot_obj, "created_at", None)),
        }

    return {
        "has_attempt": True,
        "display_name": participant_payload["display_name"],
        "participant": participant_payload,
        "attempt": attempt_payload,
        "computed_result": computed_result_payload,
        "report_snapshot": report_snapshot_payload,
    }


async def build_bi_context(
    db: AsyncSession,
    *,
    cliente_id: str | None,
    rodada_id: str | None = None,
    setor_id: str | None = None,
    cargo: str | None = None,
    tipo_aplicacao: str | None = None,
    status: str | None = None,
    only_completed: bool = False,
) -> dict[str, Any]:
    """
    Monta o bloco de BI oficial do recorte atual.
    """
    if not cliente_id:
        return {
            "has_bi_context": False,
            "filters": {},
            "payload": None,
        }

    filters = BIServiceFilters(
        cliente_id=_clean_text(cliente_id),
        rodada_id=_clean_text(rodada_id),
        setor_id=_clean_text(setor_id),
        cargo=_clean_text(cargo),
        tipo_aplicacao=_clean_text(tipo_aplicacao),
        attempt_status=_clean_text(status),
        only_completed=bool(only_completed),
    )

    payload = await build_bi_service_payload(db, filters=filters)

    return {
        "has_bi_context": True,
        "filters": {
            "cliente_id": _clean_text(cliente_id),
            "rodada_id": _clean_text(rodada_id),
            "setor_id": _clean_text(setor_id),
            "cargo": _clean_text(cargo),
            "tipo_aplicacao": _clean_text(tipo_aplicacao),
            "status": _clean_text(status),
            "only_completed": bool(only_completed),
        },
        "payload": _json_safe(payload),
    }


def _build_participant_options(search_payload: dict[str, Any]) -> list[dict[str, Any]]:
    participantes = search_payload.get("participantes", []) or []
    options: list[dict[str, Any]] = []

    for item in participantes:
        attempt_id = _clean_text(item.get("attempt_id"))
        participant_name = (
            _clean_text(item.get("participant_display_name"))
            or _clean_text(item.get("participant_name"))
            or "Participante"
        )
        cargo = _clean_text(item.get("cargo"))
        status = _clean_text(item.get("status"))

        label_parts = [participant_name]
        if cargo:
            label_parts.append(cargo)
        if status:
            label_parts.append(status)

        options.append(
            {
                "value": attempt_id,
                "label": " • ".join(label_parts),
                "participant_display_name": participant_name,
                "attempt_id": attempt_id,
                "status": status,
                "cargo": cargo,
            }
        )

    return options


def _normalize_search_block(
    *,
    search_payload: dict[str, Any],
    cliente_context: dict[str, Any],
    cliente_fixed: bool,
) -> dict[str, Any]:
    """
    Em modo cliente fixo:
    - mantém apenas o cliente em contexto no eixo de clientes;
    - preserva apenas participantes daquele cliente já retornados pelo payload estrutural;
    - expõe lista de opções de participante para o template final.
    """
    payload = dict(search_payload or {})
    payload["mode"] = "cliente_fixed" if cliente_fixed else "global"

    clientes = payload.get("clientes", []) or []
    participantes = payload.get("participantes", []) or []

    if cliente_fixed and cliente_context.get("has_cliente") and cliente_context.get("cliente"):
        payload["clientes"] = [cliente_context["cliente"]]
    else:
        payload["clientes"] = clientes

    payload["participantes"] = participantes
    payload["participant_options"] = _build_participant_options(payload)

    meta = payload.get("meta", {}) or {}
    meta["search_clientes"] = len(payload["clientes"])
    meta["search_participantes"] = len(payload["participantes"])
    meta["mode"] = payload["mode"]
    payload["meta"] = meta

    return payload


def _build_attempt_entry_from_context(attempt_context: dict[str, Any]) -> dict[str, Any] | None:
    participant_payload = attempt_context.get("participant")
    attempt_payload = attempt_context.get("attempt")

    if not isinstance(participant_payload, dict) or not isinstance(attempt_payload, dict):
        return None

    attempt_id = _clean_text(attempt_payload.get("id"))
    if not attempt_id:
        return None

    participant_display_name = (
        _clean_text(participant_payload.get("display_name"))
        or "Participante"
    )

    return {
        "attempt_id": attempt_id,
        "participant_id": _clean_text(participant_payload.get("id")),
        "participant_display_name": participant_display_name,
        "participant_name": participant_display_name,
        "cargo": _clean_text(attempt_payload.get("cargo")),
        "status": _clean_text(attempt_payload.get("status")),
        "cliente_id": _clean_text(attempt_payload.get("cliente_id")),
        "rodada_id": _clean_text(attempt_payload.get("rodada_id")),
        "setor_id": _clean_text(attempt_payload.get("setor_id")),
        "tipo_aplicacao": _clean_text(participant_payload.get("tipo_aplicacao")),
        "empresa_nome": _clean_text(participant_payload.get("empresa_nome")),
    }


async def _load_structural_participants(
    db: AsyncSession,
    *,
    request: DanaContextRequest,
) -> list[dict[str, Any]]:
    """
    Carrega a lista estrutural de participantes/attempts do painel.

    Regras:
    - esta função substitui a dependência indevida da docsIA para povoar a UI;
    - preserva filtros essenciais do painel;
    - não interfere no bloco docsia.
    """
    stmt = (
        select(Attempt, Participant)
        .outerjoin(Participant, Participant.id == Attempt.participant_id)
    )

    cliente_uuid = _safe_uuid(request.cliente_id)
    rodada_uuid = _safe_uuid(request.rodada_id)
    setor_uuid = _safe_uuid(request.setor_id)

    if cliente_uuid:
        stmt = stmt.where(Attempt.cliente_id == cliente_uuid)

    if rodada_uuid:
        stmt = stmt.where(Attempt.rodada_id == rodada_uuid)

    if setor_uuid:
        stmt = stmt.where(Attempt.setor_id == setor_uuid)

    cargo_filter = _clean_text(request.cargo)
    if cargo_filter:
        stmt = stmt.where(Attempt.cargo.ilike(f"%{cargo_filter}%"))

    status_filter = _clean_text(request.status)
    if status_filter:
        stmt = stmt.where(Attempt.status == status_filter)

    tipo_aplicacao_filter = _clean_text(request.tipo_aplicacao)
    if tipo_aplicacao_filter:
        stmt = stmt.where(Participant.tipo_aplicacao == tipo_aplicacao_filter)

    if bool(request.only_completed):
        stmt = stmt.where(Attempt.data_conclusao.is_not(None))

    term = _clean_text(request.term)
    if term:
        pattern = f"%{term}%"
        stmt = stmt.where(
            or_(
                Participant.nome.ilike(pattern),
                Participant.sobrenome.ilike(pattern),
                Participant.email.ilike(pattern),
                Participant.empresa_nome.ilike(pattern),
                Attempt.cargo.ilike(pattern),
            )
        )

    limit_participantes = max(int(request.limit_participantes or 50), 1)

    stmt = stmt.order_by(
        Attempt.data_inicio.desc(),
        Attempt.id.desc(),
    ).limit(limit_participantes)

    result = await db.execute(stmt)
    rows = result.all()

    participants: list[dict[str, Any]] = []
    seen_attempt_ids: set[str] = set()

    for attempt, participant in rows:
        attempt_id = _clean_text(getattr(attempt, "id", None))
        if not attempt_id or attempt_id in seen_attempt_ids:
            continue

        seen_attempt_ids.add(attempt_id)

        participant_display_name = (
            _participant_display_name(participant)
            if participant is not None
            else "Participante não identificado"
        )

        participants.append(
            {
                "attempt_id": attempt_id,
                "participant_id": (
                    _clean_text(getattr(participant, "id", None))
                    if participant is not None
                    else None
                ),
                "participant_display_name": participant_display_name,
                "participant_name": participant_display_name,
                "cargo": _clean_text(getattr(attempt, "cargo", None)),
                "status": _clean_text(getattr(attempt, "status", None)),
                "cliente_id": _clean_text(getattr(attempt, "cliente_id", None)),
                "rodada_id": _clean_text(getattr(attempt, "rodada_id", None)),
                "setor_id": _clean_text(getattr(attempt, "setor_id", None)),
                "tipo_aplicacao": (
                    _clean_text(getattr(participant, "tipo_aplicacao", None))
                    if participant is not None
                    else None
                ),
                "empresa_nome": (
                    _clean_text(getattr(participant, "empresa_nome", None))
                    if participant is not None
                    else None
                ),
            }
        )

    return participants


async def _build_structural_search_payload(
    db: AsyncSession,
    *,
    cliente_context: dict[str, Any],
    attempt_context: dict[str, Any],
    request: DanaContextRequest,
) -> dict[str, Any]:
    """
    Monta o bloco search do painel em formato seguro e compatível com o template,
    sem depender do módulo de busca docsIA.

    Observação:
    - este bloco representa o contexto estrutural do painel/admin;
    - docsIA fica em bloco próprio e separado.
    """
    clientes: list[dict[str, Any]] = []
    participante_entries = await _load_structural_participants(
        db,
        request=request,
    )

    cliente_payload = cliente_context.get("cliente")
    if isinstance(cliente_payload, dict) and cliente_payload:
        clientes.append(cliente_payload)

    selected_entry = _build_attempt_entry_from_context(attempt_context)
    if selected_entry is not None:
        selected_attempt_id = selected_entry["attempt_id"]
        if all(item.get("attempt_id") != selected_attempt_id for item in participante_entries):
            participante_entries.insert(0, selected_entry)

    return {
        "clientes": clientes,
        "participantes": participante_entries,
        "meta": {
            "mode": "cliente_fixed" if _clean_text(request.cliente_id) else "global",
            "term": _clean_text(request.term),
            "search_clientes": len(clientes),
            "search_participantes": len(participante_entries),
            "source": "structural_context_db",
        },
    }


def _resolve_docsia_runtime_path() -> Path:
    if DOCSIA_RUNTIME_BASE.exists() and DOCSIA_RUNTIME_BASE.is_dir():
        return DOCSIA_RUNTIME_BASE
    if DOCSIA_HOST_BASE.exists() and DOCSIA_HOST_BASE.is_dir():
        return DOCSIA_HOST_BASE
    return DOCSIA_RUNTIME_BASE


def build_docsia_context(
    *,
    term: str | None,
    allowed_themes: list[str] | None = None,
    top_k: int = DOCSIA_TOP_K_DEFAULT,
) -> dict[str, Any]:
    """
    Executa a busca docsIA de forma isolada e resiliente.

    Regras:
    - nunca quebra a tela da DANA;
    - só usa documentos approved já validados;
    - usa pipeline real validado: extractor -> chunker -> embeddings -> indexer -> search;
    - retorna payload JSON-safe e auditável.
    """
    normalized_term = _clean_text(term)

    if not normalized_term:
        return {
            "enabled": True,
            "query": "",
            "matches_returned": 0,
            "matches": [],
            "errors": [],
            "warnings": [],
            "meta": {
                "source": "docsia",
                "executed": False,
                "reason": "empty_term",
            },
        }

    try:
        docsia_path = _resolve_docsia_runtime_path()

        extract_report = extract_docsia_documents(docsia_path)
        if not extract_report.is_valid:
            return {
                "enabled": True,
                "query": normalized_term,
                "matches_returned": 0,
                "matches": [],
                "errors": [asdict(item) for item in extract_report.errors],
                "warnings": [asdict(item) for item in extract_report.warnings],
                "meta": {
                    "source": "docsia",
                    "executed": True,
                    "stage": "extractor",
                    "is_valid": False,
                    "documents_extracted": extract_report.documents_extracted,
                },
            }

        chunk_report = chunk_extracted_documents(extract_report.extracted_documents)
        if not chunk_report.is_valid:
            return {
                "enabled": True,
                "query": normalized_term,
                "matches_returned": 0,
                "matches": [],
                "errors": [asdict(item) for item in chunk_report.errors],
                "warnings": [asdict(item) for item in chunk_report.warnings],
                "meta": {
                    "source": "docsia",
                    "executed": True,
                    "stage": "chunker",
                    "is_valid": False,
                    "documents_chunked": chunk_report.documents_chunked,
                    "chunks_created": chunk_report.chunks_created,
                },
            }

        embedding_report = build_embedding_records(chunk_report.chunks)
        if not embedding_report.is_valid:
            return {
                "enabled": True,
                "query": normalized_term,
                "matches_returned": 0,
                "matches": [],
                "errors": [asdict(item) for item in embedding_report.errors],
                "warnings": [asdict(item) for item in embedding_report.warnings],
                "meta": {
                    "source": "docsia",
                    "executed": True,
                    "stage": "embeddings",
                    "is_valid": False,
                    "chunks_received": embedding_report.chunks_received,
                    "embeddings_created": embedding_report.embeddings_created,
                },
            }

        index_report = build_index_from_embeddings(embedding_report.embeddings)
        if not index_report.is_valid:
            return {
                "enabled": True,
                "query": normalized_term,
                "matches_returned": 0,
                "matches": [],
                "errors": [asdict(item) for item in index_report.errors],
                "warnings": [asdict(item) for item in index_report.warnings],
                "meta": {
                    "source": "docsia",
                    "executed": True,
                    "stage": "indexer",
                    "is_valid": False,
                    "indexed_documents": index_report.indexed_documents,
                    "indexed_chunks": index_report.indexed_chunks,
                    "index_entries_created": index_report.index_entries_created,
                },
            }

        search_report = search_docsia(
            query=normalized_term,
            index_entries=index_report.index_entries,
            top_k=max(int(top_k), 1),
            allowed_themes=list(allowed_themes or []),
        )

        return {
            "enabled": True,
            "query": normalized_term,
            "matches_returned": search_report.matches_returned,
            "matches": [asdict(item) for item in search_report.matches],
            "errors": [asdict(item) for item in search_report.errors],
            "warnings": [asdict(item) for item in search_report.warnings],
            "meta": {
                "source": "docsia",
                "executed": True,
                "is_valid": search_report.is_valid,
                "documents_extracted": extract_report.documents_extracted,
                "chunks_created": chunk_report.chunks_created,
                "embeddings_created": embedding_report.embeddings_created,
                "index_entries_created": index_report.index_entries_created,
                "allowed_themes": list(allowed_themes or []),
            },
        }

    except Exception as exc:
        return {
            "enabled": True,
            "query": normalized_term,
            "matches_returned": 0,
            "matches": [],
            "errors": [
                {
                    "code": "docsia_context_build_failed",
                    "message": str(exc),
                    "context": {},
                }
            ],
            "warnings": [],
            "meta": {
                "source": "docsia",
                "executed": True,
                "is_valid": False,
                "stage": "unexpected_exception",
            },
        }


async def build_analysis_context(
    db: AsyncSession,
    *,
    request: DanaContextRequest,
) -> dict[str, Any]:
    """
    Monta o payload consolidado do painel da página
    'Análise Inteligente Dana'.

    Em modo cliente fixo (quando há cliente_id), o contexto passa a ser
    centrado no cliente selecionado:
    - cliente humano em destaque
    - participante individual selecionado
    - resultado oficial individual
    - BI oficial do recorte do cliente
    - enriquecimento documental docsIA em bloco separado
    """
    cliente_fixed = bool(_clean_text(request.cliente_id))

    cliente_context = await build_cliente_header_context(
        db,
        cliente_id=request.cliente_id,
    )

    attempt_context = await build_attempt_context(
        db,
        attempt_id=request.attempt_id,
        cliente_id=request.cliente_id,
    )

    search_payload_raw = await _build_structural_search_payload(
        db,
        cliente_context=cliente_context,
        attempt_context=attempt_context,
        request=request,
    )

    search_payload = _normalize_search_block(
        search_payload=search_payload_raw,
        cliente_context=cliente_context,
        cliente_fixed=cliente_fixed,
    )

    bi_context = await build_bi_context(
        db,
        cliente_id=request.cliente_id,
        rodada_id=request.rodada_id,
        setor_id=request.setor_id,
        cargo=request.cargo,
        tipo_aplicacao=request.tipo_aplicacao,
        status=request.status,
        only_completed=request.only_completed,
    )

    docsia_context = build_docsia_context(
        term=request.term,
        allowed_themes=[],
        top_k=min(max(int(request.limit_participantes or DOCSIA_TOP_K_DEFAULT), 1), 20),
    )

    cliente_display_name = cliente_context.get("display_name")
    participant_display_name = attempt_context.get("display_name")

    computed_result_payload = attempt_context.get("computed_result")
    report_snapshot_payload = attempt_context.get("report_snapshot")

    scope = {
        "mode": "cliente_fixed" if cliente_fixed else "global",
        "cliente_fixed": cliente_fixed,
        "cliente_id": _clean_text(request.cliente_id),
        "cliente_display_name": cliente_display_name,
        "participante_id": (
            attempt_context.get("participant", {}) or {}
        ).get("id"),
        "participante_display_name": participant_display_name,
        "attempt_id": _clean_text(request.attempt_id),
        "term": _clean_text(request.term),
        "rodada_id": _clean_text(request.rodada_id),
        "setor_id": _clean_text(request.setor_id),
        "cargo": _clean_text(request.cargo),
        "tipo_aplicacao": _clean_text(request.tipo_aplicacao),
        "status": _clean_text(request.status),
        "date_from": _clean_text(request.date_from),
        "date_to": _clean_text(request.date_to),
        "only_completed": bool(request.only_completed),
        "display_label": _human_scope_label(
            cliente_display_name=cliente_display_name,
            participant_display_name=participant_display_name,
        ),
    }

    meta = {
        "mode": "cliente_fixed" if cliente_fixed else "global",
        "cliente_fixed": cliente_fixed,
        "search_clientes": len(search_payload.get("clientes", []) or []),
        "search_participantes": len(search_payload.get("participantes", []) or []),
        "cliente_display_name": cliente_display_name,
        "participante_display_name": participant_display_name,
        "has_computed_result": bool(computed_result_payload),
        "has_report_snapshot": bool(report_snapshot_payload),
        "has_bi_context": bool(bi_context.get("has_bi_context")),
        "has_docsia_context": bool(docsia_context.get("enabled")),
        "docsia_matches_returned": int(docsia_context.get("matches_returned") or 0),
    }

    return {
        "scope": scope,
        "search": search_payload,
        "cliente": cliente_context,
        "attempt": {
            "has_attempt": bool(attempt_context.get("has_attempt")),
            "display_name": participant_display_name,
            "participant": attempt_context.get("participant"),
            "attempt": attempt_context.get("attempt"),
        },
        "computed_result": {
            "has_computed_result": bool(computed_result_payload),
            "payload": computed_result_payload,
        },
        "report_snapshot": {
            "has_report_snapshot": bool(report_snapshot_payload),
            "payload": report_snapshot_payload,
        },
        "bi": bi_context,
        "docsia": docsia_context,
        "meta": meta,
    }
