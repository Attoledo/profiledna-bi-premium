from __future__ import annotations

import re
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader, select_autoescape

# Detecta QUALQUER letra única de dimensão (A..T) seguida de "(" ou "—"/"-" residual,
# em vez de uma lista fixa de letras (ex.: apenas D/F/K/N). Isso garante que o contrato
# do renderer rejeite vazamentos para as 20 dimensões, não só para um subconjunto.
_DIMENSION_LEAK_PATTERNS = (
    re.compile(r"\b[A-Z]\s*\([^)]+\)"),
    re.compile(r"\b[A-Z]\s*[—-]\s*"),
)


def _validate_premium_context(context: Dict[str, Any]) -> None:
    executive_summary_text = context.get("executive_summary_text")

    if not isinstance(executive_summary_text, str):
        raise ValueError(
            "Premium renderer contract error: executive_summary_text must be a string."
        )

    forbidden_raw = context.get("sintese_executiva")
    if isinstance(forbidden_raw, dict):
        if any(
            key in forbidden_raw
            for key in (
                "texto",
                "destaques_principais",
                "ampliacao_potencial",
                "pontos_atencao",
                "strengths",
                "growth",
                "attention",
                "dimensao_alta_principal",
                "dimensao_baixa_prioritaria",
                "risco_tipico",
                "recomendacao_objetiva",
            )
        ):
            raise ValueError(
                "Premium renderer contract error: raw sintese_executiva dict cannot be rendered by the premium template."
            )

    if any(pattern.search(executive_summary_text) for pattern in _DIMENSION_LEAK_PATTERNS):
        raise ValueError(
            "Premium renderer contract error: executive_summary_text contains a residual technical dimension code."
        )


def render_report_premium_html(context: Dict[str, Any]) -> str:
    """
    Renderer dedicado do relatório premium.

    Regras:
      - usa template premium próprio
      - não altera o renderer técnico existente
      - não recalcula scoring
      - apenas renderiza a camada de apresentação premium
      - falha explicitamente se houver risco de vazamento estrutural
    """
    safe_context = dict(context or {})
    _validate_premium_context(safe_context)

    env = Environment(
        loader=FileSystemLoader("backend/templates"),
        autoescape=select_autoescape(["html", "xml"]),
    )

    tpl = env.get_template("reports/report_premium.html")
    return tpl.render(**safe_context)
