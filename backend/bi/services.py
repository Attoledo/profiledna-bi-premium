# /srv/profiledna/backend/bi/services.py
from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
import json

from backend.bi.selectors import (
    BIAreaAggregate,
    BIDimensionAggregate,
    BISelectorFilters,
    count_bi_attempt_rows,
    get_bi_area_aggregates,
    get_bi_bottom3_frequency,
    get_bi_cargo_distribution,
    get_bi_dimension_aggregates,
    get_bi_filter_options,
    get_bi_overview_payload,
    get_bi_setor_distribution,
    get_bi_status_distribution,
    get_bi_tipo_aplicacao_distribution,
    get_bi_top5_frequency,
)


@dataclass(slots=True)
class BIServiceFilters:
    cliente_id: str | None = None
    rodada_id: str | None = None
    setor_id: str | None = None
    cargo: str | None = None
    tipo_aplicacao: str | None = None
    attempt_status: str | None = None
    only_completed: bool = False


@dataclass(slots=True)
class BIOverviewCard:
    key: str
    title: str
    value: str
    subtitle: str | None = None


@dataclass(slots=True)
class BIServicePayload:
    filters_applied: dict[str, Any]
    overview_cards: list[dict[str, Any]]
    status_distribution: list[dict[str, Any]]
    tipo_aplicacao_distribution: list[dict[str, Any]]
    setor_distribution: list[dict[str, Any]]
    cargo_distribution: list[dict[str, Any]]
    radar_area: dict[str, Any]
    dimension_table: list[dict[str, Any]]
    top5_frequency: list[dict[str, Any]]
    bottom3_frequency: list[dict[str, Any]]
    filter_options: dict[str, list[dict[str, str]]]
    meta: dict[str, Any]


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _format_number(value: int | float | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, int):
        return str(value)
    return f"{value:.2f}"


def _percent(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((part / total) * 100.0, 2)


def _normalize_filter_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _build_selector_filters(filters: BIServiceFilters | None) -> BISelectorFilters:
    filters = filters or BIServiceFilters()
    return BISelectorFilters(
        cliente_id=filters.cliente_id,
        rodada_id=filters.rodada_id,
        setor_id=filters.setor_id,
        cargo=_normalize_filter_text(filters.cargo),
        tipo_aplicacao=_normalize_filter_text(filters.tipo_aplicacao),
        attempt_status=_normalize_filter_text(filters.attempt_status),
        only_completed=bool(filters.only_completed),
        limit=5000,
    )


def _build_overview_cards_from_payload(overview: dict[str, Any]) -> list[dict[str, Any]]:
    total_attempts = int(overview.get("total_attempts", 0) or 0)
    completed_attempts = int(overview.get("completed_attempts", 0) or 0)
    attempts_with_computed_result = int(overview.get("attempts_with_computed_result", 0) or 0)

    completion_rate = _percent(completed_attempts, total_attempts)
    computed_rate = _percent(attempts_with_computed_result, total_attempts)

    cards = [
        BIOverviewCard(
            key="total_attempts",
            title="Total de participantes",
            value=_format_number(total_attempts),
            subtitle="Participações encontradas no recorte atual.",
        ),
        BIOverviewCard(
            key="completed_attempts",
            title="Concluídos",
            value=_format_number(completed_attempts),
            subtitle=f"{completion_rate:.2f}% de conclusão.",
        ),
        BIOverviewCard(
            key="attempts_with_computed_result",
            title="Resultados consolidados",
            value=_format_number(attempts_with_computed_result),
            subtitle=f"{computed_rate:.2f}% com payload analítico disponível.",
        ),
    ]
    return [asdict(card) for card in cards]



@lru_cache(maxsize=1)
def _load_dimension_catalog() -> dict[str, dict[str, str]]:
    catalog_path = Path("data/ssot/profiledna/v1/dimensions_20.json")
    if not catalog_path.exists():
        return {}

    try:
        raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    items = raw if isinstance(raw, list) else []
    catalog: dict[str, dict[str, str]] = {}

    for item in items:
        if not isinstance(item, dict):
            continue

        letter = str(item.get("letter") or "").strip().upper()
        if not letter:
            continue

        catalog[letter] = {
            "letter": letter,
            "name": str(item.get("name") or "").strip(),
            "area": str(item.get("area") or "").strip().upper(),
            "competency_rh": str(item.get("competency_rh") or "").strip(),
        }

    return catalog


def _get_dimension_catalog_entry(dimension_key: str) -> dict[str, str]:
    key = str(dimension_key or "").strip().upper()
    return dict(_load_dimension_catalog().get(key, {}))


def _resolve_dimension_display_name(dimension_key: str) -> str:
    entry = _get_dimension_catalog_entry(dimension_key)
    name = str(entry.get("name") or "").strip()
    return name or str(dimension_key or "").strip() or "-"


def _resolve_dimension_competency_label(dimension_key: str) -> str:
    entry = _get_dimension_catalog_entry(dimension_key)
    competency = str(entry.get("competency_rh") or "").strip()
    return competency or _resolve_dimension_display_name(dimension_key)


def _resolve_dimension_area_from_catalog(dimension_key: str) -> str | None:
    entry = _get_dimension_catalog_entry(dimension_key)
    area = str(entry.get("area") or "").strip().upper()
    return area or None


CANONICAL_DIMENSION_AREA: dict[str, str] = {
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

CANONICAL_AREA_ORDER: list[str] = [
    "GERENCIAL",
    "INTER PESSOAL",
    "PESSOAL",
]

AREA_ALIASES: dict[str, str] = {
    "GERENCIAL": "GERENCIAL",
    "GERENCIAL ": "GERENCIAL",
    "INTERPESSOAL": "INTER PESSOAL",
    "INTER PESSOAL": "INTER PESSOAL",
    "INTER_PESSOAL": "INTER PESSOAL",
    "INTER-PESSOAL": "INTER PESSOAL",
    "PESSOAL": "PESSOAL",
}


def _source_get(source: Any, key: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _pick_first(source: Any, *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = _source_get(source, key, None)
        if value is not None:
            return value
    return default


def _normalize_dimension_key(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text[:1] if text else "-"


def _normalize_area_label(raw_area: Any) -> str:
    text = str(raw_area or "").strip().upper()
    if not text:
        return ""
    return AREA_ALIASES.get(text, text)


def _canonical_area_from_dimension(dimension_key: str, raw_area: Any = None) -> str:
    normalized_area = _normalize_area_label(raw_area)
    if normalized_area:
        return normalized_area

    catalog_area = _resolve_dimension_area_from_catalog(dimension_key)
    if catalog_area:
        return catalog_area

    return CANONICAL_DIMENSION_AREA.get(dimension_key, "SEM_AREA")



def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _safe_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return float(value)
    except Exception:
        return None


def _format_score_label(value: Any) -> str:
    parsed = _safe_optional_float(value)
    if parsed is None:
        return "—"
    return f"{parsed:.2f}"


def _score_band_from_value(value: Any) -> str:
    parsed = _safe_optional_float(value)
    if parsed is None:
        return "-"
    if parsed <= 3:
        return "Baixa"
    if parsed <= 6:
        return "Média"
    return "Alta"


def _percent(numerator: Any, denominator: Any) -> float:
    n = _safe_int(numerator)
    d = _safe_int(denominator)
    if d <= 0:
        return 0.0
    return round((n / d) * 100.0, 2)


def _build_dimension_stats_description(
    *,
    area: str,
    count: int,
    low_count: int,
    mid_count: int,
    high_count: int,
    low_pct: float,
    mid_pct: float,
    high_pct: float,
) -> str:
    return (
        f"Área: {area} · N={count} · "
        f"Baixa {low_count} ({low_pct:.2f}%) · "
        f"Média {mid_count} ({mid_pct:.2f}%) · "
        f"Alta {high_count} ({high_pct:.2f}%)"
    )


def _build_dimension_managerial_description(
    *,
    dimension_key: str,
    area: str,
) -> str:
    display_name = _resolve_dimension_display_name(dimension_key)
    competency_label = _resolve_dimension_competency_label(dimension_key)

    if competency_label and competency_label != display_name:
        return f"{display_name}: competência relacionada a {competency_label.lower()} na área {area.title()}."
    return f"{display_name}: dimensão da área {area.title()} com leitura gerencial consolidada no recorte atual."



def _resolve_average_score(source: Any) -> float | None:
    return _safe_optional_float(
        _pick_first(
            source,
            "average_score",
            "average",
            "avg_score",
            "media",
            "mean",
            "mean_score",
            "score_avg",
            "score_mean",
            "media_score",
            default=None,
        )
    )

def _resolve_median_score(source: Any) -> float | None:
    return _safe_optional_float(
        _pick_first(
            source,
            "median_score",
            "median",
            "mediana",
            "median_value",
            "score_median",
            "median_avg",
            default=None,
        )
    )



def _resolve_area_label(source: Any, dimension_key: str) -> str:
    raw_area = _pick_first(
        source,
        "area",
        "area_name",
        "nome_area",
        "macro_area",
        "group_area",
        "label",
        default=None,
    )
    return _canonical_area_from_dimension(dimension_key, raw_area)


def _resolve_dimension_key(source: Any) -> str:
    return _normalize_dimension_key(
        _pick_first(
            source,
            "dimension_key",
            "dimension",
            "key",
            "letra",
            "label",
            "name",
            default="-",
        )
    )


def _decorate_ranking_rows(
    rows: list[dict[str, Any]],
    *,
    denominator: int,
) -> list[dict[str, Any]]:
    decorated: list[dict[str, Any]] = []

    for row in rows:
        dimension_key = _resolve_dimension_key(row)
        count = _safe_int(_pick_first(row, "count", "total", "n", default=0))
        pct = _percent(count, denominator)
        area = _canonical_area_from_dimension(dimension_key)
        dimension_label = _resolve_dimension_display_name(dimension_key)
        competency_label = _resolve_dimension_competency_label(dimension_key)
        description = _build_dimension_managerial_description(
            dimension_key=dimension_key,
            area=area,
        )
        stats_description = f"Área: {area} · {count} ocorrência(s) · {pct:.2f}%"

        decorated.append(
            {
                **row,
                "dimension": dimension_key,
                "dimension_key": dimension_key,
                "dimension_label": dimension_label,
                "label": dimension_label,
                "competency_label": competency_label,
                "count": count,
                "value": count,
                "pct": pct,
                "pct_label": f"{pct:.2f}%",
                "area": area,
                "description": description,
                "leitura": description,
                "stats_description": stats_description,
            }
        )

    return decorated



def _build_radar_area_payload(
    area_aggregates: list[Any],
    *,
    dimension_table: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    dimension_table = dimension_table or []

    area_map: dict[str, dict[str, Any]] = {
        area: {
            "area": area,
            "average_score": None,
            "count_dimensions": 0,
        }
        for area in CANONICAL_AREA_ORDER
    }

    for item in area_aggregates:
        raw_area = _pick_first(
            item,
            "area",
            "area_name",
            "nome_area",
            "macro_area",
            "label",
            default=None,
        )
        area = _normalize_area_label(raw_area)
        if area not in area_map:
            continue

        average_score = _resolve_average_score(item)
        count_dimensions = _safe_int(
            _pick_first(
                item,
                "count_dimensions",
                "dimensions_count",
                "dimension_count",
                "qtd_dimensoes",
                "count",
                default=0,
            )
        )

        if average_score is not None:
            area_map[area]["average_score"] = round(average_score, 2)
        if count_dimensions > 0:
            area_map[area]["count_dimensions"] = count_dimensions

    if dimension_table:
        grouped_scores: dict[str, list[float]] = {area: [] for area in CANONICAL_AREA_ORDER}
        grouped_dimensions: dict[str, set[str]] = {area: set() for area in CANONICAL_AREA_ORDER}

        for row in dimension_table:
            dimension_key = _resolve_dimension_key(row)
            area = _resolve_area_label(row, dimension_key)
            average_score = _resolve_average_score(row)

            if area in grouped_dimensions:
                grouped_dimensions[area].add(dimension_key)

            if area in grouped_scores and average_score is not None:
                grouped_scores[area].append(average_score)

        for area in CANONICAL_AREA_ORDER:
            if grouped_scores[area]:
                area_map[area]["average_score"] = round(
                    sum(grouped_scores[area]) / len(grouped_scores[area]),
                    2,
                )
            if grouped_dimensions[area]:
                area_map[area]["count_dimensions"] = len(grouped_dimensions[area])

    details = [area_map[area] for area in CANONICAL_AREA_ORDER]
    dataset_values = [
        round(item["average_score"], 2) if item["average_score"] is not None else 0.0
        for item in details
    ]
    has_data = any(item["average_score"] is not None for item in details)

    return {
        "labels": [item["area"] for item in details],
        "datasets": [
            {
                "label": "Média por área",
                "data": dataset_values,
            }
        ],
        "details": details,
        "scale_min": 0,
        "scale_max": 10,
        "has_data": has_data,
    }




def _build_dimension_table(
    dimension_aggregates: list[Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for item in dimension_aggregates:
        dimension_key = _resolve_dimension_key(item)
        area = _resolve_area_label(item, dimension_key)

        average_score = _resolve_average_score(item)
        average_score_label = _format_score_label(average_score)

        median_score = _resolve_median_score(item)
        median_score_label = _format_score_label(median_score)

        count = _safe_int(_pick_first(item, "count", "total", "n", default=0))
        low_count = _safe_int(_pick_first(item, "low_count", "count_low", "baixo_count", default=0))
        mid_count = _safe_int(_pick_first(item, "mid_count", "count_mid", "medio_count", default=0))
        high_count = _safe_int(_pick_first(item, "high_count", "count_high", "alto_count", default=0))

        low_pct = _percent(low_count, count)
        mid_pct = _percent(mid_count, count)
        high_pct = _percent(high_count, count)

        band = _score_band_from_value(average_score)
        dimension_label = _resolve_dimension_display_name(dimension_key)
        competency_label = _resolve_dimension_competency_label(dimension_key)
        stats_description = _build_dimension_stats_description(
            area=area,
            count=count,
            low_count=low_count,
            mid_count=mid_count,
            high_count=high_count,
            low_pct=low_pct,
            mid_pct=mid_pct,
            high_pct=high_pct,
        )
        description = _build_dimension_managerial_description(
            dimension_key=dimension_key,
            area=area,
        )

        rows.append(
            {
                "dimension_key": dimension_key,
                "dimension_label": dimension_label,
                "dimension": dimension_key,
                "label": dimension_label,
                "competency_label": competency_label,
                "area": area,
                "average_score": average_score,
                "average_score_label": average_score_label,
                "average": average_score,
                "average_label": average_score_label,
                "median_score": median_score,
                "median_score_label": median_score_label,
                "median": median_score,
                "median_label": median_score_label,
                "value": average_score_label,
                "media": average_score_label,
                "band": band,
                "faixa": band,
                "description": description,
                "leitura": description,
                "stats_description": stats_description,
                "count": count,
                "low_count": low_count,
                "mid_count": mid_count,
                "high_count": high_count,
                "low_pct": low_pct,
                "mid_pct": mid_pct,
                "high_pct": high_pct,
            }
        )

    rows.sort(key=lambda row: row.get("dimension_key", "Z"))
    return rows


def _build_meta_payload(
    *,
    filters: BIServiceFilters,
    dimension_table: list[dict[str, Any]],
    radar_area: dict[str, Any],
) -> dict[str, Any]:
    dimensions_with_score = sum(
        1 for row in dimension_table if row.get("average_score") is not None
    )
    areas_with_score = sum(
        1 for item in radar_area.get("details", []) if item.get("average_score") is not None
    )

    return {
        "filters_active": any(
            [
                filters.cliente_id,
                filters.rodada_id,
                filters.setor_id,
                _normalize_filter_text(filters.cargo),
                _normalize_filter_text(filters.tipo_aplicacao),
                _normalize_filter_text(filters.attempt_status),
                bool(filters.only_completed),
            ]
        ),
        "dimensions_available": len(dimension_table),
        "dimensions_with_score": dimensions_with_score,
        "areas_with_score": areas_with_score,
        "only_completed": bool(filters.only_completed),
    }


async def build_bi_overview_cards(
    session,
    *,
    filters: BIServiceFilters | None = None,
) -> list[dict[str, Any]]:
    selector_filters = _build_selector_filters(filters)
    overview = await get_bi_overview_payload(session, filters=selector_filters)
    return _build_overview_cards_from_payload(overview)


async def build_bi_dimension_table(
    session,
    *,
    filters: BIServiceFilters | None = None,
) -> list[dict[str, Any]]:
    selector_filters = _build_selector_filters(filters)
    aggregates = await get_bi_dimension_aggregates(session, filters=selector_filters)
    return _build_dimension_table(aggregates)


async def build_bi_radar_area(
    session,
    *,
    filters: BIServiceFilters | None = None,
) -> dict[str, Any]:
    selector_filters = _build_selector_filters(filters)
    area_aggregates = await get_bi_area_aggregates(session, filters=selector_filters)
    return _build_radar_area_payload(area_aggregates)



async def build_bi_service_payload(
    session,
    *,
    filters: BIServiceFilters | None = None,
) -> BIServicePayload:
    filters = filters or BIServiceFilters()
    selector_filters = _build_selector_filters(filters)

    overview_raw = await get_bi_overview_payload(session, filters=selector_filters)
    status_distribution = await get_bi_status_distribution(session, filters=selector_filters)
    tipo_aplicacao_distribution = await get_bi_tipo_aplicacao_distribution(
        session,
        filters=selector_filters,
    )
    setor_distribution = await get_bi_setor_distribution(session, filters=selector_filters)
    cargo_distribution = await get_bi_cargo_distribution(session, filters=selector_filters)

    top5_frequency_raw = await get_bi_top5_frequency(session, filters=selector_filters)
    bottom3_frequency_raw = await get_bi_bottom3_frequency(session, filters=selector_filters)

    dimension_aggregates = await get_bi_dimension_aggregates(session, filters=selector_filters)
    area_aggregates = await get_bi_area_aggregates(session, filters=selector_filters)

    filter_options = await get_bi_filter_options(
        session,
        cliente_id=filters.cliente_id,
        rodada_id=filters.rodada_id,
    )

    overview_cards = _build_overview_cards_from_payload(overview_raw)
    dimension_table = _build_dimension_table(dimension_aggregates)
    radar_area = _build_radar_area_payload(
        area_aggregates,
        dimension_table=dimension_table,
    )

    ranking_denominator = 0
    for card in overview_cards:
        if str(card.get("key")) == "attempts_with_computed_result":
            ranking_denominator = _safe_int(card.get("value"))
            break

    if ranking_denominator <= 0:
        ranking_denominator = max(
            (_safe_int(row.get("count", 0)) for row in dimension_table),
            default=0,
        )

    top5_frequency = _decorate_ranking_rows(
        top5_frequency_raw,
        denominator=ranking_denominator,
    )
    bottom3_frequency = _decorate_ranking_rows(
        bottom3_frequency_raw,
        denominator=ranking_denominator,
    )

    applied_filters = {
        "cliente_id": filters.cliente_id,
        "rodada_id": filters.rodada_id,
        "setor_id": filters.setor_id,
        "cargo": _normalize_filter_text(filters.cargo),
        "tipo_aplicacao": _normalize_filter_text(filters.tipo_aplicacao),
        "attempt_status": _normalize_filter_text(filters.attempt_status),
        "only_completed": bool(filters.only_completed),
    }

    meta = _build_meta_payload(
        filters=filters,
        dimension_table=dimension_table,
        radar_area=radar_area,
    )
    meta["total_attempts"] = await count_bi_attempt_rows(session, filters=selector_filters)
    meta["ranking_denominator"] = ranking_denominator

    return BIServicePayload(
        filters_applied=applied_filters,
        overview_cards=overview_cards,
        status_distribution=status_distribution,
        tipo_aplicacao_distribution=tipo_aplicacao_distribution,
        setor_distribution=setor_distribution,
        cargo_distribution=cargo_distribution,
        radar_area=radar_area,
        dimension_table=dimension_table,
        top5_frequency=top5_frequency,
        bottom3_frequency=bottom3_frequency,
        filter_options=filter_options,
        meta=meta,
    )




def _comparison_signal(delta: float) -> str:
    if delta > 0:
        return "A_MAIOR"
    if delta < 0:
        return "B_MAIOR"
    return "IGUAL"


def build_bi_comparison_dimension_table(
    left_payload: BIServicePayload,
    right_payload: BIServicePayload,
) -> list[dict[str, Any]]:
    left_rows = {
        str(row.get("dimension") or row.get("dimension_key") or row.get("label") or "").strip().upper(): row
        for row in list(left_payload.dimension_table or [])
    }
    right_rows = {
        str(row.get("dimension") or row.get("dimension_key") or row.get("label") or "").strip().upper(): row
        for row in list(right_payload.dimension_table or [])
    }

    comparison_rows: list[dict[str, Any]] = []

    ordered_dimensions = sorted(
        set(left_rows.keys()) | set(right_rows.keys()) | set(CANONICAL_DIMENSION_AREA.keys())
    )

    for dimension_key in ordered_dimensions:
        left_row = left_rows.get(dimension_key, {})
        right_row = right_rows.get(dimension_key, {})

        mean_a_raw = left_row.get("average_score")
        mean_b_raw = right_row.get("average_score")

        mean_a = _safe_optional_float(mean_a_raw)
        mean_b = _safe_optional_float(mean_b_raw)

        safe_a = 0.0 if mean_a is None else mean_a
        safe_b = 0.0 if mean_b is None else mean_b
        delta = round(safe_a - safe_b, 2)

        area = (
            left_row.get("area")
            or right_row.get("area")
            or _canonical_area_from_dimension(dimension_key)
            or CANONICAL_DIMENSION_AREA.get(dimension_key, "SEM_AREA")
        )

        dimension_label = (
            str(left_row.get("dimension_label") or "").strip()
            or str(right_row.get("dimension_label") or "").strip()
            or _resolve_dimension_display_name(dimension_key)
        )

        competency_label = (
            str(left_row.get("competency_label") or "").strip()
            or str(right_row.get("competency_label") or "").strip()
            or _resolve_dimension_competency_label(dimension_key)
        )

        description = (
            str(left_row.get("description") or "").strip()
            or str(right_row.get("description") or "").strip()
            or _build_dimension_managerial_description(
                dimension_key=dimension_key,
                area=str(area),
            )
        )

        comparison_rows.append(
            {
                "dimension": dimension_key,
                "dimension_key": dimension_key,
                "dimension_label": dimension_label,
                "label": dimension_label,
                "competency_label": competency_label,
                "area": area,
                "description": description,
                "mean_a": mean_a,
                "mean_b": mean_b,
                "delta": delta,
                "signal": _comparison_signal(delta),
            }
        )

    return comparison_rows


async def build_bi_template_context(
    session,
    *,
    filters: BIServiceFilters | None = None,
) -> dict[str, Any]:
    payload = await build_bi_service_payload(session, filters=filters)

    return {
        "bi_filters": payload.filters_applied,
        "bi_overview_cards": payload.overview_cards,
        "bi_status_distribution": payload.status_distribution,
        "bi_tipo_aplicacao_distribution": payload.tipo_aplicacao_distribution,
        "bi_setor_distribution": payload.setor_distribution,
        "bi_cargo_distribution": payload.cargo_distribution,
        "bi_radar_area": payload.radar_area,
        "bi_dimension_table": payload.dimension_table,
        "bi_top5_frequency": payload.top5_frequency,
        "bi_bottom3_frequency": payload.bottom3_frequency,
        "bi_filter_options": payload.filter_options,
        "bi_meta": payload.meta,
    }


async def build_bi_cliente_context(
    session,
    *,
    cliente_id: str,
    rodada_id: str | None = None,
    setor_id: str | None = None,
    cargo: str | None = None,
    tipo_aplicacao: str | None = None,
    attempt_status: str | None = None,
    only_completed: bool = False,
) -> dict[str, Any]:
    filters = BIServiceFilters(
        cliente_id=cliente_id,
        rodada_id=rodada_id,
        setor_id=setor_id,
        cargo=cargo,
        tipo_aplicacao=tipo_aplicacao,
        attempt_status=attempt_status,
        only_completed=only_completed,
    )
    return await build_bi_template_context(session, filters=filters)
