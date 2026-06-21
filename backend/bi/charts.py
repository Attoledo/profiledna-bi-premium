from __future__ import annotations

from typing import Any

from backend.bi.services import BIServicePayload


def _safe_get(source: Any, *keys: str, default: Any = None) -> Any:
    if source is None:
        return default

    if isinstance(source, dict):
        for key in keys:
            if key in source and source[key] is not None:
                return source[key]
        return default

    for key in keys:
        if hasattr(source, key):
            value = getattr(source, key)
            if value is not None:
                return value

    return default


def _coerce_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default

    if isinstance(value, bool):
        return float(int(value))

    if isinstance(value, (int, float)):
        return float(value)

    raw = str(value).strip().replace(",", ".")
    if not raw or raw == "—" or raw == "-":
        return default

    try:
        return float(raw)
    except Exception:
        return default


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _coerce_display_number(value: Any) -> float | int | str:
    if value in (None, "", "—", "-"):
        return "—"

    number = _coerce_float(value, default=0.0)
    if float(number).is_integer():
        return int(number)
    return round(number, 2)


def _coerce_label(item: Any, fallback: str) -> str:
    label = _safe_get(
        item,
        "label",
        "dimension_label",
        "dimension",
        "area",
        "status",
        "tipo_aplicacao",
        "setor",
        "cargo",
        "title",
        default=None,
    )
    text = str(label or "").strip()
    return text or fallback


def _coerce_description(item: Any) -> str | None:
    description = _safe_get(
        item,
        "description",
        "leitura",
        "summary",
        "subtitle",
        default=None,
    )
    text = str(description or "").strip()
    return text or None


def _coerce_score_label(item: Any) -> str:
    value = _safe_get(
        item,
        "value",
        "media",
        "average_label",
        "average_score_label",
        "median_label",
        "median_score_label",
        default="—",
    )
    text = str(value or "").strip()
    return text or "—"


def _build_radar_chart_config(payload: BIServicePayload) -> dict[str, Any]:
    radar_source = getattr(payload, "radar_area", None) or {}

    labels = list(_safe_get(radar_source, "labels", default=[]) or [])
    datasets = list(_safe_get(radar_source, "datasets", default=[]) or [])
    details = list(_safe_get(radar_source, "details", default=[]) or [])

    normalized_details: list[dict[str, Any]] = []
    for item in details:
        area = str(_safe_get(item, "area", default="-") or "-")
        average_score = _safe_get(item, "average_score", default=None)
        count_dimensions = _coerce_int(_safe_get(item, "count_dimensions", default=0), default=0)

        normalized_details.append(
            {
                "area": area,
                "average_score": average_score,
                "average_score_label": "—" if average_score is None else f"{_coerce_float(average_score):.2f}",
                "count_dimensions": count_dimensions,
                "description": (
                    f"{count_dimensions} dimensão(ões) na área"
                    + (
                        f" · média {float(_coerce_float(average_score)):.2f}"
                        if average_score is not None
                        else " · sem score consolidado"
                    )
                ),
            }
        )

    if not labels and normalized_details:
        labels = [str(item["area"]) for item in normalized_details]

    if not datasets and normalized_details:
        datasets = [
            {
                "label": "Média por área",
                "data": [
                    0.0 if item["average_score"] is None else round(_coerce_float(item["average_score"]), 2)
                    for item in normalized_details
                ],
            }
        ]

    has_data = bool(_safe_get(radar_source, "has_data", default=False))
    if not has_data:
        has_data = any(item["average_score"] is not None for item in normalized_details)

    return {
        "title": "Radar / Área analítica",
        "labels": labels,
        "datasets": datasets,
        "details": normalized_details,
        "scale_min": _coerce_int(_safe_get(radar_source, "scale_min", default=0), default=0),
        "scale_max": _coerce_int(_safe_get(radar_source, "scale_max", default=10), default=10),
        "has_data": has_data,
    }


def _build_pie_chart_config(
    items: list[Any] | None,
    *,
    title: str,
    fallback_prefix: str,
    label_keys: tuple[str, ...],
    value_keys: tuple[str, ...] = ("count", "value"),
) -> dict[str, Any]:
    normalized_items: list[dict[str, Any]] = []

    for index, item in enumerate(items or [], start=1):
        label = _safe_get(item, *label_keys, default=f"{fallback_prefix} {index}")
        label_text = str(label or "").strip() or f"{fallback_prefix} {index}"

        raw_value = _safe_get(item, *value_keys, default=0)
        value = _coerce_float(raw_value, default=0.0)
        if value < 0:
            value = 0.0

        normalized_items.append(
            {
                "label": label_text,
                "value": value,
                "count": _coerce_int(raw_value, default=0),
                "pct": _coerce_float(_safe_get(item, "pct", default=0.0), default=0.0),
                "pct_label": str(_safe_get(item, "pct_label", default="")).strip() or None,
                "area": _safe_get(item, "area", default=None),
                "description": _coerce_description(item),
            }
        )

    total = round(sum(item["value"] for item in normalized_items), 2)
    labels = [item["label"] for item in normalized_items]
    values = [item["value"] for item in normalized_items]

    return {
        "title": title,
        "labels": labels,
        "values": values,
        "total": total,
        "has_data": bool(normalized_items),
        "items": normalized_items,
    }


def _build_band_label(item: Any) -> str:
    band = _safe_get(item, "band", "faixa", default=None)
    if band is not None and str(band).strip():
        return str(band).strip()

    value = _coerce_float(
        _safe_get(
            item,
            "average_score",
            "average",
            "median_score",
            "median",
            "value",
            default=None,
        ),
        default=0.0,
    )
    if value <= 3:
        return "Baixa"
    if value <= 6:
        return "Média"
    return "Alta"


def build_dimension_table_visual(payload: BIServicePayload) -> list[dict[str, Any]]:
    rows = getattr(payload, "dimension_table", None) or []
    visual_rows: list[dict[str, Any]] = []

    for index, row in enumerate(rows, start=1):
        label = _coerce_label(row, f"Dimensão {index}")
        band = _build_band_label(row)
        description = _coerce_description(row) or "Leitura consolidada da dimensão no recorte selecionado."

        visual_rows.append(
            {
                "label": label,
                "dimension": _safe_get(row, "dimension", "dimension_key", default=label),
                "area": _safe_get(row, "area", default="-"),
                "value": _coerce_score_label(row),
                "average": _safe_get(row, "average", "average_score", default=None),
                "average_label": str(_safe_get(row, "average_label", "average_score_label", default="—") or "—"),
                "median": _safe_get(row, "median", "median_score", default=None),
                "median_label": str(_safe_get(row, "median_label", "median_score_label", default="—") or "—"),
                "band": band,
                "description": description,
                "count": _coerce_int(_safe_get(row, "count", default=0), default=0),
                "low_pct": round(_coerce_float(_safe_get(row, "low_pct", default=0.0), default=0.0), 2),
                "mid_pct": round(_coerce_float(_safe_get(row, "mid_pct", default=0.0), default=0.0), 2),
                "high_pct": round(_coerce_float(_safe_get(row, "high_pct", default=0.0), default=0.0), 2),
            }
        )

    return visual_rows


def build_top_bottom_cards(
    items: list[Any] | None,
    *,
    fallback_prefix: str,
) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []

    for index, item in enumerate(items or [], start=1):
        label = _coerce_label(item, f"{fallback_prefix} {index}")
        value = _coerce_int(_safe_get(item, "count", "value", default=0), default=0)

        cards.append(
            {
                "label": label,
                "value": value,
                "count": value,
                "pct": round(_coerce_float(_safe_get(item, "pct", default=0.0), default=0.0), 2),
                "pct_label": str(_safe_get(item, "pct_label", default="")).strip() or None,
                "area": _safe_get(item, "area", default=None),
                "description": _coerce_description(item),
            }
        )

    cards.sort(key=lambda x: x["value"], reverse=True)
    return cards


def build_bi_chart_bundle(payload: BIServicePayload) -> dict[str, Any]:
    radar_area_chart = _build_radar_chart_config(payload)

    status_pie_chart = _build_pie_chart_config(
        getattr(payload, "status_distribution", None),
        title="Distribuição por status",
        fallback_prefix="Status",
        label_keys=("status", "label"),
        value_keys=("count", "value"),
    )

    top5_chart = _build_pie_chart_config(
        getattr(payload, "top5_frequency", None),
        title="Top 5 mais frequentes",
        fallback_prefix="Top",
        label_keys=("label", "dimension", "dimension_label"),
        value_keys=("count", "value"),
    )

    bottom3_chart = _build_pie_chart_config(
        getattr(payload, "bottom3_frequency", None),
        title="Bottom 3 mais frequentes",
        fallback_prefix="Bottom",
        label_keys=("label", "dimension", "dimension_label"),
        value_keys=("count", "value"),
    )

    dimension_table = build_dimension_table_visual(payload)
    top5_cards = build_top_bottom_cards(
        getattr(payload, "top5_frequency", None),
        fallback_prefix="Top",
    )
    bottom3_cards = build_top_bottom_cards(
        getattr(payload, "bottom3_frequency", None),
        fallback_prefix="Bottom",
    )

    return {
        "overview_cards": getattr(payload, "overview_cards", []) or [],
        "radar_area_chart": radar_area_chart,
        "status_pie_chart": status_pie_chart,
        "top5_chart": top5_chart,
        "bottom3_chart": bottom3_chart,
        "dimension_table": dimension_table,
        "top5_cards": top5_cards,
        "bottom3_cards": bottom3_cards,
        "filter_options": getattr(payload, "filter_options", {}) or {},
        "filters_applied": getattr(payload, "filters_applied", {}) or {},
        "meta": getattr(payload, "meta", {}) or {},
    }
