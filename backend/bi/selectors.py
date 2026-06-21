from __future__ import annotations

import json
from dataclasses import dataclass
from statistics import mean, median
from typing import Any, Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models.attempt import Attempt
from backend.models.cliente import Cliente, RodadaAplicacao, SetorEmpresa
from backend.models.result import ComputedResult

CANONICAL_DIMENSION_AREA_BI: dict[str, str] = {
    "A": "GERENCIAL",
    "B": "GERENCIAL",
    "C": "GERENCIAL",
    "D": "GERENCIAL",
    "E": "INTER PESSOAL",
    "F": "GERENCIAL",
    "G": "PESSOAL",
    "H": "PESSOAL",
    "I": "PESSOAL",
    "J": "GERENCIAL",
    "K": "PESSOAL",
    "L": "GERENCIAL",
    "M": "INTER PESSOAL",
    "N": "INTER PESSOAL",
    "O": "PESSOAL",
    "P": "INTER PESSOAL",
    "Q": "PESSOAL",
    "R": "PESSOAL",
    "S": "INTER PESSOAL",
    "T": "PESSOAL",
}


def _safe_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).strip().replace(",", ".")
    if not raw:
        return None
    try:
        return float(raw)
    except Exception:
        return None


def _canonical_area_for_dimension(dimension_key: str) -> str | None:
    key = _safe_str(dimension_key).upper()
    return CANONICAL_DIMENSION_AREA_BI.get(key)


def _band_from_score(score: float | None) -> str | None:
    if score is None:
        return None
    if score <= 3:
        return "low"
    if score <= 6:
        return "mid"
    return "high"


@dataclass(slots=True)
class BISelectorFilters:
    cliente_id: UUID | str | None = None
    rodada_id: UUID | str | None = None
    setor_id: UUID | str | None = None
    cargo: str | None = None
    tipo_aplicacao: str | None = None
    attempt_status: str | None = None
    only_completed: bool = False
    limit: int = 5000


@dataclass(slots=True)
class BIAttemptRow:
    attempt_id: str
    cliente_id: str | None
    cliente_nome: str | None
    rodada_id: str | None
    rodada_nome: str | None
    setor_id: str | None
    setor_nome: str | None
    participant_nome: str | None
    participant_email: str | None
    empresa_nome: str | None
    tipo_aplicacao: str | None
    cargo: str | None
    status: str | None
    progress: int | None
    data_inicio: str | None
    data_conclusao: str | None
    computed_result: ComputedResult | None



@dataclass(slots=True)
class BIDimensionAggregate:
    dimension_key: str
    dimension_label: str
    area: str | None
    count: int
    average_score: float | None
    median_score: float | None
    low_count: int
    mid_count: int
    high_count: int


@dataclass(slots=True)
class BIAreaAggregate:
    area: str
    count_dimensions: int
    average_score: float | None


# ============================================================
# HELPERS INTERNOS
# ============================================================


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_text_filter(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_payload(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, (dict, list)):
        return value

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    return None


def _extract_participant(attempt: Attempt) -> Any:
    return getattr(attempt, "participant", None)


def _extract_dimension_payload(computed_result: ComputedResult | None) -> dict[str, Any]:
    """
    Tenta localizar o payload persistido com as 20 dimensões do relatório.

    Esta função é tolerante a variações de nome interno, porque o BI ainda está
    sendo iniciado e não devemos acoplar a uma única convenção antes de auditar
    toda a cadeia de persistência.
    """
    if computed_result is None:
        return {}

    candidates = [
        "dimensions",
        "dimensoes",
        "dimension_results",
        "dimensions_result",
        "scores",
        "score_payload",
        "scores_payload",
        "scores_by_dimension",
        "score_by_dimension",
        "result_payload",
        "payload",
        "report_payload",
        "computed_payload",
    ]

    for attr_name in candidates:
        raw = getattr(computed_result, attr_name, None)
        payload = _normalize_payload(raw)
        if isinstance(payload, dict) and payload:
            if _looks_like_dimension_map(payload):
                return payload

    # fallback: varrer atributos conhecidos do objeto
    for attr_name in dir(computed_result):
        if attr_name.startswith("_"):
            continue
        if attr_name in {"metadata", "registry"}:
            continue
        try:
            raw = getattr(computed_result, attr_name)
        except Exception:
            continue
        payload = _normalize_payload(raw)
        if isinstance(payload, dict) and payload and _looks_like_dimension_map(payload):
            return payload

    return {}


def _looks_like_dimension_map(payload: dict[str, Any]) -> bool:
    """
    Detecta mapas no formato A..T ou estruturas equivalentes.
    """
    uppercase_keys = {str(k).strip().upper() for k in payload.keys() if str(k).strip()}
    expected = set("ABCDEFGHIJKLMNOPQRST")

    if uppercase_keys & expected:
        return True

    # payload aninhado
    nested_candidates = [
        payload.get("dimensions"),
        payload.get("dimensoes"),
        payload.get("scores"),
        payload.get("items"),
        payload.get("results"),
    ]
    for item in nested_candidates:
        if isinstance(item, dict):
            nested_keys = {str(k).strip().upper() for k in item.keys() if str(k).strip()}
            if nested_keys & expected:
                return True

    return False


def _unwrap_dimension_map(payload: dict[str, Any]) -> dict[str, Any]:
    uppercase_keys = {str(k).strip().upper() for k in payload.keys() if str(k).strip()}
    expected = set("ABCDEFGHIJKLMNOPQRST")

    if uppercase_keys & expected:
        return payload

    for key in ["dimensions", "dimensoes", "scores", "items", "results"]:
        nested = payload.get(key)
        if isinstance(nested, dict):
            nested_keys = {str(k).strip().upper() for k in nested.keys() if str(k).strip()}
            if nested_keys & expected:
                return nested

    return {}


def _extract_dimension_label(dimension_key: str, payload: Any) -> str:
    if isinstance(payload, dict):
        for key in [
            "label",
            "nome",
            "name",
            "dimension_label",
            "titulo",
            "title",
        ]:
            value = _safe_str(payload.get(key))
            if value:
                return value

    return dimension_key


def _extract_dimension_area(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None

    for key in ["area", "grupo", "group", "categoria", "category"]:
        value = _safe_str(payload.get(key))
        if value:
            return value.upper()

    return None


def _extract_dimension_score(payload: Any) -> float | None:
    if not isinstance(payload, dict):
        return None

    for key in ["score", "valor", "value", "points", "pontuacao"]:
        raw = payload.get(key)
        if raw is None:
            continue
        try:
            return float(raw)
        except Exception:
            continue

    return None


def _extract_dimension_band(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None

    for key in ["band", "faixa", "range"]:
        value = _safe_str(payload.get(key))
        if value:
            normalized = value.strip().lower()
            if normalized in {"low", "baixo"}:
                return "low"
            if normalized in {"mid", "medio", "médio"}:
                return "mid"
            if normalized in {"high", "alto"}:
                return "high"

    score = _extract_dimension_score(payload)
    if score is None:
        return None
    if score <= 3:
        return "low"
    if score <= 6:
        return "mid"
    return "high"


def _extract_ranking_list(
    computed_result: ComputedResult | None,
    *,
    attr_name: str,
    nested_key: str,
) -> list[str]:
    if computed_result is None:
        return []

    raw = getattr(computed_result, attr_name, None)
    payload = _normalize_payload(raw)

    if isinstance(payload, dict):
        data = payload.get(nested_key, [])
    elif isinstance(payload, list):
        data = payload
    else:
        data = []

    result: list[str] = []
    for item in data:
        if isinstance(item, dict):
            key = _safe_str(
                item.get("dimension")
                or item.get("key")
                or item.get("sigla")
                or item.get("code")
                or item.get("id")
            )
            label = _safe_str(
                item.get("label")
                or item.get("name")
                or item.get("nome")
                or item.get("dimension_label")
            )
            if key and label:
                result.append(f"{key} — {label}")
                continue
            if key:
                result.append(key)
                continue
            if label:
                result.append(label)
                continue

        text = _safe_str(item)
        if text:
            result.append(text)

    return result



def _extract_dimension_items(computed_result: ComputedResult | None) -> list[dict[str, Any]]:
    if computed_result is None:
        return []

    raw_scores = getattr(computed_result, "scores", None)
    raw_bands = getattr(computed_result, "bands", None)

    scores_payload = _normalize_payload(raw_scores)
    bands_payload = _normalize_payload(raw_bands)

    if not isinstance(scores_payload, dict):
        return []

    rows: list[dict[str, Any]] = []

    for raw_key, raw_score in scores_payload.items():
        key = _safe_str(raw_key)
        if not key:
            continue

        dimension_key = key.upper()
        dimension_label = dimension_key

        score: float | None = None
        area: str | None = None
        band: str | None = None

        if isinstance(raw_score, dict):
            score = _safe_optional_float(
                raw_score.get("score")
                or raw_score.get("value")
                or raw_score.get("media")
                or raw_score.get("average")
                or raw_score.get("avg")
            )
            area = _safe_str(
                raw_score.get("area")
                or raw_score.get("macro_area")
                or raw_score.get("group")
                or raw_score.get("group_area")
            ) or None
            dimension_label = _safe_str(
                raw_score.get("label")
                or raw_score.get("dimension_label")
                or raw_score.get("name")
            ) or dimension_key
        else:
            score = _safe_optional_float(raw_score)

        if isinstance(bands_payload, dict):
            raw_band = bands_payload.get(dimension_key)
            if isinstance(raw_band, dict):
                band = _safe_str(
                    raw_band.get("band")
                    or raw_band.get("faixa")
                    or raw_band.get("value")
                ) or None
            else:
                band = _safe_str(raw_band) or None

        if not area:
            area = _canonical_area_for_dimension(dimension_key)

        if not band:
            band = _band_from_score(score)

        rows.append(
            {
                "dimension_key": dimension_key,
                "dimension_label": dimension_label,
                "area": area,
                "score": score,
                "band": band,
            }
        )

    rows.sort(key=lambda item: item["dimension_key"])
    return rows


async def _load_context_labels(
    session: AsyncSession,
    rows: list[BIAttemptRow],
) -> list[BIAttemptRow]:
    cliente_ids = {row.cliente_id for row in rows if row.cliente_id}
    rodada_ids = {row.rodada_id for row in rows if row.rodada_id}
    setor_ids = {row.setor_id for row in rows if row.setor_id}

    clientes_map: dict[str, str] = {}
    rodadas_map: dict[str, str] = {}
    setores_map: dict[str, str] = {}

    if cliente_ids:
        result = await session.execute(
            select(Cliente).where(Cliente.id.in_(cliente_ids))
        )
        for item in result.scalars().all():
            clientes_map[str(item.id)] = _safe_str(getattr(item, "nome", None)) or str(item.id)

    if rodada_ids:
        result = await session.execute(
            select(RodadaAplicacao).where(RodadaAplicacao.id.in_(rodada_ids))
        )
        for item in result.scalars().all():
            rodadas_map[str(item.id)] = _safe_str(getattr(item, "nome", None)) or str(item.id)

    if setor_ids:
        result = await session.execute(
            select(SetorEmpresa).where(SetorEmpresa.id.in_(setor_ids))
        )
        for item in result.scalars().all():
            setores_map[str(item.id)] = _safe_str(getattr(item, "nome", None)) or str(item.id)

    enriched: list[BIAttemptRow] = []
    for row in rows:
        enriched.append(
            BIAttemptRow(
                attempt_id=row.attempt_id,
                cliente_id=row.cliente_id,
                cliente_nome=row.cliente_nome or clientes_map.get(row.cliente_id or "", None),
                rodada_id=row.rodada_id,
                rodada_nome=row.rodada_nome or rodadas_map.get(row.rodada_id or "", None),
                setor_id=row.setor_id,
                setor_nome=row.setor_nome or setores_map.get(row.setor_id or "", None),
                participant_nome=row.participant_nome,
                participant_email=row.participant_email,
                empresa_nome=row.empresa_nome,
                tipo_aplicacao=row.tipo_aplicacao,
                cargo=row.cargo,
                status=row.status,
                progress=row.progress,
                data_inicio=row.data_inicio,
                data_conclusao=row.data_conclusao,
                computed_result=row.computed_result,
            )
        )

    return enriched


def _apply_python_level_filters(
    rows: list[BIAttemptRow],
    *,
    cargo: str | None,
    tipo_aplicacao: str | None,
) -> list[BIAttemptRow]:
    cargo_filter = _normalize_text_filter(cargo)
    tipo_filter = _normalize_text_filter(tipo_aplicacao)

    filtered = rows

    if cargo_filter:
        needle = cargo_filter.lower()
        filtered = [
            row
            for row in filtered
            if (row.cargo or "").strip().lower() == needle
        ]

    if tipo_filter:
        needle = tipo_filter.lower()
        filtered = [
            row
            for row in filtered
            if (row.tipo_aplicacao or "").strip().lower() == needle
        ]

    return filtered


# ============================================================
# SELECTORS BASE
# ============================================================


async def list_bi_attempt_rows(
    session: AsyncSession,
    *,
    filters: BISelectorFilters | None = None,
) -> list[BIAttemptRow]:
    filters = filters or BISelectorFilters()

    query = (
        select(Attempt)
        .options(selectinload(Attempt.participant))
        .order_by(Attempt.data_inicio.desc())
        .limit(filters.limit)
    )

    if filters.cliente_id:
        query = query.where(Attempt.cliente_id == filters.cliente_id)
    if filters.rodada_id:
        query = query.where(Attempt.rodada_id == filters.rodada_id)
    if filters.setor_id:
        query = query.where(Attempt.setor_id == filters.setor_id)
    if filters.attempt_status:
        query = query.where(Attempt.status == filters.attempt_status)
    if filters.only_completed:
        query = query.where(Attempt.data_conclusao.is_not(None))

    result = await session.execute(query)
    attempts = list(result.scalars().all())
    if not attempts:
        return []

    attempt_ids = [attempt.id for attempt in attempts]

    computed_result_query = select(ComputedResult).where(
        ComputedResult.attempt_id.in_(attempt_ids)
    )
    computed_result_result = await session.execute(computed_result_query)
    computed_results = list(computed_result_result.scalars().all())
    computed_result_map = {
        str(item.attempt_id): item
        for item in computed_results
    }

    rows: list[BIAttemptRow] = []
    for attempt in attempts:
        participant = _extract_participant(attempt)

        rows.append(
            BIAttemptRow(
                attempt_id=str(attempt.id),
                cliente_id=_safe_str(getattr(attempt, "cliente_id", None)),
                cliente_nome=None,
                rodada_id=_safe_str(getattr(attempt, "rodada_id", None)),
                rodada_nome=None,
                setor_id=_safe_str(getattr(attempt, "setor_id", None)),
                setor_nome=None,
                participant_nome=_safe_str(getattr(participant, "nome", None)),
                participant_email=_safe_str(getattr(participant, "email", None)),
                empresa_nome=_safe_str(getattr(participant, "empresa_nome", None)),
                tipo_aplicacao=_safe_str(getattr(participant, "tipo_aplicacao", None)),
                cargo=_safe_str(getattr(attempt, "cargo", None)),
                status=_safe_str(getattr(attempt, "status", None)),
                progress=getattr(attempt, "progress", None),
                data_inicio=_safe_str(getattr(attempt, "data_inicio", None)),
                data_conclusao=_safe_str(getattr(attempt, "data_conclusao", None)),
                computed_result=computed_result_map.get(str(attempt.id)),
            )
        )

    rows = await _load_context_labels(session, rows)
    rows = _apply_python_level_filters(
        rows,
        cargo=filters.cargo,
        tipo_aplicacao=filters.tipo_aplicacao,
    )
    return rows


async def count_bi_attempt_rows(
    session: AsyncSession,
    *,
    filters: BISelectorFilters | None = None,
) -> int:
    rows = await list_bi_attempt_rows(session, filters=filters)
    return len(rows)


# ============================================================
# SELECTORS DE DISTRIBUICAO
# ============================================================


async def get_bi_status_distribution(
    session: AsyncSession,
    *,
    filters: BISelectorFilters | None = None,
) -> list[dict[str, Any]]:
    rows = await list_bi_attempt_rows(session, filters=filters)

    counter: dict[str, int] = {}
    for row in rows:
        key = row.status or "SEM_STATUS"
        counter[key] = counter.get(key, 0) + 1

    return [
        {"status": status, "count": count}
        for status, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


async def get_bi_tipo_aplicacao_distribution(
    session: AsyncSession,
    *,
    filters: BISelectorFilters | None = None,
) -> list[dict[str, Any]]:
    rows = await list_bi_attempt_rows(session, filters=filters)

    counter: dict[str, int] = {}
    for row in rows:
        key = row.tipo_aplicacao or "NAO_INFORMADO"
        counter[key] = counter.get(key, 0) + 1

    return [
        {"tipo_aplicacao": item_type, "count": count}
        for item_type, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


async def get_bi_setor_distribution(
    session: AsyncSession,
    *,
    filters: BISelectorFilters | None = None,
) -> list[dict[str, Any]]:
    rows = await list_bi_attempt_rows(session, filters=filters)

    counter: dict[str, int] = {}
    for row in rows:
        key = row.setor_nome or "SEM_SETOR"
        counter[key] = counter.get(key, 0) + 1

    return [
        {"setor": setor, "count": count}
        for setor, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


async def get_bi_cargo_distribution(
    session: AsyncSession,
    *,
    filters: BISelectorFilters | None = None,
) -> list[dict[str, Any]]:
    rows = await list_bi_attempt_rows(session, filters=filters)

    counter: dict[str, int] = {}
    for row in rows:
        key = row.cargo or "NAO_INFORMADO"
        counter[key] = counter.get(key, 0) + 1

    return [
        {"cargo": cargo, "count": count}
        for cargo, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


# ============================================================
# SELECTORS DE RANKING
# ============================================================


async def get_bi_top5_frequency(
    session: AsyncSession,
    *,
    filters: BISelectorFilters | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    rows = await list_bi_attempt_rows(session, filters=filters)

    counter: dict[str, int] = {}
    for row in rows:
        ranking = _extract_ranking_list(
            row.computed_result,
            attr_name="top5",
            nested_key="top5",
        )
        for item in ranking:
            counter[item] = counter.get(item, 0) + 1

    ranked = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    return [
        {"dimension": dimension, "count": count}
        for dimension, count in ranked[:limit]
    ]


async def get_bi_bottom3_frequency(
    session: AsyncSession,
    *,
    filters: BISelectorFilters | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    rows = await list_bi_attempt_rows(session, filters=filters)

    counter: dict[str, int] = {}
    for row in rows:
        ranking = _extract_ranking_list(
            row.computed_result,
            attr_name="bottom3",
            nested_key="bottom3",
        )
        for item in ranking:
            counter[item] = counter.get(item, 0) + 1

    ranked = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    return [
        {"dimension": dimension, "count": count}
        for dimension, count in ranked[:limit]
    ]


# ============================================================
# SELECTORS DE DIMENSAO / AREA
# ============================================================



async def get_bi_dimension_aggregates(
    session: AsyncSession,
    *,
    filters: BISelectorFilters | None = None,
) -> list[BIDimensionAggregate]:
    rows = await list_bi_attempt_rows(session, filters=filters)

    buckets: dict[str, dict[str, Any]] = {}

    for row in rows:
        items = _extract_dimension_items(row.computed_result)
        for item in items:
            key = item["dimension_key"]
            bucket = buckets.setdefault(
                key,
                {
                    "dimension_key": key,
                    "dimension_label": item["dimension_label"],
                    "area": item["area"],
                    "scores": [],
                    "low_count": 0,
                    "mid_count": 0,
                    "high_count": 0,
                    "count": 0,
                },
            )

            bucket["count"] += 1

            if not bucket["area"] and item["area"]:
                bucket["area"] = item["area"]
            if bucket["dimension_label"] == bucket["dimension_key"] and item["dimension_label"]:
                bucket["dimension_label"] = item["dimension_label"]

            score = item["score"]
            if score is not None:
                bucket["scores"].append(float(score))

            band = _safe_str(item["band"]).lower()
            if band == "low":
                bucket["low_count"] += 1
            elif band == "mid":
                bucket["mid_count"] += 1
            elif band == "high":
                bucket["high_count"] += 1

    aggregates: list[BIDimensionAggregate] = []
    for _, bucket in sorted(buckets.items(), key=lambda item: item[0]):
        scores: list[float] = bucket["scores"]
        aggregates.append(
            BIDimensionAggregate(
                dimension_key=bucket["dimension_key"],
                dimension_label=bucket["dimension_label"],
                area=bucket["area"],
                count=bucket["count"],
                average_score=round(mean(scores), 2) if scores else None,
                median_score=round(median(scores), 2) if scores else None,
                low_count=bucket["low_count"],
                mid_count=bucket["mid_count"],
                high_count=bucket["high_count"],
            )
        )

    return aggregates


async def get_bi_area_aggregates(
    session: AsyncSession,
    *,
    filters: BISelectorFilters | None = None,
) -> list[BIAreaAggregate]:
    dimensions = await get_bi_dimension_aggregates(session, filters=filters)

    buckets: dict[str, list[float]] = {}
    counts: dict[str, int] = {}

    for item in dimensions:
        if not item.area:
            continue
        buckets.setdefault(item.area, [])
        counts[item.area] = counts.get(item.area, 0) + 1
        if item.average_score is not None:
            buckets[item.area].append(item.average_score)

    result: list[BIAreaAggregate] = []
    for area in sorted(counts.keys()):
        scores = buckets.get(area, [])
        result.append(
            BIAreaAggregate(
                area=area,
                count_dimensions=counts[area],
                average_score=round(mean(scores), 2) if scores else None,
            )
        )

    return result


# ============================================================
# SELECTORS DE FILTROS
# ============================================================


async def get_bi_filter_options(
    session: AsyncSession,
    *,
    cliente_id: UUID | str | None = None,
    rodada_id: UUID | str | None = None,
) -> dict[str, list[dict[str, str]]]:
    clientes_result = await session.execute(
        select(Cliente).order_by(Cliente.nome.asc())
    )
    clientes = [
        {"id": str(item.id), "label": _safe_str(item.nome) or str(item.id)}
        for item in clientes_result.scalars().all()
    ]

    rodadas_query = select(RodadaAplicacao)
    if cliente_id:
        rodadas_query = rodadas_query.where(RodadaAplicacao.cliente_id == cliente_id)
    rodadas_query = rodadas_query.order_by(RodadaAplicacao.data_inicio.desc(), RodadaAplicacao.nome.asc())
    rodadas_result = await session.execute(rodadas_query)
    rodadas = [
        {"id": str(item.id), "label": _safe_str(item.nome) or str(item.id)}
        for item in rodadas_result.scalars().all()
    ]

    setores_query = select(SetorEmpresa)
    if cliente_id:
        setores_query = setores_query.where(SetorEmpresa.cliente_id == cliente_id)
    setores_query = setores_query.order_by(SetorEmpresa.nome.asc())
    setores_result = await session.execute(setores_query)
    setores = [
        {"id": str(item.id), "label": _safe_str(item.nome) or str(item.id)}
        for item in setores_result.scalars().all()
    ]

    base_filters = BISelectorFilters(
        cliente_id=cliente_id,
        rodada_id=rodada_id,
        limit=5000,
    )
    rows = await list_bi_attempt_rows(session, filters=base_filters)

    tipos = sorted(
        {row.tipo_aplicacao for row in rows if row.tipo_aplicacao}
    )
    cargos = sorted(
        {row.cargo for row in rows if row.cargo}
    )
    statuses = sorted(
        {row.status for row in rows if row.status}
    )

    return {
        "clientes": clientes,
        "rodadas": rodadas,
        "setores": setores,
        "tipos_aplicacao": [{"id": item, "label": item} for item in tipos],
        "cargos": [{"id": item, "label": item} for item in cargos],
        "statuses": [{"id": item, "label": item} for item in statuses],
    }


# ============================================================
# SELECTOR EXECUTIVO INICIAL
# ============================================================


async def get_bi_overview_payload(
    session: AsyncSession,
    *,
    filters: BISelectorFilters | None = None,
) -> dict[str, Any]:
    rows = await list_bi_attempt_rows(session, filters=filters)

    completed_count = sum(1 for row in rows if row.data_conclusao)
    with_computed_result = sum(1 for row in rows if row.computed_result is not None)

    return {
        "total_attempts": len(rows),
        "completed_attempts": completed_count,
        "attempts_with_computed_result": with_computed_result,
        "status_distribution": await get_bi_status_distribution(session, filters=filters),
        "tipo_aplicacao_distribution": await get_bi_tipo_aplicacao_distribution(session, filters=filters),
        "setor_distribution": await get_bi_setor_distribution(session, filters=filters),
        "cargo_distribution": await get_bi_cargo_distribution(session, filters=filters),
        "top5_frequency": await get_bi_top5_frequency(session, filters=filters),
        "bottom3_frequency": await get_bi_bottom3_frequency(session, filters=filters),
        "dimension_aggregates": await get_bi_dimension_aggregates(session, filters=filters),
        "area_aggregates": await get_bi_area_aggregates(session, filters=filters),
    }
