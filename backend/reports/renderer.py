from __future__ import annotations

from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader, select_autoescape


def render_report_html(context: Dict[str, Any]) -> str:
    """
    Renderiza HTML do relatório para snapshot em DB.

    FASE 2B:
    - migra do template simplificado public/report.html
      para o template canônico reports/report_full.html
    - mantém compatibilidade com o payload atual
    - injeta defaults seguros para as seções do relatório
    """
    env = Environment(
        loader=FileSystemLoader("backend/templates"),
        autoescape=select_autoescape(["html", "xml"]),
    )

    tpl = env.get_template("reports/report_full.html")

    safe_context = dict(context or {})

    if "request" not in safe_context:
        safe_context["request"] = None

    # Defaults seguros para o template canônico.
    # Não inventam dados; apenas evitam quebra de render enquanto
    # o backend canônico ainda não entrega todo o payload final.
    safe_context.setdefault("participant", {})
    safe_context.setdefault("attempt", {})
    safe_context.setdefault("ranking", {})
    safe_context.setdefault("interpretations", {})
    safe_context.setdefault("sintese_executiva", {})
    safe_context.setdefault("paineis_area", [])
    safe_context.setdefault("pdi_competencias", [])
    safe_context.setdefault("gestor_rh", {})
    safe_context.setdefault("nota_tecnica", {})

    return tpl.render(**safe_context)
