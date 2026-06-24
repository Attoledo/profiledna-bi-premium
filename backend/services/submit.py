from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.attempt import Attempt, Participant
from backend.reports.renderer import render_report_html
from backend.scoring.engine import compute_scores
from backend.ssot.loader import load_json

from backend.repositories import attempt as repo_attempt
from backend.repositories import invite as repo_invite
from backend.repositories import result as repo_result


class SubmitIncompleteError(Exception):
    """
    Submit inválido porque ainda não existem 100 respostas.
    SSOT: submit só é permitido com 100 respostas.
    """


def _safe_datetime_str(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def _normalize_tipo_aplicacao(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_corporate_tipo(tipo_aplicacao: str) -> bool:
    tipo = _normalize_tipo_aplicacao(tipo_aplicacao)
    return tipo in {"empresa", "profissional", "corporativo", "corporativa"}


def _normalize_area(area: Any) -> str:
    txt = str(area or "").strip().upper()
    if txt in {"GERENCIAL", "INTER PESSOAL", "INTERPESSOAL", "PESSOAL"}:
        if txt == "INTERPESSOAL":
            return "INTER PESSOAL"
        return txt
    return "PESSOAL"


def _display_area_label(area: Any) -> str:
    value = _normalize_area(area)
    mapping = {
        "GERENCIAL": "Gerencial",
        "INTER PESSOAL": "Interpessoal",
        "PESSOAL": "Pessoal",
    }
    return mapping.get(value, "Pessoal")


def _band_label(value: Any) -> str:
    val = str(value or "").strip().lower()
    mapping = {
        "low": "Baixo",
        "mid": "Médio",
        "high": "Alto",
        "baixo": "Baixo",
        "medio": "Médio",
        "médio": "Médio",
        "alto": "Alto",
    }
    return mapping.get(val, str(value or "").strip())


def _first_nonempty_sentence(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    parts = [p.strip() for p in value.replace("\n", " ").split(".") if p.strip()]
    if not parts:
        return value
    return f"{parts[0]}."


def _trim_text(value: Any, max_len: int = 220) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _ordered_unique_letters(values: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in values:
        letter = str(value or "").strip()
        if not letter or letter in seen:
            continue
        seen.add(letter)
        out.append(letter)
    return out


def _ranking_letters(ranking: Dict[str, Any], key: str) -> List[str]:
    raw = ranking.get(key, [])
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item).strip()]


def _load_dimensions_map() -> Dict[str, Dict[str, Any]]:
    """
    dimensions_20.json:
      - pode ser lista de objetos com campo 'letter'
      - ou dict { "A": {...}, ... }
    Retorna map: letter -> meta(dict)
    """
    data = load_json("data/ssot/profiledna/v1/dimensions_20.json")
    out: Dict[str, Dict[str, Any]] = {}

    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict):
                out[str(key)] = dict(value)
            else:
                out[str(key)] = {"raw": value}
        return out

    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            letter = item.get("letter")
            if not letter:
                continue
            out[str(letter)] = dict(item)
        return out

    return out


def _load_dimension_competency_map() -> Dict[str, str]:
    dims = _load_dimensions_map()

    try:
        data = load_json("data/ssot/profiledna/v1/dimension_competency_map.json")
    except Exception:
        data = None

    out: Dict[str, str] = {}

    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, str) and value.strip():
                out[str(key)] = value.strip()
            elif isinstance(value, dict):
                txt = value.get("competency_rh") or value.get("competencia_rh") or value.get("competency")
                if isinstance(txt, str) and txt.strip():
                    out[str(key)] = txt.strip()

    if out:
        return out

    for letter, meta in dims.items():
        competency = meta.get("competency_rh") or meta.get("competencia_rh") or ""
        if isinstance(competency, str) and competency.strip():
            out[str(letter)] = competency.strip()

    return out


def _load_premium_manager_blocks() -> Dict[str, Any]:
    try:
        data = load_json("data/ssot/profiledna/v1/premium_manager_blocks.json")
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _load_library_map(tipo_aplicacao: str) -> Dict[str, Dict[str, Any]]:
    """
    SSOT v2.0 (OBRIGATÓRIO):
      - tipo_aplicacao='pessoal' -> library1_basic.json
      - tipo_aplicacao='empresa' -> library2_premium.json
    """
    tipo = (tipo_aplicacao or "").strip().lower()
    if tipo == "empresa":
        path = "data/ssot/profiledna/v1/library2_premium.json"
    else:
        path = "data/ssot/profiledna/v1/library1_basic.json"

    data = load_json(path)
    if not isinstance(data, dict):
        return {}

    out: Dict[str, Dict[str, Any]] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            out[str(key)] = dict(value)
        else:
            out[str(key)] = {"raw": value}
    return out


def _pick_band_text_from_library(entry: Dict[str, Any], band_key: str) -> str:
    """
    SSOT v2.0:
      - textos por faixa ficam em entry.fields.low/mid/high
    Fallbacks aceitos:
      - entry.low/mid/high
    """
    fields = entry.get("fields")
    if isinstance(fields, dict):
        txt = fields.get(band_key)
        if isinstance(txt, str):
            return txt.strip()

    txt2 = entry.get(band_key)
    if isinstance(txt2, str):
        return txt2.strip()

    return ""


def _build_interpretations_payload(
    scores: Dict[str, int],
    bands: Dict[str, str],
    tipo_aplicacao: str,
) -> Dict[str, Any]:
    """
    interpretations = {
      "A": {"letter":"A","score":3,"band_key":"low","name":"...","text":"..."},
      ...
    }
    Fonte do texto:
      - library1_basic (pessoal)
      - library2_premium (empresa)
    """
    dims = _load_dimensions_map()
    lib = _load_library_map(tipo_aplicacao)

    out: Dict[str, Any] = {}
    for letter, score in sorted(scores.items(), key=lambda kv: kv[0]):
        band_key = str(bands.get(letter, ""))
        meta = dims.get(letter, {})
        lib_entry = lib.get(letter, {})

        out[letter] = {
            "letter": letter,
            "score": int(score),
            "band_key": band_key,
            "name": meta.get("name") or meta.get("nome") or "",
            "area": meta.get("area") or "",
            "competency_rh": meta.get("competency_rh") or meta.get("competencia_rh") or "",
            "text": _pick_band_text_from_library(lib_entry, band_key),
        }
    return out


def _ranking_payload_from_lists(top3: list, top5: list, bottom3: list) -> Dict[str, Any]:
    return {"top3": top3, "top5": top5, "bottom3": bottom3}


def _pick_first_bullets(raw: Any, limit: int = 3) -> List[str]:
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()][:limit]

    if isinstance(raw, dict):
        candidates: List[str] = []
        for key in ("bullets", "items", "linhas", "conteudo", "content"):
            value = raw.get(key)
            if isinstance(value, list):
                candidates.extend([str(item).strip() for item in value if str(item).strip()])
        return candidates[:limit]

    return []


def _get_dim_name(letter: str, interpretations: Dict[str, Any], dims: Dict[str, Dict[str, Any]]) -> str:
    interp = interpretations.get(letter, {})
    if isinstance(interp, dict):
        name = interp.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()

    meta = dims.get(letter, {})
    return str(meta.get("name") or meta.get("nome") or letter).strip()


def _get_dim_area(letter: str, interpretations: Dict[str, Any], dims: Dict[str, Dict[str, Any]]) -> str:
    interp = interpretations.get(letter, {})
    if isinstance(interp, dict):
        area = interp.get("area")
        if isinstance(area, str) and area.strip():
            return _normalize_area(area)

    meta = dims.get(letter, {})
    return _normalize_area(meta.get("area"))


def _get_dim_text(letter: str, interpretations: Dict[str, Any]) -> str:
    interp = interpretations.get(letter, {})
    if not isinstance(interp, dict):
        return ""
    return str(interp.get("text") or "").strip()


def _get_dim_score(letter: str, scores: Dict[str, Any], interpretations: Dict[str, Any]) -> int:
    if letter in scores:
        try:
            return int(scores.get(letter) or 0)
        except Exception:
            return 0

    interp = interpretations.get(letter, {})
    if isinstance(interp, dict):
        try:
            return int(interp.get("score") or 0)
        except Exception:
            return 0

    return 0


def _get_dim_band(letter: str, bands: Dict[str, Any], interpretations: Dict[str, Any]) -> str:
    if letter in bands:
        return str(bands.get(letter, "") or "").strip().lower()

    interp = interpretations.get(letter, {})
    if isinstance(interp, dict):
        return str(interp.get("band_key") or "").strip().lower()

    return ""


def _get_dim_competency(letter: str, interpretations: Dict[str, Any], dims: Dict[str, Dict[str, Any]]) -> str:
    interp = interpretations.get(letter, {})
    if isinstance(interp, dict):
        competency = interp.get("competency_rh")
        if isinstance(competency, str) and competency.strip():
            return competency.strip()

    meta = dims.get(letter, {})
    competency = meta.get("competency_rh") or meta.get("competencia_rh") or ""
    return str(competency).strip()


async def _load_participant_by_attempt(session: AsyncSession, attempt: Attempt) -> Optional[Participant]:
    """
    Importante:
    não acessar attempt.participant aqui, porque isso pode disparar
    lazy-loading ORM em contexto async inadequado e causar MissingGreenlet.
    """
    res = await session.execute(
        select(Participant).where(Participant.id == attempt.participant_id)
    )
    return res.scalar_one_or_none()


async def _build_participant_payload(session: AsyncSession, attempt: Attempt) -> Dict[str, Any]:
    participant = await _load_participant_by_attempt(session, attempt)
    if not participant:
        return {}

    return {
        "id": str(participant.id),
        "nome": participant.nome or "",
        "sobrenome": participant.sobrenome or "",
        "email": participant.email or "",
        "empresa_nome": getattr(participant, "empresa_nome", None) or "",
        "tipo_aplicacao": participant.tipo_aplicacao or "",
    }


def _build_attempt_payload(attempt: Attempt) -> Dict[str, Any]:
    return {
        "id": str(attempt.id),
        "cargo": attempt.cargo or "",
        "status": attempt.status or "",
        "progress": int(attempt.progress or 0),
        "testdef_version": attempt.testdef_version or "",
        "data_inicio": _safe_datetime_str(attempt.data_inicio),
        "data_conclusao": _safe_datetime_str(attempt.data_conclusao),
    }


def _compose_strength_bullet(letter: str, interpretations: Dict[str, Any], dims: Dict[str, Dict[str, Any]]) -> str:
    name = _get_dim_name(letter, interpretations, dims)
    area = _display_area_label(_get_dim_area(letter, interpretations, dims))
    text = _first_nonempty_sentence(_get_dim_text(letter, interpretations))
    base = f"{letter} — {name}"
    if area:
        base += f" ({area})"
    if text:
        return f"{base}: {text}"
    return f"{base}: indicador de força predominante no perfil atual."


def _compose_growth_bullet(letter: str, interpretations: Dict[str, Any], dims: Dict[str, Dict[str, Any]]) -> str:
    name = _get_dim_name(letter, interpretations, dims)
    area = _display_area_label(_get_dim_area(letter, interpretations, dims))
    text = _first_nonempty_sentence(_get_dim_text(letter, interpretations))
    base = f"{letter} — {name}"
    if area:
        base += f" ({area})"
    if text:
        return f"{base}: pode ser ampliado de forma intencional para gerar mais consistência nos resultados. {text}"
    return f"{base}: pode ser ampliado com prática deliberada e observação do comportamento no dia a dia."


def _compose_attention_bullet(letter: str, interpretations: Dict[str, Any], dims: Dict[str, Dict[str, Any]]) -> str:
    name = _get_dim_name(letter, interpretations, dims)
    area = _display_area_label(_get_dim_area(letter, interpretations, dims))
    text = _first_nonempty_sentence(_get_dim_text(letter, interpretations))
    base = f"{letter} — {name}"
    if area:
        base += f" ({area})"
    if text:
        return f"{base}: merece atenção no desenvolvimento para reduzir impacto funcional. {text}"
    return f"{base}: requer desenvolvimento intencional para reduzir riscos de baixa expressão no contexto atual."


def _build_sintese_risco_tipico(
    primary_letter: str,
    interpretations: Dict[str, Any],
    dims: Dict[str, Dict[str, Any]],
) -> str:
    dim_name = _get_dim_name(primary_letter, interpretations, dims)
    area = _display_area_label(_get_dim_area(primary_letter, interpretations, dims))
    text = _first_nonempty_sentence(_get_dim_text(primary_letter, interpretations))

    if text:
        return (
            f"O risco típico está no excesso ou uso pouco calibrado de {primary_letter} — {dim_name}"
            f"{f' ({area})' if area else ''}, especialmente quando essa força deixa de considerar contexto,"
            f" timing ou dosagem comportamental. {text}"
        )

    return (
        f"O risco típico está no excesso ou uso pouco calibrado de {primary_letter} — {dim_name}, "
        f"quando uma força dominante passa a operar sem ajuste ao contexto."
    )


def _build_sintese_recomendacao_objetiva(
    priority_letter: str,
    interpretations: Dict[str, Any],
    dims: Dict[str, Dict[str, Any]],
) -> str:
    dim_name = _get_dim_name(priority_letter, interpretations, dims)
    area = _display_area_label(_get_dim_area(priority_letter, interpretations, dims))
    dim_lower = str(dim_name or priority_letter).strip().lower()

    if area == "Gerencial":
        return (
            f"Como recomendação objetiva, priorize o desenvolvimento de {priority_letter} — {dim_name}"
            f" com uma prática semanal observável ligada à tomada de decisão, priorização ou qualidade da entrega."
        )
    if area == "Interpessoal":
        return (
            f"Como recomendação objetiva, priorize o desenvolvimento de {priority_letter} — {dim_name}"
            f" em interações recorrentes, treinando uma resposta comportamental simples e validando o efeito com feedback externo."
        )
    return (
        f"Como recomendação objetiva, priorize o desenvolvimento de {priority_letter} — {dim_name}"
        f" com repetição deliberada em situações do dia a dia, transformando {dim_lower} em comportamento mais consistente."
    )


def _build_sintese_executiva_payload(
    participant_payload: Dict[str, Any],
    ranking: Dict[str, Any],
    interpretations: Dict[str, Any],
    dims: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    top3 = _ordered_unique_letters([str(x) for x in (ranking.get("top3") or [])])
    top5 = _ordered_unique_letters([str(x) for x in (ranking.get("top5") or [])])
    bottom3 = _ordered_unique_letters([str(x) for x in (ranking.get("bottom3") or [])])

    destaques = [_compose_strength_bullet(letter, interpretations, dims) for letter in top3[:3]]
    ampliacao = [_compose_growth_bullet(letter, interpretations, dims) for letter in top5[:5]]
    atencao = [_compose_attention_bullet(letter, interpretations, dims) for letter in bottom3[:3]]

    nome = str(participant_payload.get("nome") or "").strip()
    tipo = _normalize_tipo_aplicacao(participant_payload.get("tipo_aplicacao"))
    tipo_label = tipo if tipo else "perfil avaliado"

    # Concordância de gênero dinâmica do artigo ("na empresa" vs. "no ambiente",
    # "no perfil avaliado", "no profissional", "no corporativo"/"na corporativa").
    artigo = "na" if str(tipo_label).strip().lower().endswith("a") else "no"

    top3_labels = ", ".join(
        f"{letter} ({_get_dim_name(letter, interpretations, dims)})"
        for letter in top3[:3]
    )

    dimensao_alta_principal = top3[0] if top3 else ""
    dimensao_baixa_prioritaria = bottom3[0] if bottom3 else ""

    risco_tipico = (
        _build_sintese_risco_tipico(dimensao_alta_principal, interpretations, dims)
        if dimensao_alta_principal
        else "O risco típico do perfil deve ser lido considerando o excesso ou subuso das forças predominantes no contexto."
    )

    recomendacao_objetiva = (
        _build_sintese_recomendacao_objetiva(dimensao_baixa_prioritaria, interpretations, dims)
        if dimensao_baixa_prioritaria
        else "Como recomendação objetiva, priorize uma prática comportamental concreta e observável nas dimensões de menor recorrência."
    )

    texto_base = (
        f"{nome or 'O participante'} apresenta como destaques principais "
        f"{top3_labels or 'dimensões de maior expressão'}, indicando padrões predominantes observáveis {artigo} {tipo_label}. "
        f"{risco_tipico} {recomendacao_objetiva}"
    )

    return {
        "texto": _trim_text(texto_base, max_len=900),
        "destaques_principais": destaques,
        "ampliacao_potencial": ampliacao,
        "pontos_atencao": atencao,
        "strengths": destaques,
        "growth": ampliacao,
        "attention": atencao,
        "dimensao_alta_principal": dimensao_alta_principal,
        "dimensao_baixa_prioritaria": dimensao_baixa_prioritaria,
        "risco_tipico": risco_tipico,
        "recomendacao_objetiva": recomendacao_objetiva,
    }


def _build_paineis_area_payload(
    scores: Dict[str, Any],
    bands: Dict[str, Any],
    interpretations: Dict[str, Any],
    dims: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[str]] = {
        "GERENCIAL": [],
        "INTER PESSOAL": [],
        "PESSOAL": [],
    }

    for letter in sorted(scores.keys()):
        grouped[_get_dim_area(letter, interpretations, dims)].append(letter)

    paineis: List[Dict[str, Any]] = []
    for area in ["GERENCIAL", "INTER PESSOAL", "PESSOAL"]:
        letters = grouped.get(area, [])
        ordered_letters = sorted(
            letters,
            key=lambda l: (-_get_dim_score(l, scores, interpretations), l),
        )

        structured_items: List[Dict[str, Any]] = []
        legacy_items: List[str] = []

        for letter in ordered_letters:
            item = {
                "letter": letter,
                "name": _get_dim_name(letter, interpretations, dims),
                "score": _get_dim_score(letter, scores, interpretations),
                "band": _band_label(_get_dim_band(letter, bands, interpretations)),
                "text": _get_dim_text(letter, interpretations),
            }
            structured_items.append(item)

            line = (
                f"{item['letter']} — {item['name']}: "
                f"Score {item['score']} • Faixa {item['band']}."
            )
            if item["text"]:
                line += f" {item['text']}"
            legacy_items.append(line)

        avg_score = round(
            (sum(_get_dim_score(letter, scores, interpretations) for letter in letters) / len(letters)),
            2,
        ) if letters else 0.0

        highlight = structured_items[0] if structured_items else None
        attention = structured_items[-1] if structured_items else None

        if structured_items:
            summary = (
                f"A área {_display_area_label(area)} apresenta média {avg_score}/10, "
                f"com maior recorrência em {highlight['letter']} — {highlight['name']} "
                f"e menor recorrência em {attention['letter']} — {attention['name']}."
            )
        else:
            summary = f"A área {_display_area_label(area)} não possui indicadores disponíveis."

        paineis.append(
            {
                "titulo": _display_area_label(area),
                "descricao": summary,
                "itens": legacy_items,
                "area": area,
                "average_score": avg_score,
                "media": avg_score,
                "items": structured_items,
                "highlight": highlight,
                "attention": attention,
                "summary": summary,
                "resumo": summary,
            }
        )

    return paineis


def _to_sentence(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.endswith("."):
        return text
    return f"{text}."


def _lower_name(value: str) -> str:
    return str(value or "").strip().lower()


def _normalize_axis_label(axis: str) -> str:
    return "potencializar" if axis == "potencializar" else "desenvolver"


def _default_competency_title(letter: str, dim_name: str) -> str:
    base = str(dim_name or letter).strip()
    if not base:
        return "Competência"
    return base


def _build_pdi_relevance(axis: str, competency: str, dim_name: str, interp_text: str) -> str:
    interp_sentence = _to_sentence(interp_text)

    if axis == "potencializar":
        prefix = (
            f"{competency} é relevante porque representa uma força já presente no perfil "
            f"e pode ser consolidada como padrão consciente de desempenho."
        )
    else:
        prefix = (
            f"{competency} é relevante porque representa uma prioridade objetiva de desenvolvimento "
            f"e tende a afetar consistência, qualidade de decisão ou efetividade relacional quando aparece com baixa recorrência."
        )

    if interp_sentence:
        return f"{prefix} {interp_sentence}"
    return f"{prefix} A competência está associada à dimensão {dim_name}."


def _build_pdi_actions(axis: str, competency: str, dim_name: str, area: str) -> List[str]:
    dim_lower = _lower_name(dim_name)
    area_upper = _normalize_area(area)

    if axis == "potencializar":
        if area_upper == "GERENCIAL":
            return [
                f"Escolher uma entrega real da semana para aplicar {dim_lower} de forma explícita.",
                "Registrar uma decisão prática em que a competência foi usada para elevar qualidade, clareza ou previsibilidade.",
                "Compartilhar com o gestor ou avaliador um exemplo concreto do uso da competência no trabalho.",
            ]
        if area_upper == "INTER PESSOAL":
            return [
                f"Usar {dim_lower} de forma deliberada em interações-chave da semana.",
                "Observar como a competência melhora alinhamento, vínculo ou clareza entre pessoas.",
                "Registrar uma situação em que o uso intencional da competência gerou melhor resposta do outro lado.",
            ]
        return [
            f"Aplicar {dim_lower} de forma consciente em uma situação prática do dia a dia.",
            "Escolher um contexto recorrente para transformar força natural em padrão consistente.",
            "Anotar um exemplo concreto em que a competência ajudou a sustentar resultado, estabilidade ou adaptação.",
        ]

    if area_upper == "GERENCIAL":
        return [
            f"Selecionar uma entrega da semana para praticar {dim_lower} com critério explícito.",
            "Quebrar a prática em um comportamento pequeno, observável e repetível por 2 semanas.",
            "Revisar ao fim da semana o que mudou em qualidade, previsibilidade ou tomada de decisão.",
        ]
    if area_upper == "INTER PESSOAL":
        return [
            f"Escolher uma interação recorrente para treinar {dim_lower} de forma objetiva.",
            "Praticar uma resposta comportamental simples antes, durante ou depois da conversa.",
            "Revisar com feedback externo se o comportamento ficou mais claro, estável e funcional.",
        ]
    return [
        f"Definir um contexto concreto para desenvolver {dim_lower} com repetição curta e deliberada.",
        "Transformar a competência em um hábito observável nas próximas 2 semanas.",
        "Encerrar cada semana com uma autoavaliação breve sobre consistência da prática.",
    ]


def _build_pdi_behaviors(axis: str, competency: str, dim_name: str, area: str) -> List[str]:
    dim_lower = _lower_name(dim_name)
    area_upper = _normalize_area(area)

    if axis == "potencializar":
        if area_upper == "GERENCIAL":
            return [
                f"Demonstra {dim_lower} de modo visível em decisões, priorização ou condução do trabalho.",
                "Mantém regularidade no uso da competência, sem depender apenas de esforço espontâneo.",
            ]
        if area_upper == "INTER PESSOAL":
            return [
                f"Expressa {dim_lower} de forma perceptível nas interações relevantes.",
                "Converte a competência em comportamento relacional observável, e não apenas intenção.",
            ]
        return [
            f"Usa {dim_lower} de forma consciente em situações recorrentes.",
            "Apresenta maior estabilidade do comportamento ao longo da rotina.",
        ]

    if area_upper == "GERENCIAL":
        return [
            f"Apresenta sinais concretos de avanço em {dim_lower} no trabalho.",
            "Mostra mais consistência entre intenção, execução e revisão da própria entrega.",
        ]
    if area_upper == "INTER PESSOAL":
        return [
            f"Exibe progresso observável em {dim_lower} nas relações e conversas do dia a dia.",
            "Reduz respostas automáticas e aumenta escolha consciente do comportamento.",
        ]
    return [
        f"Demonstra evolução prática em {dim_lower} em situações comuns da rotina.",
        "Mantém repetição suficiente para transformar tentativa em padrão inicial de comportamento.",
    ]


def _build_pdi_routine(axis: str, competency: str, dim_name: str, area: str) -> str:
    dim_lower = _lower_name(dim_name)
    if axis == "potencializar":
        return (
            f"Durante 2 semanas, escolher 1 situação por dia para aplicar {dim_lower} de forma intencional "
            f"e registrar em uma linha o contexto e o efeito percebido."
        )
    return (
        f"Durante 2 semanas, praticar 1 comportamento ligado a {dim_lower} em pelo menos 3 ocasiões por semana "
        f"e registrar o que facilitou ou dificultou a execução."
    )


def _build_pdi_indicator(axis: str, competency: str, dim_name: str, area: str) -> str:
    dim_lower = _lower_name(dim_name)
    if axis == "potencializar":
        return (
            f"Evidências observáveis de uso mais frequente e consciente de {dim_lower}, "
            f"validadas por autoavaliação breve e feedback do gestor/avaliador."
        )
    return (
        f"Aumento da consistência comportamental em {dim_lower}, com pelo menos 3 registros práticos "
        f"e 1 feedback externo confirmando evolução."
    )


def _build_pdi_item(
    *,
    letter: str,
    axis: str,
    interpretations: Dict[str, Any],
    dims: Dict[str, Dict[str, Any]],
    competency_map: Dict[str, str],
) -> Dict[str, Any]:
    dim_name = _get_dim_name(letter, interpretations, dims)
    area_raw = _get_dim_area(letter, interpretations, dims)
    area = _display_area_label(area_raw)
    interp_text = _get_dim_text(letter, interpretations)
    competency = (
        competency_map.get(letter)
        or _get_dim_competency(letter, interpretations, dims)
        or _default_competency_title(letter, dim_name)
    )
    axis_label = _normalize_axis_label(axis)

    porque_relevante = _build_pdi_relevance(axis_label, competency, dim_name, interp_text)
    acoes = _build_pdi_actions(axis_label, competency, dim_name, area_raw)
    comportamentos_alvo = _build_pdi_behaviors(axis_label, competency, dim_name, area_raw)
    rotina_pratica = _build_pdi_routine(axis_label, competency, dim_name, area_raw)
    indicador_evolucao = _build_pdi_indicator(axis_label, competency, dim_name, area_raw)

    descricao_curta = _to_sentence(interp_text) or f"Relacionada à dimensão {letter} — {dim_name}."

    return {
        "titulo": competency,
        "descricao": descricao_curta,
        "acoes": acoes,
        "eixo": axis_label,
        "letter": letter,
        "competencia": competency,
        "dimensao_nome": dim_name,
        "area": area,
        "porque_relevante": porque_relevante,
        "comportamentos_alvo": comportamentos_alvo,
        "rotina_pratica": rotina_pratica,
        "indicador_evolucao": indicador_evolucao,
    }


def _build_pdi_competencias_payload(
    ranking: Dict[str, Any],
    interpretations: Dict[str, Any],
    dims: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    competency_map = _load_dimension_competency_map()

    top3 = _ordered_unique_letters(_ranking_letters(ranking, "top3"))[:3]
    bottom3 = _ordered_unique_letters(_ranking_letters(ranking, "bottom3"))[:3]

    result: List[Dict[str, Any]] = []

    for letter in top3:
        result.append(
            _build_pdi_item(
                letter=letter,
                axis="potencializar",
                interpretations=interpretations,
                dims=dims,
                competency_map=competency_map,
            )
        )

    for letter in bottom3:
        result.append(
            _build_pdi_item(
                letter=letter,
                axis="desenvolver",
                interpretations=interpretations,
                dims=dims,
                competency_map=competency_map,
            )
        )

    return result


def _build_gestor_rh_payload(
    participant_payload: Dict[str, Any],
    ranking: Dict[str, Any],
    interpretations: Dict[str, Any],
    dims: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    tipo_aplicacao = _normalize_tipo_aplicacao(participant_payload.get("tipo_aplicacao"))
    if not _is_corporate_tipo(tipo_aplicacao):
        return {
            "enabled": False,
            "texto": "",
            "recomendacoes": [],
            "engajar": [],
            "feedback": [],
            "ambiente_ideal": [],
            "blocos": [],
        }

    premium_blocks = _load_premium_manager_blocks()

    engajar = _pick_first_bullets(
        premium_blocks.get("engajar") or premium_blocks.get("engajar_performance"),
        limit=3,
    )
    feedback = _pick_first_bullets(premium_blocks.get("feedback"), limit=3)
    ambiente = _pick_first_bullets(
        premium_blocks.get("ambiente_ideal") or premium_blocks.get("ambiente"),
        limit=3,
    )

    top3 = _ranking_letters(ranking, "top3")
    bottom3 = _ranking_letters(ranking, "bottom3")

    top_names = [f"{letter} — {_get_dim_name(letter, interpretations, dims)}" for letter in top3[:3]]
    bottom_names = [f"{letter} — {_get_dim_name(letter, interpretations, dims)}" for letter in bottom3[:3]]

    if not engajar:
        engajar = [
            f"Alocar atividades que aproveitem os destaques principais do perfil: {', '.join(top_names)}.",
            "Definir expectativas com clareza, escopo e critério objetivo de sucesso.",
            "Acompanhar evolução com checkpoints curtos e observáveis.",
        ]

    if not feedback:
        feedback = [
            "Dar feedback com exemplos concretos de comportamento observável.",
            f"Equilibrar reconhecimento das forças ({', '.join(top_names)}) com desenvolvimento dos pontos de atenção.",
            "Combinar próximo passo prático, prazo e evidência de evolução.",
        ]

    if not ambiente:
        ambiente = [
            "Oferecer contexto claro sobre prioridades, responsabilidades e entregáveis.",
            f"Observar as dimensões que pedem maior acompanhamento no momento: {', '.join(bottom_names)}.",
            "Ajustar ritmo, autonomia e proximidade de gestão conforme o contexto da função.",
        ]

    texto = (
        "Esta seção é destinada ao contexto organizacional e apoia leituras de desenvolvimento, "
        "alocação, acompanhamento e tomada de decisão com base no resultado consolidado do perfil."
    )

    blocos = [
        {"titulo": "Como engajar", "bullets": engajar},
        {"titulo": "Como dar feedback", "bullets": feedback},
        {"titulo": "Ambiente ideal", "bullets": ambiente},
    ]

    recomendacoes = engajar[:1] + feedback[:1] + ambiente[:1]

    return {
        "enabled": True,
        "texto": texto,
        "recomendacoes": recomendacoes,
        "engajar": engajar,
        "feedback": feedback,
        "ambiente_ideal": ambiente,
        "blocos": blocos,
    }


def _build_nota_tecnica_payload() -> Dict[str, Any]:
    texto = (
        "Este instrumento descreve tendências comportamentais a partir de autorrelato "
        "e deve ser analisado junto a contexto, histórico e observação. Recomenda-se "
        "uso para desenvolvimento, orientação e alinhamento de equipe."
    )

    texto_longo = (
        "Este relatório foi gerado a partir de um instrumento estruturado com 100 questões "
        "dicotômicas (A/B), processadas por motor determinístico de apuração conforme as "
        "regras do sistema. As respostas são convertidas em contagens por dimensão, "
        "classificadas em faixas interpretativas e consolidadas em rankings de maior e menor "
        "recorrência, preservando a lógica de leitura definida para o produto. "
        "O conteúdo apresentado deve ser utilizado como apoio à reflexão, desenvolvimento "
        "e tomada de decisão, considerando sempre o contexto de aplicação e a análise "
        "complementar do avaliador, gestor ou profissional responsável. "
        "Este material não substitui avaliação técnica complementar, entrevista estruturada, "
        "análise de contexto organizacional ou acompanhamento profissional quando aplicável."
    )

    return {
        "texto": texto,
        "texto_longo": texto_longo,
        "metodo": "Leitura baseada em 100 questões dicotômicas (A/B), com contagem determinística por dimensão.",
        "escala": "As dimensões são apresentadas em escala de 0 a 10, com faixas low/mid/high.",
        "criterio": "Top 3, Top 5 e Bottom 3 seguem ordenação determinística conforme o motor de scoring do produto.",
    }


async def _build_report_context(
    session: AsyncSession,
    *,
    attempt: Attempt,
    scores: Dict[str, Any],
    bands: Dict[str, Any],
    ranking: Dict[str, Any],
    interpretations: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Contexto canônico do relatório.

    Nesta fase:
      - participant/attempt vêm de dados reais
      - snapshot do submit passa a usar a mesma estrutura-base do relatório público
    """
    participant_payload = await _build_participant_payload(session, attempt)
    attempt_payload = _build_attempt_payload(attempt)
    dims = _load_dimensions_map()

    sintese_executiva = _build_sintese_executiva_payload(
        participant_payload=participant_payload,
        ranking=ranking,
        interpretations=interpretations,
        dims=dims,
    )
    paineis_area = _build_paineis_area_payload(
        scores=scores,
        bands=bands,
        interpretations=interpretations,
        dims=dims,
    )
    pdi_competencias = _build_pdi_competencias_payload(
        ranking=ranking,
        interpretations=interpretations,
        dims=dims,
    )
    gestor_rh = _build_gestor_rh_payload(
        participant_payload=participant_payload,
        ranking=ranking,
        interpretations=interpretations,
        dims=dims,
    )
    nota_tecnica = _build_nota_tecnica_payload()

    return {
        "token": "",
        "participant": participant_payload,
        "attempt": attempt_payload,
        "scores": scores,
        "bands": bands,
        "ranking": ranking,
        "interpretations": interpretations,
        "sintese_executiva": sintese_executiva,
        "paineis_area": paineis_area,
        "pdi_competencias": pdi_competencias,
        "gestor_rh": gestor_rh,
        "nota_tecnica": nota_tecnica,
        "report_template": "reports/report_full.html",
    }


async def submit_attempt(session: AsyncSession, attempt: Attempt):
    """
    Submit do attempt + computed_results (imutável) + report_snapshot (imutável).

    - Idempotente: se attempt já SUBMITTED, retorna computed existente.
    - Se não houver 100 respostas, levanta SubmitIncompleteError.
    """
    if attempt.status == "SUBMITTED":
        existing = await repo_result.get_computed_result_by_attempt_id(session, attempt.id)
        if existing:
            snap = await repo_result.get_report_snapshot_by_attempt_id(session, attempt.id)
            if not snap:
                ranking = _ranking_payload_from_lists(
                    (existing.top3 or {}).get("top3", []),
                    (existing.top5 or {}).get("top5", []),
                    (existing.bottom3 or {}).get("bottom3", []),
                )
                context = await _build_report_context(
                    session,
                    attempt=attempt,
                    scores=existing.scores or {},
                    bands=existing.bands or {},
                    ranking=ranking,
                    interpretations=existing.interpretations or {},
                )
                html = render_report_html(context)
                await repo_result.ensure_report_snapshot(session, attempt.id, html)
            return existing

    answers = await repo_attempt.list_answers_by_attempt_id(session, attempt.id)
    if len(answers) != 100:
        raise SubmitIncompleteError(f"Expected 100 answers, got {len(answers)}")

    ab_list: List[str] = [a.choice for a in answers]
    engine_res = compute_scores(ab_list)

    tipo_aplicacao = await repo_attempt.get_tipo_aplicacao_by_attempt(session, attempt)
    interpretations_payload = _build_interpretations_payload(
        engine_res.scores,
        engine_res.bands,
        tipo_aplicacao,
    )

    computed = await repo_result.upsert_computed_result(
        session=session,
        attempt_id=attempt.id,
        scores=engine_res.scores,
        bands=engine_res.bands,
        top3=engine_res.ranking.top3,
        top5=engine_res.ranking.top5,
        bottom3=engine_res.ranking.bottom3,
        interpretations=interpretations_payload,
        premium_data={},
    )

    attempt.status = "SUBMITTED"
    attempt.progress = 100
    attempt.data_conclusao = func.now()

    try:
        inv_id = getattr(attempt, "invite_id", None)
        if inv_id:
            await repo_invite.mark_invite_completed(session, invite_id=inv_id)
    except Exception:
        pass

    session.add(attempt)
    await session.flush()

    try:
        await session.refresh(attempt)
    except Exception:
        pass

    snap = await repo_result.get_report_snapshot_by_attempt_id(session, attempt.id)
    if not snap:
        ranking = _ranking_payload_from_lists(
            engine_res.ranking.top3,
            engine_res.ranking.top5,
            engine_res.ranking.bottom3,
        )
        context = await _build_report_context(
            session,
            attempt=attempt,
            scores=computed.scores or {},
            bands=computed.bands or {},
            ranking=ranking,
            interpretations=computed.interpretations or {},
        )
        html = render_report_html(context)
        await repo_result.ensure_report_snapshot(session, attempt.id, html)

    return computed
