from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.attempt import Attempt
from backend.models.result import ComputedResult
from backend.services.submit import (
    _build_attempt_payload,
    _build_paineis_area_payload,
    _build_participant_payload,
    _build_sintese_executiva_payload,
    _load_dimensions_map,
)



def _normalize_band_label(value: Any) -> str:
    raw = str(value or "").strip().lower()
    mapping = {
        "high": "Alto",
        "mid": "Médio",
        "low": "Baixo",
        "alto": "Alto",
        "médio": "Médio",
        "medio": "Médio",
        "baixo": "Baixo",
    }
    return mapping.get(raw, str(value or "").strip() or "Não informado")


def _resolve_area_label(letter: str, paineis_area: List[Dict[str, Any]]) -> str:
    for painel in paineis_area:
        area_label = str(painel.get("area_label") or painel.get("area") or "").strip()
        for item in painel.get("items", []) or []:
            item_letter = str(item.get("letter") or item.get("dim") or item.get("code") or "").strip()
            if item_letter == letter:
                return area_label
    return ""


def _safe_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _normalize_key(value: Any) -> str:
    raw = str(value or "").strip().lower()
    replacements = {
        "á": "a",
        "à": "a",
        "â": "a",
        "ã": "a",
        "é": "e",
        "ê": "e",
        "í": "i",
        "ó": "o",
        "ô": "o",
        "õ": "o",
        "ú": "u",
        "ç": "c",
        "/": " ",
        "-": " ",
        "(": " ",
        ")": " ",
        ".": " ",
        ",": " ",
    }
    for src, dst in replacements.items():
        raw = raw.replace(src, dst)
    return " ".join(raw.split())



def _format_assessment_datetime(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "Não informados"

    try:
        normalized = raw.replace("Z", "+00:00")
        if normalized.endswith("+0000"):
            normalized = normalized[:-5] + "+00:00"
        from datetime import datetime
        dt = datetime.fromisoformat(normalized)
        return dt.strftime("%d/%m/%Y às %H:%M")
    except Exception:
        return raw


def _sanitize_executive_summary_text(text: str) -> str:
    """
    Remove qualquer prefixo de letra de dimensão residual no formato "X (Nome)" ou
    "X — Nome" (ex.: "G (Ritmo de Execução)" -> "Ritmo de Execução"), deixando apenas
    o nome de exibição da competência. Funciona para qualquer letra A..T, não apenas
    para uma lista fixa, e suporta nomes com parênteses internos (ex.: "Obstinação
    (Persistência/Firmeza)").
    """
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""

    # "X (Nome)" -> "Nome" — qualquer letra única seguida de "(" vira apenas o conteúdo.
    cleaned = re.sub(r"\b[A-Z]\s*\(([^)]+)\)", r"\1", cleaned)

    # "X — Nome" / "X - Nome" (sem parênteses) -> "Nome"
    cleaned = re.sub(r"\b[A-Z]\s*[—-]\s*", "", cleaned)

    return " ".join(cleaned.split())


def _extract_executive_summary_text(value: Any) -> str:
    if isinstance(value, str):
        return " ".join(value.split()).strip()

    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str) and item.strip():
                parts.append(" ".join(item.split()).strip())
        return " ".join(parts).strip()

    if isinstance(value, dict):
        internal_keys = {
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
        }

        text_candidates = [
            value.get("texto_final"),
            value.get("texto"),
            value.get("summary"),
            value.get("resumo"),
        ]

        for candidate in text_candidates:
            if isinstance(candidate, str) and candidate.strip():
                return " ".join(candidate.split()).strip()

        if any(key in value for key in internal_keys):
            raise ValueError(
                "Premium context contract error: sintese_executiva dict contains internal keys and no approved final text field."
            )

    return ""


def _ranking_from_computed(computed_result: ComputedResult) -> Dict[str, Any]:
    return {
        "top3": _safe_list((computed_result.top3 or {}).get("top3", [])),
        "top5": _safe_list((computed_result.top5 or {}).get("top5", [])),
        "bottom3": _safe_list((computed_result.bottom3 or {}).get("bottom3", [])),
    }


def _dimension_name(letter: str, dims: Dict[str, Dict[str, Any]], interpretations: Dict[str, Any]) -> str:
    interp = interpretations.get(letter, {})
    if isinstance(interp, dict):
        name = interp.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()

    meta = dims.get(letter, {})
    raw = meta.get("name") or meta.get("nome") or letter
    return str(raw).strip()


def _dimension_text(letter: str, interpretations: Dict[str, Any]) -> str:
    interp = interpretations.get(letter, {})
    if isinstance(interp, dict):
        text = interp.get("text") or interp.get("texto")
        if isinstance(text, str) and text.strip():
            return " ".join(text.split()).strip()
    return ""


def _dimension_area(letter: str, dims: Dict[str, Dict[str, Any]]) -> Tuple[str, str]:
    meta = dims.get(letter, {}) or {}
    area = str(meta.get("area") or "").strip()
    area_label = str(meta.get("area_label") or "").strip()

    if area and area_label:
        return area, area_label

    normalized = _normalize_key(area or area_label)

    if "gerencial" in normalized:
        return "gerencial", "Gerencial"
    if "interpessoal" in normalized:
        return "interpessoal", "Interpessoal"
    if "pessoal" in normalized:
        return "pessoal", "Pessoal"

    return "geral", "Geral"


def _build_dimension_index(
    *,
    scores: Dict[str, Any],
    bands: Dict[str, Any],
    interpretations: Dict[str, Any],
    dims: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}

    for letter, score in (scores or {}).items():
        if not isinstance(letter, str):
            continue

        name = _dimension_name(letter, dims, interpretations)
        base_text = _dimension_text(letter, interpretations)
        area, area_label = _dimension_area(letter, dims)
        band = str((bands or {}).get(letter) or "").strip()

        try:
            score_int = int(score)
        except Exception:
            score_int = 0

        index[letter] = {
            "letter": letter,
            "name": name,
            "score": score_int,
            "band": band,
            "text": base_text,
            "area": area,
            "area_label": area_label,
        }

    return index


COMPETENCY_COPY: Dict[str, Dict[str, Dict[str, Any]]] = {
    "lideranca": {
        "top": {
            "impactos": "Amplia clareza de direção, coordenação de esforços e velocidade de alinhamento quando o contexto pede alguém capaz de assumir frente com segurança.",
            "dificuldades": "Quando usada em excesso, pode reduzir espaço de contribuição do grupo e transformar firmeza em centralização ou imposição.",
            "orientacao": "Avaliar como conduz prioridades, distribui responsabilidades e sustenta decisões sem absorver sozinho etapas que poderiam ser delegadas.",
            "tendencia": "No dia a dia, tende a puxar a frente da situação, organizar o rumo e ocupar naturalmente espaço de condução.",
            "impacto_esperado": "O fortalecimento desta competência tende a aumentar qualidade de direcionamento, coerência nas decisões e capacidade de mobilizar pessoas sem perder escuta e calibragem.",
            "sugestoes_treinamento": [
                "Treino de liderança situacional com cenários de delegação, alinhamento e cobrança equilibrada.",
                "Prática guiada de comunicação de direção com validação de entendimento da equipe.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Observar se a condução gera clareza e movimento sem sufocar autonomia do time.",
                "Dar feedback sobre dosagem entre firmeza, escuta, delegação e responsabilização.",
            ],
            "metas_comportamentais": [
                "Explicita direção e prioridade com mais clareza antes de iniciar a execução.",
                "Conduz reuniões ou decisões sem concentrar desnecessariamente todas as definições em si.",
            ],
            "indicador_evolucao": "Maior percepção de clareza de rumo pela equipe, com evidências de delegação mais funcional e condução firme sem excesso de centralização.",
            "acoes_praticas": [
                "Escolher uma decisão relevante da semana para comunicar objetivo, prioridade e critério de fechamento com clareza.",
                "Delegar uma etapa importante definindo resultado esperado e checkpoint, sem reassumir a tarefa antes do combinado.",
                "Registrar o efeito da sua condução sobre alinhamento, agilidade e autonomia do entorno.",
            ],
        },
        "bottom": {
            "impactos": "Seu desenvolvimento tende a aumentar capacidade de posicionamento, coordenação e presença funcional em situações que pedem direção mais explícita.",
            "dificuldades": "Baixa recorrência pode aparecer como hesitação em assumir frente, demora para definir rumo ou excesso de espera por validação externa.",
            "orientacao": "Criar oportunidades pequenas e frequentes para praticar condução objetiva, definição de prioridade e comunicação de encaminhamento.",
            "tendencia": "No cotidiano, pode preferir apoiar mais do que conduzir, mesmo quando o contexto já pede posicionamento mais claro.",
            "impacto_esperado": "O desenvolvimento desta competência tende a ampliar presença de liderança, autonomia de condução e segurança para definir caminhos em momentos decisivos.",
            "sugestoes_treinamento": [
                "Exercícios curtos de condução de pauta, priorização e fechamento de decisão.",
                "Role play de comunicação assertiva para assumir frente em situações de indefinição.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Estimular a pessoa a assumir pequenas lideranças de processo ou decisão.",
                "Reforçar feedbacks sobre momentos em que a condução foi clara e funcional.",
            ],
            "metas_comportamentais": [
                "Assume com mais frequência a condução de situações objetivas da rotina.",
                "Define encaminhamento com menor dependência de validação externa imediata.",
            ],
            "indicador_evolucao": "Aumento de episódios em que assume frente com clareza, define rumo e sustenta encaminhamento de forma funcional.",
            "acoes_praticas": [
                "Conduzir uma pauta curta da rotina definindo objetivo, prioridade e próximo passo.",
                "Em uma situação de indefinição, explicitar uma proposta concreta de encaminhamento.",
                "Revisar depois com o gestor o efeito da sua condução sobre clareza e andamento.",
            ],
        },
    },
    "decisao de risco": {
        "top": {
            "impactos": "Favorece avanço em cenários ambíguos, acelera movimento com responsabilidade e reduz paralisia quando a decisão precisa acontecer mesmo sem garantia total.",
            "dificuldades": "Se pouco calibrada, pode antecipar movimento, reduzir prudência ou elevar exposição além do que o contexto comporta.",
            "orientacao": "Observar como pondera risco aceitável, contingência e responsabilidade antes de avançar em contexto incompleto.",
            "tendencia": "Tende a decidir com agilidade e seguir adiante quando identifica probabilidade razoável de progresso.",
            "impacto_esperado": "O fortalecimento desta competência tende a melhorar qualidade de decisão sob incerteza, consciência de risco aceitável e segurança para avançar com responsabilidade.",
            "sugestoes_treinamento": [
                "Simulações de decisão com informação parcial e definição explícita de risco aceitável.",
                "Debrief de casos reais para separar coragem decisória de impulsividade.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Revisar o racional das decisões assumidas em cenário ambíguo.",
                "Dar feedback sobre qualidade da ponderação entre rapidez, prudência e contingência.",
            ],
            "metas_comportamentais": [
                "Explicita risco aceitável e critério de decisão antes de avançar.",
                "Equilibra rapidez com análise mínima de consequência e contingência.",
            ],
            "indicador_evolucao": "Decisões mais rápidas e mais bem justificadas em cenários ambíguos, com menor oscilação entre excesso de cautela e exposição desnecessária.",
            "acoes_praticas": [
                "Escolher uma decisão ambígua da rotina e escrever risco aceitável, ganho esperado e plano B em três linhas.",
                "Antes de decidir, diferenciar o que é incerteza tolerável do que é risco que exige contenção.",
                "Revisar depois do fato onde houve boa calibragem e onde houve excesso ou falta de prudência.",
            ],
        },
        "bottom": {
            "impactos": "Seu desenvolvimento tende a ampliar autonomia decisória, reduzir travamento sob ambiguidade e aumentar capacidade de agir com responsabilidade mesmo sem controle total do cenário.",
            "dificuldades": "Baixa recorrência pode aparecer como demora excessiva para decidir, busca contínua de segurança total ou dificuldade de assumir risco calculado.",
            "orientacao": "Trabalhar decisões de menor porte em que seja possível praticar avanço com critério, sem esperar certeza completa.",
            "tendencia": "No cotidiano, pode preferir mais garantias antes de se mover, mesmo quando o contexto já admite risco mensurado.",
            "impacto_esperado": "O desenvolvimento desta competência tende a dar mais fluidez à tomada de decisão, com avanço mais seguro e menos dependência de cenário totalmente controlado.",
            "sugestoes_treinamento": [
                "Exercícios de decisão progressiva com definição de risco controlado.",
                "Prática de análise rápida de cenário focada em impacto, reversibilidade e contingência.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Acompanhar onde a busca por certeza total está atrasando decisões relevantes.",
                "Validar pequenas decisões bem assumidas em contexto incompleto.",
            ],
            "metas_comportamentais": [
                "Assume decisões de menor porte com mais autonomia em cenário incompleto.",
                "Reduz a necessidade de garantias totais antes de se mover quando o risco é controlável.",
            ],
            "indicador_evolucao": "Maior número de decisões assumidas com risco mensurado e melhor equilíbrio entre cautela funcional e velocidade de ação.",
            "acoes_praticas": [
                "Selecionar uma decisão recorrente em que a espera por segurança total costuma atrasar o avanço.",
                "Definir um limite claro de informação suficiente para agir com responsabilidade.",
                "Registrar o que mudou no tempo de resposta e na qualidade do avanço após usar esse critério.",
            ],
        },
    },
    "obstinacao persistencia firmeza": {
        "top": {
            "impactos": "Sustenta esforço em cenário difícil, aumenta resistência à pressão e favorece continuidade quando o contexto exige firmeza e constância.",
            "dificuldades": "Quando excessiva, pode endurecer a rota, reduzir flexibilidade e transformar persistência útil em insistência improdutiva.",
            "orientacao": "Observar não apenas quanto insiste, mas em que momento flexibiliza com inteligência diante de novos dados.",
            "tendencia": "Tende a sustentar posição, atravessar dificuldade e não desistir com facilidade do que considera importante.",
            "impacto_esperado": "O fortalecimento desta competência tende a ampliar resiliência prática sem rigidez, preservando firmeza com mais capacidade de ajustar rota quando necessário.",
            "sugestoes_treinamento": [
                "Treino de resiliência aplicada com distinção entre firmeza útil e rigidez.",
                "Estudo de casos sobre persistência estratégica e revisão inteligente de rota.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Avaliar se a pessoa mantém constância sem se fechar a ajuste de caminho.",
                "Dar feedback sobre momentos em que insistência foi útil e quando já pedia flexibilização.",
            ],
            "metas_comportamentais": [
                "Sustenta esforço em cenário difícil sem perder leitura de contexto.",
                "Flexibiliza estratégia quando os sinais mostram que a insistência deixou de ser útil.",
            ],
            "indicador_evolucao": "Maior capacidade de sustentar pressão com firmeza e, ao mesmo tempo, revisar rota com maturidade quando o contexto muda.",
            "acoes_praticas": [
                "Escolher um desafio real que exija continuidade mesmo sob desconforto ou resistência.",
                "Definir antes um critério de insistência útil e um critério claro de revisão de rota.",
                "Registrar ao final se a persistência fortaleceu o resultado ou se pediu ajuste mais cedo.",
            ],
        },
        "bottom": {
            "impactos": "Seu desenvolvimento tende a aumentar consistência frente a obstáculos, capacidade de sustentar esforço e maior estabilidade diante de frustração ou resistência.",
            "dificuldades": "Baixa recorrência pode surgir como desistência precoce, queda de energia diante de barreira ou dificuldade de sustentar direção sob pressão.",
            "orientacao": "Criar metas curtas com acompanhamento visível para treinar continuidade mesmo quando o retorno não é imediato.",
            "tendencia": "No cotidiano, pode interromper o movimento antes do ponto necessário quando encontra resistência ou desconforto.",
            "impacto_esperado": "O desenvolvimento desta competência tende a fortalecer constância de execução e maior capacidade de atravessar pressão sem abandonar cedo demais o que é importante.",
            "sugestoes_treinamento": [
                "Treino de continuidade e resiliência com metas curtas e revisão semanal.",
                "Exercícios de tolerância a frustração e manutenção de esforço em cenário adverso.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Monitorar pontos em que a pessoa interrompe cedo demais um esforço relevante.",
                "Reforçar evidências de constância e atravessamento produtivo de dificuldade.",
            ],
            "metas_comportamentais": [
                "Mantém esforço por mais tempo quando encontra resistência ou desconforto.",
                "Reduz abandono precoce de ações relevantes antes de testar ajuste viável.",
            ],
            "indicador_evolucao": "Mais episódios de continuidade sob pressão, com menor desistência precoce diante de obstáculos da rotina.",
            "acoes_praticas": [
                "Selecionar uma tarefa ou projeto em que costuma ceder cedo diante de dificuldade.",
                "Definir um ponto mínimo de continuidade antes de reavaliar se vale parar.",
                "Registrar semanalmente onde conseguiu sustentar esforço além do padrão anterior.",
            ],
        },
    },
    "ambicao resultados carreira": {
        "top": {
            "impactos": "Eleva senso de meta, direciona energia para progresso e favorece mobilização para resultados relevantes.",
            "dificuldades": "Se pouco calibrada, pode gerar aceleração excessiva, impaciência com o ritmo dos outros e foco estreito apenas em entrega.",
            "orientacao": "Observar como busca resultado preservando qualidade, sustentabilidade e leitura de impacto no entorno.",
            "tendencia": "Tende a se orientar por avanço, meta e crescimento com energia prática para produzir movimento.",
            "impacto_esperado": "O fortalecimento desta competência tende a ampliar tração para resultado sem perda de qualidade, consistência e maturidade na condução do próprio crescimento.",
            "sugestoes_treinamento": [
                "Treino de gestão de metas com equilíbrio entre ambição, qualidade e sustentabilidade.",
                "Exercícios de priorização focados em resultado com leitura de impacto sobre o entorno.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Avaliar como persegue meta sem sacrificar relacionamento, processo ou qualidade.",
                "Dar feedback sobre equilíbrio entre velocidade, entrega e sustentabilidade.",
            ],
            "metas_comportamentais": [
                "Mantém foco em resultado com melhor calibragem entre intensidade e qualidade.",
                "Conecta ambição de crescimento a execução consistente e sustentável.",
            ],
            "indicador_evolucao": "Resultados perseguidos com maior equilíbrio entre velocidade, qualidade e impacto relacional no contexto de trabalho.",
            "acoes_praticas": [
                "Escolher uma meta importante e explicitar critérios de qualidade além do número final.",
                "Revisar semanalmente se a busca por resultado está preservando consistência e relação com o entorno.",
                "Registrar onde a ambição acelerou de forma saudável e onde pediu mais dosagem.",
            ],
        },
        "bottom": {
            "impactos": "Seu desenvolvimento tende a aumentar tração para resultado, maior senso de progressão e disposição mais concreta para assumir desafios.",
            "dificuldades": "Baixa recorrência pode aparecer como acomodação, menor urgência para avanço ou dificuldade de se mobilizar para metas mais desafiadoras.",
            "orientacao": "Trabalhar metas claras, de curto prazo, com ganhos visíveis e revisão objetiva de evolução.",
            "tendencia": "No cotidiano, pode manter ritmo funcional, porém com menor impulso espontâneo para crescimento ou conquista mais agressiva.",
            "impacto_esperado": "O desenvolvimento desta competência tende a ampliar energia para desafio, posicionamento diante de meta e maior iniciativa orientada a progresso.",
            "sugestoes_treinamento": [
                "Treino de definição de meta com marco curto e revisão de evolução.",
                "Exercícios de planejamento de progresso com foco em visibilidade de avanço.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Ajudar a transformar metas amplas em marcos observáveis de curto prazo.",
                "Reforçar progresso concreto para estimular maior tração de crescimento.",
            ],
            "metas_comportamentais": [
                "Assume metas com maior senso de avanço e responsabilização pelo progresso.",
                "Demonstra iniciativa mais explícita diante de desafios relevantes da rotina.",
            ],
            "indicador_evolucao": "Maior energia para perseguir metas e mais evidências de iniciativa voltada a crescimento e progresso concreto.",
            "acoes_praticas": [
                "Definir uma meta curta e objetiva para a semana com critério claro de sucesso.",
                "Identificar uma ação que antecipe resultado, sem esperar apenas demanda externa.",
                "Revisar no fim da semana se houve mais movimento prático em direção ao que deseja construir.",
            ],
        },
    },
    "confrontacao pessoal assertividade conflito": {
        "top": {
            "impactos": "Favorece franqueza funcional, sustentação de posição e capacidade de lidar com divergência sem evitamento excessivo.",
            "dificuldades": "Se exagerada, pode aumentar dureza, elevar tensão relacional ou fazer a conversa perder nuance e escuta.",
            "orientacao": "Observar como sustenta divergência preservando precisão, respeito e ajuste de intensidade conforme o interlocutor e o tema.",
            "tendencia": "Tende a colocar pontos difíceis na mesa quando percebe necessidade de enfrentamento objetivo.",
            "impacto_esperado": "O fortalecimento desta competência tende a melhorar assertividade madura, enfrentamento produtivo de divergências e clareza em conversas sensíveis.",
            "sugestoes_treinamento": [
                "Treino de conversas difíceis com foco em firmeza, escuta e regulação de intensidade.",
                "Role play de feedback franco com preservação de vínculo e objetivo da conversa.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Avaliar como confronta temas difíceis sem escalar desnecessariamente a tensão.",
                "Dar feedback sobre clareza, escuta e dosagem da assertividade em conversas sensíveis.",
            ],
            "metas_comportamentais": [
                "Sustenta posição com clareza sem endurecer além do necessário.",
                "Enfrenta divergência preservando respeito, escuta e objetivo funcional da conversa.",
            ],
            "indicador_evolucao": "Maior qualidade em conversas de divergência, com assertividade útil e menor geração de ruído relacional desnecessário.",
            "acoes_praticas": [
                "Escolher uma conversa delicada e preparar antes qual ponto precisa ser dito com objetividade.",
                "Durante a conversa, verificar se está sustentando posição e também escutando o retorno do outro.",
                "Revisar depois se a firmeza ajudou a resolver ou se a intensidade poderia ter sido melhor dosada.",
            ],
        },
        "bottom": {
            "impactos": "Seu desenvolvimento tende a ampliar capacidade de dizer o que precisa ser dito, reduzir evitamento de conflito e aumentar clareza em conversas sensíveis.",
            "dificuldades": "Baixa recorrência pode surgir como dificuldade de confrontar o necessário, excesso de acomodação ou adiamento de conversas importantes.",
            "orientacao": "Treinar enfrentamento gradual de divergências objetivas, começando por temas claros e com baixo risco relacional.",
            "tendencia": "No cotidiano, pode poupar confronto demais e deixar pontos importantes sem explicitação no momento adequado.",
            "impacto_esperado": "O desenvolvimento desta competência tende a dar mais franqueza funcional às interações, com menor evitamento e maior clareza nas conversas necessárias.",
            "sugestoes_treinamento": [
                "Prática de assertividade básica em conversas de alinhamento e correção de rota.",
                "Exercícios de formulação de discordância respeitosa com foco em objetividade.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Acompanhar se temas importantes estão sendo evitados ou postergados.",
                "Reforçar positivamente episódios em que conseguiu confrontar de forma clara e funcional.",
            ],
            "metas_comportamentais": [
                "Expõe pontos relevantes com menor evitamento em situações que pedem clareza.",
                "Aborda divergências objetivas antes que se tornem acúmulo silencioso de tensão.",
            ],
            "indicador_evolucao": "Mais conversas necessárias realizadas com objetividade, menor adiamento de temas sensíveis e maior clareza relacional.",
            "acoes_praticas": [
                "Escolher um tema pequeno que está sendo evitado e trazê-lo para conversa com objetividade.",
                "Usar uma estrutura simples: fato observado, impacto e pedido claro.",
                "Registrar como se sentiu antes e depois de enfrentar a conversa de modo funcional.",
            ],
        },
    },
    "repressao emocional autocontrole expressao": {
        "top": {
            "impactos": "Favorece estabilidade de resposta, preserva clareza sob pressão e ajuda a regular expressão emocional em contexto sensível.",
            "dificuldades": "Quando excessiva, pode endurecer a expressão, dificultar acesso relacional e passar impressão de distância emocional.",
            "orientacao": "Observar se o controle emocional preserva funcionalidade sem bloquear presença, abertura e leitura humana da situação.",
            "tendencia": "Tende a responder com maior contenção e regulação emocional diante de tensão ou pressão.",
            "impacto_esperado": "O fortalecimento desta competência tende a consolidar estabilidade emocional madura, com resposta funcional sem esfriamento excessivo do vínculo.",
            "sugestoes_treinamento": [
                "Treino de regulação emocional com foco em equilíbrio entre controle e presença.",
                "Exercícios de leitura de impacto relacional da própria expressão sob pressão.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Observar se a contenção emocional mantém clareza sem gerar frieza excessiva.",
                "Dar feedback sobre equilíbrio entre estabilidade, presença e comunicação humana.",
            ],
            "metas_comportamentais": [
                "Mantém estabilidade emocional sem perder contato relacional com o contexto.",
                "Regula expressão sob pressão preservando clareza e presença funcional.",
            ],
            "indicador_evolucao": "Respostas mais estáveis e funcionais sob pressão, com equilíbrio entre autocontrole e presença relacional.",
            "acoes_praticas": [
                "Mapear uma situação de pressão em que costuma conter demais a expressão e verificar o efeito sobre o outro.",
                "Treinar resposta regulada que preserve clareza sem esfriar excessivamente a interação.",
                "Registrar quando conseguiu equilibrar estabilidade emocional e presença funcional.",
            ],
        },
        "bottom": {
            "impactos": "Seu desenvolvimento tende a reduzir reatividade, ampliar estabilidade de resposta e melhorar a qualidade da interação em contextos de pressão ou frustração.",
            "dificuldades": "Baixa recorrência pode aparecer como resposta no calor do momento, oscilação expressiva e dificuldade de conter impulso emocional.",
            "orientacao": "Trabalhar pausas curtas antes de responder, nomeação do estado emocional e revisão posterior de episódios críticos.",
            "tendencia": "No cotidiano, pode reagir com mais espontaneidade emocional do que o contexto funcional recomendaria.",
            "impacto_esperado": "O desenvolvimento desta competência tende a aumentar capacidade de sustentar clareza, timing de resposta e estabilidade emocional em interações sensíveis.",
            "sugestoes_treinamento": [
                "Treino breve de autorregulação emocional aplicado a conversas reais da rotina.",
                "Prática de pausa, respiração e nomeação do estado emocional antes de responder sob pressão.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Acompanhar episódios de contrariedade ou frustração e revisar o padrão de resposta.",
                "Dar feedback específico sobre tom, tempo de reação e impacto relacional da resposta emocional.",
            ],
            "metas_comportamentais": [
                "Reduz respostas automáticas em situações de pressão, contrariedade ou frustração.",
                "Demonstra maior capacidade de pausar e escolher a forma de responder em interações sensíveis.",
            ],
            "indicador_evolucao": "Menor frequência de respostas impulsivas e mais episódios em que regula emoção antes de agir ou responder.",
            "acoes_praticas": [
                "Identificar uma conversa recorrente em que a reação emocional costuma subir rápido.",
                "Praticar uma pausa curta antes de responder e nomear internamente o estado emocional.",
                "Revisar após a interação o que ajudou a manter estabilidade e clareza.",
            ],
        },
    },
    "envolvimento afetivo empatia vinculo": {
        "top": {
            "impactos": "Favorece vínculo, sensibilidade relacional e maior capacidade de perceber como a postura é recebida pelo outro.",
            "dificuldades": "Quando excessiva, pode aumentar envolvimento pessoal demais, dificultar objetividade ou tornar mais difícil delimitar fronteiras funcionais.",
            "orientacao": "Observar se a empatia está ajudando vínculo e cooperação sem prejudicar objetividade, limite e foco de trabalho.",
            "tendencia": "Tende a perceber o outro com mais proximidade e demonstrar presença relacional de forma espontânea.",
            "impacto_esperado": "O fortalecimento desta competência tende a consolidar vínculo profissional de qualidade, escuta mais sensível e cooperação mais fluida nas relações de trabalho.",
            "sugestoes_treinamento": [
                "Treino de empatia aplicada com equilíbrio entre proximidade e objetividade.",
                "Exercícios de escuta ativa com devolutiva breve do que foi compreendido.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Avaliar se a sensibilidade relacional está gerando vínculo sem perda de foco funcional.",
                "Reforçar evidências de escuta, presença e boa leitura do impacto sobre o outro.",
            ],
            "metas_comportamentais": [
                "Mantém presença relacional sem perder objetividade no contexto profissional.",
                "Usa escuta e empatia de modo funcional para melhorar vínculo e cooperação.",
            ],
            "indicador_evolucao": "Interações com maior qualidade de vínculo e escuta, mantendo equilíbrio entre proximidade e foco funcional.",
            "acoes_praticas": [
                "Escolher uma interação relevante para praticar escuta ativa com devolutiva curta do que compreendeu.",
                "Perguntar ao menos uma vez como o outro percebeu a situação antes de apresentar a própria solução.",
                "Registrar se isso aumentou confiança, clareza ou cooperação.",
            ],
        },
        "bottom": {
            "impactos": "Seu desenvolvimento tende a melhorar vínculo, qualidade de escuta e percepção de como sua postura é recebida pelos outros.",
            "dificuldades": "Baixa recorrência pode aparecer como interação mais técnica, distância afetiva e menor demonstração prática de empatia.",
            "orientacao": "Trabalhar perguntas de compreensão, validação curta do outro e demonstração objetiva de presença relacional.",
            "tendencia": "Pode ser percebido como correto e funcional, porém mais distante ou contido no plano afetivo.",
            "impacto_esperado": "O desenvolvimento desta competência tende a ampliar qualidade de vínculo profissional, escuta percebida e capacidade de gerar proximidade funcional sem perder objetividade.",
            "sugestoes_treinamento": [
                "Prática guiada de escuta ativa, empatia aplicada e leitura de impacto relacional.",
                "Role play de conversas com foco em presença, vínculo e objetividade.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Observar sinais práticos de escuta, validação e qualidade de vínculo nas interações.",
                "Coletar feedback de pares sobre proximidade, abertura e percepção de presença relacional.",
            ],
            "metas_comportamentais": [
                "Demonstra mais escuta percebida e validação objetiva nas interações relevantes.",
                "Reduz distância relacional excessiva em conversas que pedem presença humana mais explícita.",
            ],
            "indicador_evolucao": "Maior percepção externa de abertura, escuta e presença relacional, com melhoria da qualidade do vínculo profissional.",
            "acoes_praticas": [
                "Escolher uma interação importante da semana para praticar escuta ativa e validação objetiva do outro.",
                "Fazer pelo menos uma pergunta de compreensão antes de responder tecnicamente.",
                "Registrar como a qualidade do vínculo influenciou clareza, confiança ou cooperação.",
            ],
        },
    },
    "gosto pela inovacao": {
        "top": {
            "impactos": "Favorece abertura para melhoria, experimentação útil e adaptação mais rápida a novos caminhos, métodos ou soluções.",
            "dificuldades": "Quando excessiva, pode reduzir aderência a padrão necessário, aumentar dispersão ou gerar mudança sem ganho real.",
            "orientacao": "Observar se a abertura para o novo está preservando consistência, processo e critério de valor agregado.",
            "tendencia": "Tende a experimentar, questionar o modo atual e testar alternativas com mais naturalidade.",
            "impacto_esperado": "O fortalecimento desta competência tende a ampliar melhoria contínua com critério, abertura para experimento útil e adaptação mais inteligente a mudanças.",
            "sugestoes_treinamento": [
                "Workshop prático de melhoria contínua com teste controlado e revisão de aprendizado.",
                "Exercícios de inovação aplicada com foco em ganho real, critério e segurança.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Avaliar se as mudanças propostas geram ganho concreto sem perder estabilidade necessária.",
                "Dar feedback sobre equilíbrio entre inovação útil, disciplina de processo e consistência.",
            ],
            "metas_comportamentais": [
                "Propõe melhorias com critério de valor agregado e impacto real.",
                "Experimenta sem perder estabilidade nos pontos que exigem padronização.",
            ],
            "indicador_evolucao": "Mais iniciativas de melhoria com boa relação entre novidade, segurança e ganho concreto para a rotina ou processo.",
            "acoes_praticas": [
                "Selecionar uma rotina estável e propor um microteste de melhoria com escopo controlado.",
                "Definir antes o que precisa permanecer estável e o que pode entrar em experimento.",
                "Revisar no fim da semana se houve ganho real sem perda de consistência.",
            ],
        },
        "bottom": {
            "impactos": "Seu desenvolvimento tende a ampliar adaptabilidade, experimentação segura e abertura prática para melhoria contínua.",
            "dificuldades": "Baixa recorrência pode surgir como apego ao conhecido, resistência a teste e preferência forte por estabilidade já dominada.",
            "orientacao": "Criar pequenos experimentos controlados, separar áreas estáveis de áreas de teste e revisar ganho real com segurança.",
            "tendencia": "Tende a preferir método conhecido, previsibilidade e mudança apenas quando a necessidade já está muito evidente.",
            "impacto_esperado": "O desenvolvimento desta competência tende a aumentar flexibilidade diante de mudança, abertura a experimento controlado e capacidade de inovar com segurança.",
            "sugestoes_treinamento": [
                "Treino de melhoria contínua com experimento curto e revisão de aprendizado.",
                "Workshop prático sobre equilíbrio entre inovação, estabilidade e padronização.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Avaliar disposição para testar melhoria sem comprometer segurança do processo.",
                "Revisar se a pessoa consegue diferenciar inovação útil de mudança desnecessária.",
            ],
            "metas_comportamentais": [
                "Testa pequenas melhorias controladas sem depender apenas de mudança já imposta pelo contexto.",
                "Amplia abertura para ajustes e experimentos mantendo segurança do que precisa permanecer estável.",
            ],
            "indicador_evolucao": "Mais evidências de teste controlado, abertura a mudança útil e menor apego automático apenas ao método já conhecido.",
            "acoes_praticas": [
                "Definir uma pequena melhoria controlada para testar em processo ou rotina conhecida.",
                "Separar o que precisa permanecer estável do que pode entrar em experimento.",
                "Ao final da semana, revisar se a mudança trouxe ganho real sem perder consistência.",
            ],
        },
    },
    "ritmo de execucao": {
        "top": {
            "impactos": "Acelera entregas, reduz tempo de resposta e mantém o time em movimento mesmo sob pressão de prazo, funcionando como motor de produtividade em contextos de alta demanda.",
            "dificuldades": "Quando o ritmo não é calibrado, pode gerar atropelo de etapas críticas, comunicação apressada e desgaste da própria energia ou da equipe ao redor.",
            "orientacao": "Potencializar o Ritmo de Execução é fundamental para transformar o senso de urgência nativo em uma alavanca estratégica, garantindo que a alta velocidade de entrega seja combinada com planejamento para evitar o esgotamento produtivo ou o atropelo de processos críticos.",
            "tendencia": "Tende a priorizar velocidade e ação imediata, buscando destravar gargalos e entregar rápido mesmo quando o cenário pede mais cautela.",
            "impacto_esperado": "O refino desta força consolida a capacidade do profissional de liderar projetos de alta pressão, mantendo a consistência tática e entregando resultados complexos em prazos agressivos sem perda de qualidade estrutural.",
            "sugestoes_treinamento": [
                "Treino de gestão de ritmo com técnicas de priorização sob pressão e identificação de etapas não negociáveis.",
                "Prática de planejamento rápido (sprint planning) para conciliar velocidade com checkpoints de qualidade.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Acompanhar se a velocidade de entrega está sendo acompanhada de qualidade estrutural ou se está gerando retrabalho.",
                "Dar feedback sobre momentos em que a urgência ajudou o time e momentos em que atropelou etapas necessárias.",
            ],
            "metas_comportamentais": [
                "Define, antes de acelerar, quais etapas do processo são inegociáveis e não podem ser puladas.",
                "Comunica prazos agressivos de forma clara ao time, sem transferir pressão de forma desorganizada.",
            ],
            "indicador_evolucao": "Mais entregas rápidas sustentadas por planejamento prévio, com redução de retrabalho e de sinais de esgotamento no próprio ritmo de trabalho.",
            "acoes_praticas": [
                "Antes de iniciar uma entrega urgente, mapear em poucos minutos as etapas que não podem ser puladas mesmo sob pressão.",
                "Negociar com o gestor um checkpoint intermediário em entregas de alta velocidade para validar qualidade antes do prazo final.",
                "Registrar ao final de semanas de alta demanda o que funcionou e onde o ritmo gerou desgaste evitável.",
            ],
        },
        "bottom": {
            "impactos": "Seu desenvolvimento tende a reduzir o tempo entre decisão e ação, aumentar a capacidade de resposta em cenários de urgência e ampliar a percepção de confiabilidade nas entregas com prazo.",
            "dificuldades": "Baixa recorrência pode aparecer como demora para iniciar tarefas, excesso de planejamento antes de agir ou dificuldade de manter ritmo quando a pressão aumenta.",
            "orientacao": "Desenvolver o Ritmo de Execução é importante para reduzir a hesitação na partida de tarefas e ampliar a capacidade de responder com agilidade a demandas que exigem decisão e movimento rápidos, sem depender de pressão externa para agir.",
            "tendencia": "No cotidiano, tende a preferir avançar com calma e revisão extensa, mesmo em situações que pedem resposta mais rápida e decisão imediata.",
            "impacto_esperado": "O fortalecimento desta competência tende a aumentar a velocidade de resposta em situações de prazo apertado, reduzindo atrasos por excesso de análise e ampliando a confiança do time na sua capacidade de entregar dentro do tempo necessário.",
            "sugestoes_treinamento": [
                "Exercícios de execução cronometrada para treinar tomada de ação mais rápida em tarefas de menor risco.",
                "Prática de priorização ágil (matriz de urgência/impacto) para reduzir tempo de decisão antes de agir.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Atribuir tarefas com prazos curtos e acompanhar a evolução do tempo de resposta.",
                "Dar feedback específico sobre o ganho de agilidade quando a entrega rápida foi bem-sucedida.",
            ],
            "metas_comportamentais": [
                "Reduz o tempo entre o recebimento de uma demanda e o início da execução.",
                "Assume entregas com prazo mais curto sem represar a tarefa por excesso de planejamento prévio.",
            ],
            "indicador_evolucao": "Redução do tempo médio de resposta a demandas urgentes, com mais evidências de entregas dentro do prazo sem necessidade de pressão externa contínua.",
            "acoes_praticas": [
                "Escolher uma tarefa da semana e definir um prazo deliberadamente mais curto do que o habitual para praticar execução ágil.",
                "Limitar o tempo de planejamento de uma atividade simples antes de iniciar a ação.",
                "Registrar o que mudou na qualidade da entrega ao reduzir o tempo de preparação antes de agir.",
            ],
        },
    },
    "necessidade de se comunicar": {
        "top": {
            "impactos": "Amplia alinhamento entre áreas, acelera a circulação de informação relevante e fortalece a capacidade de influenciar decisões por meio de comunicação clara e frequente.",
            "dificuldades": "Quando o volume de comunicação não é calibrado, pode gerar excesso de informação, diluição de mensagens-chave ou cansaço comunicacional no time.",
            "orientacao": "Aprimorar a Necessidade de se Comunicar permite canalizar a habilidade natural de articulação para uma comunicação mais assertiva e focada em resultados, transformando o volume de interações em ferramentas de alinhamento estratégico e influência executiva.",
            "tendencia": "Tende a buscar contato frequente, compartilhar informação com facilidade e manter o entorno atualizado de forma espontânea.",
            "impacto_esperado": "O fortalecimento intencional desta competência reduz drasticamente os ruídos internos na equipe, acelera a descentralização de informações críticas e aumenta o engajamento dos stakeholders por meio de narrativas claras e direcionadas.",
            "sugestoes_treinamento": [
                "Treino de comunicação executiva com foco em síntese e mensagem-chave.",
                "Prática de storytelling estratégico para transformar informação em narrativa de influência.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Observar se a comunicação está sendo direcionada às mensagens mais relevantes ou se está dispersa em volume excessivo.",
                "Dar feedback sobre o impacto da comunicação em momentos de alinhamento estratégico.",
            ],
            "metas_comportamentais": [
                "Estrutura mensagens-chave antes de comunicar decisões ou atualizações relevantes.",
                "Calibra a frequência de comunicação ao contexto e à audiência, evitando excesso de ruído.",
            ],
            "indicador_evolucao": "Mensagens mais objetivas e direcionadas, com evidências de maior engajamento e menor necessidade de repetição para garantir alinhamento.",
            "acoes_praticas": [
                "Antes de uma comunicação importante, definir em uma frase qual é a mensagem central a ser transmitida.",
                "Reduzir o número de canais usados para uma mesma informação, concentrando-a em um ponto de referência claro.",
                "Pedir feedback de um stakeholder sobre a clareza e objetividade de uma comunicação recente.",
            ],
        },
        "bottom": {
            "impactos": "Seu desenvolvimento tende a reduzir ruídos por falta de informação, aumentar a visibilidade do trabalho realizado e fortalecer vínculos com áreas e pessoas que dependem de atualização frequente.",
            "dificuldades": "Baixa recorrência pode aparecer como atualização tardia de informações relevantes, baixa visibilidade do progresso real do trabalho ou dependência de que outros perguntem para obter dados importantes.",
            "orientacao": "Desenvolver a Necessidade de se Comunicar é relevante para reduzir o isolamento informacional, ampliar a visibilidade do próprio trabalho e garantir que decisões e avanços relevantes não fiquem represados por baixa frequência de troca com o entorno.",
            "tendencia": "No cotidiano, tende a comunicar apenas quando estritamente necessário, podendo deixar o entorno sem contexto suficiente sobre o andamento real das atividades.",
            "impacto_esperado": "O desenvolvimento desta competência tende a aumentar a circulação de informações importantes, reduzir mal-entendidos por falta de atualização e fortalecer a percepção de presença e contribuição ativa dentro da equipe.",
            "sugestoes_treinamento": [
                "Prática estruturada de comunicação proativa de status, com roteiro simples de atualização.",
                "Treino de comunicação assertiva para reduzir o desconforto de compartilhar informação com mais frequência.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Criar momentos regulares e previsíveis para que a pessoa compartilhe atualizações de forma estruturada.",
                "Reforçar positivamente quando a comunicação proativa evitar um problema ou acelerar uma decisão.",
            ],
            "metas_comportamentais": [
                "Compartilha atualizações relevantes sem esperar ser questionado sobre o andamento do trabalho.",
                "Amplia a frequência de comunicação com stakeholders-chave em momentos críticos do projeto.",
            ],
            "indicador_evolucao": "Mais episódios de comunicação proativa registrados, com redução de situações em que informação relevante chegou tarde ao time ou ao gestor.",
            "acoes_praticas": [
                "Definir um momento fixo na semana para compartilhar uma atualização breve de status com o time ou gestor.",
                "Em uma situação real, comunicar um avanço ou bloqueio antes de ser perguntado sobre ele.",
                "Registrar o efeito de uma comunicação proativa sobre a velocidade de resposta do time ao redor.",
            ],
        },
    },
    "autoexposicao presenca posicionamento": {
        "top": {
            "impactos": "Amplia capacidade de representar o time e os resultados em espaços de decisão, fortalece a percepção de autoridade técnica e facilita a abertura de portas em negociações e apresentações estratégicas.",
            "dificuldades": "Quando pouco calibrada, a presença marcante pode concentrar atenção e crédito de forma desproporcional, reduzindo o espaço de visibilidade de outras pessoas do time.",
            "orientacao": "Potencializar a Autoexposição é relevante para transformar a naturalidade em ocupar espaço e se posicionar em uma ferramenta consistente de influência, garantindo que a presença marcante se traduza em representatividade qualificada para o time e para os resultados entregues.",
            "tendencia": "Tende a ocupar espaço com naturalidade em reuniões e apresentações, buscando visibilidade e reconhecimento pelo trabalho realizado.",
            "impacto_esperado": "O fortalecimento desta competência tende a ampliar a capacidade de representar projetos e equipes com autoridade, consolidando a presença como uma alavanca de negociação e abertura de oportunidades estratégicas.",
            "sugestoes_treinamento": [
                "Treino de liderança representativa com foco em dar voz e crédito a outras pessoas do time.",
                "Prática de comunicação estratégica para calibrar presença sem ofuscar contribuições coletivas.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Observar se a presença marcante está abrindo espaço também para outras pessoas do time ou concentrando holofotes.",
                "Dar feedback sobre o equilíbrio entre autopromoção saudável e reconhecimento coletivo do trabalho.",
            ],
            "metas_comportamentais": [
                "Compartilha crédito de entregas coletivas de forma explícita ao se posicionar em público.",
                "Usa a própria visibilidade para abrir espaço de fala para outras pessoas do time em momentos estratégicos.",
            ],
            "indicador_evolucao": "Maior percepção de presença estratégica bem calibrada, com evidências de que a visibilidade pessoal também amplia o reconhecimento do time como um todo.",
            "acoes_praticas": [
                "Em uma apresentação relevante, reservar um momento explícito para reconhecer a contribuição de outras pessoas do time.",
                "Usar a própria presença em uma reunião estratégica para defender um projeto ou ideia coletiva.",
                "Registrar o efeito da própria visibilidade sobre a percepção de autoridade do time como um todo.",
            ],
        },
        "bottom": {
            "impactos": "Seu desenvolvimento tende a ampliar a visibilidade do trabalho de alta qualidade já entregue, fortalecer a presença em espaços de decisão e aumentar a capacidade de influenciar resultados além da execução técnica.",
            "dificuldades": "Baixa recorrência pode aparecer como entregas relevantes que passam despercebidas, dificuldade de defender ideias em grupo ou tendência a deixar que outros se posicionem por ela.",
            "orientacao": "Desenvolver a Autoexposição é crucial para profissionais que realizam entregas brilhantes nos bastidores, mas enfrentam barreiras para defender suas ideias em fóruns de liderança, assegurando que seu valor técnico ganhe a visibilidade merecida no ecossistema.",
            "tendencia": "No cotidiano, tende a preferir atuar nos bastidores, entregando com qualidade silenciosa mas evitando protagonismo em espaços de maior visibilidade.",
            "impacto_esperado": "A evolução prática nesta dimensão resulta em um posicionamento mais maduro em reuniões estratégicas, maior capacidade de vender projetos internos e ganho de autoridade frente a clientes e diretores.",
            "sugestoes_treinamento": [
                "Treino de comunicação de impacto para apresentação de resultados e ideias em fóruns de liderança.",
                "Prática de posicionamento estratégico em reuniões, com foco em defender propostas com segurança.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Criar oportunidades estruturadas para que a pessoa apresente seus próprios resultados em reuniões relevantes.",
                "Reforçar publicamente contribuições técnicas de qualidade para ampliar visibilidade junto a outros stakeholders.",
            ],
            "metas_comportamentais": [
                "Apresenta os próprios resultados e ideias diretamente em reuniões estratégicas, sem depender de intermediários.",
                "Reduz a tendência de minimizar a própria contribuição em conversas com lideranças ou clientes.",
            ],
            "indicador_evolucao": "Mais episódios de apresentação direta de resultados e ideias em espaços de decisão, com evidências de reconhecimento mais imediato pelo trabalho entregue.",
            "acoes_praticas": [
                "Escolher uma entrega recente de qualidade e apresentá-la pessoalmente ao gestor ou cliente, em vez de deixar que seja relatada por terceiros.",
                "Em uma próxima reunião relevante, preparar e defender um ponto de vista próprio sobre um tema técnico.",
                "Registrar como a equipe ou liderança reagiu quando a pessoa se posicionou de forma mais visível.",
            ],
        },
    },
    "organizacao": {
        "top": {
            "impactos": "Amplia previsibilidade de entregas, fortalece a confiança do time em prazos e processos definidos, e cria uma base sólida de estrutura que pode ser replicada por outras pessoas da equipe.",
            "dificuldades": "Quando em excesso, pode gerar rigidez frente a imprevistos, resistência a mudanças de rota ou dificuldade de adaptação quando o planejamento original precisa ser revisto rapidamente.",
            "orientacao": "Potencializar a Organização é relevante para transformar a disciplina estrutural natural em uma referência de previsibilidade para o time, garantindo que processos bem estruturados sejam também replicáveis e ensináveis para outras pessoas da equipe.",
            "tendencia": "Tende a estruturar a própria rotina com antecedência, manter processos claros e buscar previsibilidade mesmo em contextos de alta demanda.",
            "impacto_esperado": "O fortalecimento desta competência tende a consolidar a pessoa como referência de processo dentro da área, ampliando a capacidade de estruturar fluxos de trabalho escaláveis e de apoiar outras pessoas na organização da própria rotina.",
            "sugestoes_treinamento": [
                "Treino de gestão de processos com foco em flexibilidade controlada frente a imprevistos.",
                "Prática de mentoria de organização para transferir métodos de planejamento a outras pessoas do time.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Observar se a estrutura criada está sendo usada de forma flexível quando o contexto muda.",
                "Estimular que a pessoa compartilhe seus métodos de organização com colegas que têm mais dificuldade nesse ponto.",
            ],
            "metas_comportamentais": [
                "Ajusta o planejamento original com agilidade quando o contexto exige mudança de rota.",
                "Compartilha estrutura e métodos de organização com outras pessoas do time.",
            ],
            "indicador_evolucao": "Maior percepção de previsibilidade de processo pela equipe, com evidências de que os métodos de organização da pessoa estão sendo replicados por outros.",
            "acoes_praticas": [
                "Documentar um processo pessoal de organização e compartilhá-lo com um colega que enfrente dificuldade similar.",
                "Em uma situação de mudança de prioridade, revisar o planejamento original de forma ágil sem resistência excessiva.",
                "Registrar como a estrutura criada ajudou o time a manter previsibilidade mesmo sob pressão.",
            ],
        },
        "bottom": {
            "impactos": "Seu desenvolvimento tende a ampliar previsibilidade de entregas, reduzir a sensação de sobrecarga constante e fortalecer a capacidade de planejar com antecedência mesmo em rotinas de alta demanda.",
            "dificuldades": "Baixa recorrência pode aparecer como prioridades que mudam com frequência, prazos que se acumulam de forma desordenada e dependência de urgência para mobilizar a execução.",
            "orientacao": "O desenvolvimento da Organização visa mitigar a dependência crônica do imediatismo e da gestão de crises, capacitando o profissional a antecipar cenários, estruturar fluxos previsíveis de trabalho e proteger sua própria carga de energia frente a mudanças de rota.",
            "tendencia": "No cotidiano, tende a funcionar bem sob pressão imediata, mas pode sofrer quando o contexto exige planejamento antecipado e estruturação de rotina.",
            "impacto_esperado": "A consolidação de rotinas organizadas gera maior previsibilidade nas entregas gerenciais, redução do retrabalho operacional sob estresse e melhor distribuição de prazos e recursos da área.",
            "sugestoes_treinamento": [
                "Treino prático de gestão do tempo e priorização estruturada de tarefas.",
                "Workshop de planejamento antecipado com ferramentas simples de organização de fluxo de trabalho.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Apoiar a definição de prioridades com antecedência, antes que a urgência se torne o único critério de execução.",
                "Reconhecer avanços em planejamento antecipado, mesmo quando pequenos, para reforçar o novo padrão.",
            ],
            "metas_comportamentais": [
                "Planeja a semana com antecedência, definindo prioridades antes que se tornem urgentes.",
                "Reduz a dependência de pressão de prazo para iniciar tarefas importantes.",
            ],
            "indicador_evolucao": "Mais evidências de planejamento antecipado, com redução de episódios de acúmulo desordenado de prazos e maior previsibilidade nas entregas da área.",
            "acoes_praticas": [
                "No início da semana, definir as três prioridades mais importantes antes que se tornem urgentes.",
                "Reservar um bloco fixo de tempo para planejamento, separado da execução de tarefas imediatas.",
                "Registrar ao final da semana onde o planejamento antecipado evitou uma situação de crise.",
            ],
        },
    },
    "controle": {
        "top": {
            "impactos": "Reduz surpresas de última hora em entregas críticas, aumenta a visibilidade sobre o andamento real dos projetos e fortalece a confiança da liderança na governança da área.",
            "dificuldades": "Quando em excesso, o acompanhamento detalhado pode ser percebido como microgerenciamento, reduzindo a autonomia percebida pelo time e gerando dependência de validação constante.",
            "orientacao": "Potencializar o Controle permite estruturar o acompanhamento de marcos críticos com precisão milimétrica, transformando a supervisão natural em governança tática e garantindo entregas previsíveis sem sufocar a autonomia das frentes executoras.",
            "tendencia": "Tende a acompanhar de perto marcos e prazos, intervindo quando identifica desvio antes que ele se torne crítico.",
            "impacto_esperado": "O refino desta força estabelece indicadores de progresso blindados, mitigando riscos operacionais de forma preventiva e elevando a maturidade processual da área.",
            "sugestoes_treinamento": [
                "Treino de governança ágil com definição de checkpoints sem microgerenciamento.",
                "Workshop de indicadores de progresso (KPIs operacionais) para acompanhamento preventivo de risco.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Observar se o nível de supervisão está calibrado ao risco real de cada entrega, não aplicado de forma uniforme.",
                "Reforçar momentos em que o controle preventivo evitou um problema maior.",
            ],
            "metas_comportamentais": [
                "Define checkpoints de acompanhamento proporcionais ao risco e à criticidade de cada entrega.",
                "Delega o acompanhamento de itens de menor risco, concentrando supervisão direta nos pontos mais críticos.",
            ],
            "indicador_evolucao": "Mais entregas com indicadores de progresso claros e menos intervenções de última hora, com evidências de que a supervisão preventiva reduziu riscos operacionais.",
            "acoes_praticas": [
                "Definir, antes do início de um projeto, quais marcos exigem acompanhamento direto e quais podem ser delegados.",
                "Criar um indicador simples de progresso para uma entrega crítica e revisá-lo em intervalos regulares.",
                "Registrar um caso em que o acompanhamento preventivo evitou um problema maior na entrega.",
            ],
        },
        "bottom": {
            "impactos": "Seu desenvolvimento tende a reduzir surpresas de última hora, aumentar a previsibilidade das entregas e fortalecer a confiança do time em processos bem acompanhados.",
            "dificuldades": "Baixa recorrência pode aparecer como desvios que só são percebidos tarde, falta de checkpoints intermediários ou dependência de que outros sinalizem problemas.",
            "orientacao": "Desenvolver o Controle é vital para reduzir a oscilação na supervisão de processos, capacitando o profissional a estabelecer checkpoints claros e métricas de sucesso, evitando que a falta de acompanhamento gere retrabalho ou desalinhamento.",
            "tendencia": "No cotidiano, tende a confiar que o processo seguirá o curso esperado sem necessidade de acompanhamento ativo, até que um problema se manifeste.",
            "impacto_esperado": "A evolução nesta dimensão traz estabilidade operacional, garantindo consistência na qualidade das entregas e maior visibilidade sobre o andamento dos projetos.",
            "sugestoes_treinamento": [
                "Treino de definição de checkpoints e métricas simples de acompanhamento de processo.",
                "Prática de revisão estruturada de progresso em intervalos regulares.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Definir junto com a pessoa marcos intermediários de revisão para projetos relevantes.",
                "Reconhecer quando o acompanhamento ativo evitou um problema, reforçando o novo hábito.",
            ],
            "metas_comportamentais": [
                "Estabelece ao menos um checkpoint intermediário em projetos de média ou alta complexidade.",
                "Revisa o andamento de tarefas delegadas antes do prazo final, não apenas na entrega.",
            ],
            "indicador_evolucao": "Mais checkpoints intermediários registrados, com redução de surpresas e retrabalho identificado apenas na entrega final.",
            "acoes_praticas": [
                "Definir um checkpoint intermediário em um projeto atual e marcar uma data para revisão.",
                "Criar uma métrica simples (ex.: percentual concluído) para acompanhar uma entrega em andamento.",
                "Registrar um caso em que a ausência de acompanhamento gerou retrabalho e o que poderia ter evitado isso.",
            ],
        },
    },
    "apego as tecnicas processos metodologia": {
        "top": {
            "impactos": "Garante consistência entre execuções, reduz variabilidade de qualidade entre diferentes pessoas do time e cria uma base metodológica replicável para escalar processos.",
            "dificuldades": "Quando em excesso, o apego ao método pode dificultar adaptações necessárias quando o contexto muda ou quando o processo padrão não serve mais ao objetivo real.",
            "orientacao": "Potencializar o Apego às Técnicas maximiza a eficiência por meio da replicação rigorosa de métodos validados, transformando a disciplina metodológica em um padrão de excelência operacional e blindagem de conformidade.",
            "tendencia": "Tende a seguir metodologias estabelecidas com rigor, buscando consistência e conformidade técnica em cada etapa do trabalho.",
            "impacto_esperado": "O uso intencional desta força zera desvios técnicos, reduz o tempo de onboarding de novos processos e consolida uma base sólida para automações estáveis.",
            "sugestoes_treinamento": [
                "Treino de gestão de processos com foco em quando flexibilizar metodologia sem perder padrão de qualidade.",
                "Workshop de documentação de processos para transformar conhecimento tácito em metodologia replicável.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Observar se a aderência ao processo está sendo usada com julgamento de quando adaptar.",
                "Estimular que a pessoa documente e compartilhe metodologias bem-sucedidas com o time.",
            ],
            "metas_comportamentais": [
                "Documenta metodologias validadas para que possam ser replicadas por outras pessoas do time.",
                "Reconhece e comunica quando um processo padrão precisa ser ajustado ao contexto específico.",
            ],
            "indicador_evolucao": "Mais processos documentados e replicáveis, com evidências de redução de variabilidade de qualidade entre diferentes execuções do time.",
            "acoes_praticas": [
                "Documentar um processo que domina bem, de forma que outra pessoa consiga replicá-lo com qualidade similar.",
                "Identificar uma situação em que o método padrão precisou de ajuste e registrar o critério usado para essa decisão.",
                "Revisar com o time um processo metodológico e propor um refinamento baseado na experiência prática.",
            ],
        },
        "bottom": {
            "impactos": "Seu desenvolvimento tende a aumentar a consistência das entregas, reduzir erros por execução informal e facilitar a transferência de conhecimento para outras pessoas do time.",
            "dificuldades": "Baixa recorrência pode aparecer como execução baseada apenas em intuição, dificuldade de documentar o próprio processo ou resultados que variam de execução para execução.",
            "orientacao": "Desenvolver o Apego às Técnicas visa mitigar a tendência à execução puramente intuitiva ou informal, estruturando a rotina sob fluxos de trabalho documentados e padrões técnicos que garantam a repetibilidade do sucesso.",
            "tendencia": "No cotidiano, tende a resolver problemas de forma intuitiva e informal, sem necessariamente seguir ou registrar um método estruturado.",
            "impacto_esperado": "A consolidação desta competência reduz erros por variabilidade comportamental e assegura que as entregas sigam os critérios de qualidade institucionais estabelecidos.",
            "sugestoes_treinamento": [
                "Treino de estruturação de processos com modelos simples de documentação.",
                "Prática guiada de padronização de rotina a partir de tarefas já dominadas intuitivamente.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Pedir que a pessoa documente um processo que já executa bem intuitivamente.",
                "Reconhecer ganhos de consistência quando um método estruturado é seguido com sucesso.",
            ],
            "metas_comportamentais": [
                "Segue um checklist ou roteiro estruturado em tarefas recorrentes de maior criticidade.",
                "Documenta ao menos um processo próprio para reduzir dependência de execução puramente intuitiva.",
            ],
            "indicador_evolucao": "Mais tarefas executadas a partir de um roteiro ou checklist estruturado, com redução de variabilidade de resultado entre execuções.",
            "acoes_praticas": [
                "Escolher uma tarefa recorrente e criar um checklist simples para guiar sua execução.",
                "Antes de repetir uma tarefa complexa, revisar como ela foi feita da última vez e o que funcionou.",
                "Pedir a um colega para revisar e validar um processo recém-documentado.",
            ],
        },
    },
    "atitude analitica": {
        "top": {
            "impactos": "Fortalece a qualidade das decisões com base em evidência, reduz a margem de erro em diagnósticos complexos e aumenta a credibilidade técnica das propostas apresentadas.",
            "dificuldades": "Quando em excesso, a análise pode se estender além do necessário, retardando decisões em contextos que pedem ação mais rápida do que análise completa.",
            "orientacao": "Potencializar a Atitude Analítica transforma dados brutos e padrões comportamentais em inteligência preditiva profunda, refinando a capacidade de diagnosticar cenários complexos antes que se convertam em problemas operacionais.",
            "tendencia": "Tende a buscar dados e padrões antes de decidir, preferindo diagnóstico estruturado a julgamento baseado apenas em intuição.",
            "impacto_esperado": "O fortalecimento desta competência eleva o embasamento técnico de propostas, blindando defesas estratégicas com evidências estruturadas e reduzindo o empirismo nas escolhas da área.",
            "sugestoes_treinamento": [
                "Treino de análise preditiva aplicada a cenários de negócio reais.",
                "Workshop de comunicação de dados para tornar diagnósticos complexos acessíveis a públicos não técnicos.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Observar se o tempo de análise está proporcional à criticidade da decisão.",
                "Estimular que a pessoa compartilhe diagnósticos analíticos como subsídio para decisões coletivas.",
            ],
            "metas_comportamentais": [
                "Define um limite de tempo para análise proporcional à urgência da decisão.",
                "Comunica diagnósticos analíticos de forma acessível para públicos não especialistas.",
            ],
            "indicador_evolucao": "Mais decisões da área embasadas em diagnóstico estruturado, com evidências de redução de erros por escolhas puramente empíricas.",
            "acoes_praticas": [
                "Diante de uma decisão relevante, estruturar um diagnóstico rápido com os três dados mais importantes antes de decidir.",
                "Definir previamente um prazo máximo de análise para não estender diagnóstico além do necessário.",
                "Apresentar um diagnóstico técnico de forma simplificada para um público não analítico.",
            ],
        },
        "bottom": {
            "impactos": "Seu desenvolvimento tende a aumentar a precisão das decisões, reduzir a influência de vieses cognitivos e fortalecer a credibilidade técnica das escolhas feitas sob pressão.",
            "dificuldades": "Baixa recorrência pode aparecer como decisões baseadas predominantemente em intuição, dificuldade de justificar escolhas com dados ou inconsistência de critério entre situações similares.",
            "orientacao": "Desenvolver a Atitude Analítica é necessário para transitar da tomada de ação reativa e puramente baseada em feeling para um modelo de diagnóstico factual, exercitando a quebra de problemas complexos em evidências quantificáveis.",
            "tendencia": "No cotidiano, tende a decidir com base em percepção imediata, sem necessariamente buscar dados estruturados que sustentem a escolha.",
            "impacto_esperado": "A evolução prática nesta frente traz maior precisão argumentativa, racionalidade sob pressão e blindagem contra vieses cognitivos na resolução de impasses.",
            "sugestoes_treinamento": [
                "Treino de raciocínio estruturado para quebra de problemas complexos em partes quantificáveis.",
                "Prática de tomada de decisão baseada em dados, com revisão de casos reais da rotina.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Pedir que a pessoa traga ao menos um dado objetivo antes de uma decisão relevante.",
                "Revisar com a pessoa o racional usado em uma decisão recente, identificando onde dados poderiam ter ajudado.",
            ],
            "metas_comportamentais": [
                "Busca ao menos um dado objetivo antes de tomar decisões de impacto moderado a alto.",
                "Estrutura o racional de uma decisão em etapas antes de comunicá-la.",
            ],
            "indicador_evolucao": "Mais decisões acompanhadas de racional estruturado e dados objetivos, com redução de escolhas justificadas apenas por intuição.",
            "acoes_praticas": [
                "Antes de uma decisão relevante, listar três dados ou evidências que sustentem a escolha.",
                "Revisar uma decisão recente tomada por intuição e identificar que dado teria ajudado a validá-la.",
                "Praticar a quebra de um problema complexo em partes menores e mais objetivas antes de buscar solução.",
            ],
        },
    },
    "detalhismo": {
        "top": {
            "impactos": "Eleva o padrão de qualidade percebido pelo cliente, reduz falhas que só seriam descobertas tarde e fortalece a reputação de precisão técnica da área.",
            "dificuldades": "Quando em excesso, o foco em minúcias pode atrasar entregas ao buscar um nível de perfeição desproporcional à criticidade real do item revisado.",
            "orientacao": "Potencializar o Detalhismo eleva o refino e o acabamento das entregas ao nível premium, utilizando o foco cirúrgico em minúcias para identificar inconsistências ocultas em contratos, relatórios e produtos que passariam despercebidas ao mercado.",
            "tendencia": "Tende a revisar entregas com atenção minuciosa, identificando inconsistências que outras pessoas frequentemente não percebem.",
            "impacto_esperado": "O refino desta força blinda a empresa contra passivos técnicos e operacionais, estabelecendo uma assinatura de precisão extrema em todos os artefatos gerados.",
            "sugestoes_treinamento": [
                "Treino de revisão técnica de alto nível com foco em itens de maior risco e visibilidade.",
                "Workshop de priorização de revisão, calibrando profundidade de detalhe à criticidade do entregável.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Observar se o nível de detalhe aplicado está proporcional ao risco e à visibilidade de cada entrega.",
                "Reconhecer publicamente quando uma revisão minuciosa evitou um problema relevante.",
            ],
            "metas_comportamentais": [
                "Calibra a profundidade de revisão à criticidade real de cada entrega.",
                "Compartilha com o time padrões de revisão que ajudam a elevar a qualidade coletiva.",
            ],
            "indicador_evolucao": "Mais inconsistências críticas identificadas antes da entrega final, com evidências de que o tempo de revisão está proporcional ao risco de cada item.",
            "acoes_praticas": [
                "Definir, antes de revisar um entregável, qual o nível de detalhe proporcional à sua criticidade.",
                "Criar um checklist de revisão para um tipo de entrega recorrente de alto risco.",
                "Registrar um caso em que a atenção a um detalhe evitou um problema relevante para o cliente ou para a empresa.",
            ],
        },
        "bottom": {
            "impactos": "Seu desenvolvimento tende a reduzir erros pontuais que geram retrabalho, aumentar a confiabilidade das entregas e elevar a percepção de qualidade técnica do trabalho realizado.",
            "dificuldades": "Baixa recorrência pode aparecer como erros pequenos que passam despercebidos, entregas que precisam de correção posterior ou dificuldade de revisar o próprio trabalho com profundidade.",
            "orientacao": "Desenvolver o Detalhismo é mandatório para equilibrar visões macro com a execução micro, capacitando o profissional a realizar revisões estruturadas e checklists de segurança para capturar erros pontuais antes da homologação final.",
            "tendencia": "No cotidiano, tende a priorizar a visão geral da entrega, podendo deixar passar inconsistências pontuais que só aparecem em revisão mais minuciosa.",
            "impacto_esperado": "Reduz drasticamente o retrabalho causado por falhas de atenção periférica e eleva o rigor estético e técnico dos entregáveis operacionais.",
            "sugestoes_treinamento": [
                "Treino de revisão estruturada com checklist de qualidade aplicado a entregas recorrentes.",
                "Prática de revisão cruzada com colegas para capturar erros que passam despercebidos na autorrevisão.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Disponibilizar um checklist padrão de revisão para entregas críticas.",
                "Reconhecer avanços quando uma revisão detalhada evitar retrabalho.",
            ],
            "metas_comportamentais": [
                "Usa um checklist estruturado antes de considerar uma entrega finalizada.",
                "Reserva um tempo específico de revisão minuciosa antes de submeter entregas críticas.",
            ],
            "indicador_evolucao": "Redução de erros pontuais identificados após a entrega, com mais evidências de revisão estruturada antes da finalização do trabalho.",
            "acoes_praticas": [
                "Criar um checklist simples de revisão para um tipo de entrega recorrente.",
                "Antes de finalizar uma entrega importante, reservar um tempo específico só para revisão de detalhes.",
                "Pedir a um colega para revisar um item crítico antes da entrega final.",
            ],
        },
    },
    "sociabilidade": {
        "top": {
            "impactos": "Fortalece pontes entre áreas, facilita a resolução colaborativa de impasses e amplia a rede de apoio disponível para destravar projetos complexos.",
            "dificuldades": "Quando em excesso, o foco em manter boas relações pode adiar conversas difíceis ou gerar dispersão de tempo em interações de baixo retorno estratégico.",
            "orientacao": "Potencializar a Sociabilidade expande de forma estratégica o ecossistema de conexões profissionais, utilizando a facilidade de trânsito relacional para abrir canais com diferentes áreas, clientes e parceiros de negócios.",
            "tendencia": "Tende a se conectar com facilidade a diferentes pessoas e áreas, construindo rede de relacionamento de forma natural e contínua.",
            "impacto_esperado": "Amplia a capilaridade da marca corporativa, acelera parcerias internas de cross-functional e facilita a diplomacia organizacional em projetos de alto impacto.",
            "sugestoes_treinamento": [
                "Treino de networking estratégico com foco em conexões de alto valor para os objetivos da área.",
                "Workshop de diplomacia organizacional para mediar interesses entre diferentes áreas.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Direcionar a energia relacional para conexões estratégicas alinhadas a objetivos prioritários da área.",
                "Reconhecer quando uma conexão construída destravou um projeto relevante.",
            ],
            "metas_comportamentais": [
                "Direciona parte do tempo relacional para conexões com potencial estratégico claro para a área.",
                "Usa a rede de relacionamento construída para destravar gargalos de outros times.",
            ],
            "indicador_evolucao": "Mais parcerias cross-functional viabilizadas através de conexões pessoais, com evidências de ganho estratégico real para a área.",
            "acoes_praticas": [
                "Mapear uma conexão estratégica ainda não explorada e iniciar uma aproximação profissional.",
                "Usar uma relação já construída para destravar um gargalo específico de outro time.",
                "Registrar um caso em que uma conexão pessoal trouxe ganho real para um projeto da área.",
            ],
        },
        "bottom": {
            "impactos": "Seu desenvolvimento tende a reduzir o isolamento relacional, ampliar o acesso a apoio informal e facilitar a colaboração espontânea com outras pessoas e áreas.",
            "dificuldades": "Baixa recorrência pode aparecer como pouca interação espontânea com colegas, dependência de canais formais para resolver questões simples ou isolamento em relação a outras áreas.",
            "orientacao": "Desenvolver a Sociabilidade visa transitar de uma postura excessivamente reservada ou focada estritamente na tarefa técnica para uma atuação mais conectada, estimulando a iniciativa de integração e o cultivo de redes de cooperação.",
            "tendencia": "No cotidiano, tende a se concentrar na tarefa técnica e interagir pouco além do estritamente necessário para a execução do trabalho.",
            "impacto_esperado": "Gera maior fluidez nas interações diárias, quebra silos de comunicação e facilita o acesso a suportes informais necessários para destravar gargalos da rotina.",
            "sugestoes_treinamento": [
                "Treino de habilidades sociais aplicadas ao ambiente corporativo, com foco em iniciativa de aproximação.",
                "Prática guiada de construção de rede de apoio informal dentro da própria organização.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Criar oportunidades estruturadas de interação com outras áreas ou colegas.",
                "Reconhecer iniciativas de aproximação espontânea, mesmo pequenas.",
            ],
            "metas_comportamentais": [
                "Inicia ao menos uma interação espontânea por semana com colegas de outras áreas.",
                "Busca apoio informal de colegas antes de recorrer apenas a canais formais.",
            ],
            "indicador_evolucao": "Mais interações espontâneas registradas com colegas e outras áreas, com evidências de acesso mais fácil a apoio informal na rotina.",
            "acoes_praticas": [
                "Iniciar uma conversa informal com um colega de outra área que ainda não conhece bem.",
                "Em uma dificuldade da rotina, buscar apoio informal de um colega antes de abrir um canal formal.",
                "Participar de um momento de integração da equipe com presença ativa.",
            ],
        },
    },
    "relacao com autoridade": {
        "top": {
            "impactos": "Fortalece a confiança da liderança, melhora a velocidade de execução de diretrizes estratégicas e consolida a pessoa como ponto de confiança entre a operação e a alta gestão.",
            "dificuldades": "Quando em excesso, pode gerar dependência excessiva de validação superior, reduzindo a iniciativa autônoma em decisões de menor porte.",
            "orientacao": "Potencializar a Relação com Autoridade consolida um alinhamento vertical estratégico e simbiótico, transformando o respeito por hierarquias e diretrizes em uma ponte para antecipar demandas da liderança e atuar como um braço de confiança executiva.",
            "tendencia": "Tende a respeitar e seguir diretrizes de liderança com disciplina, buscando alinhamento claro antes de agir em temas estratégicos.",
            "impacto_esperado": "Otimiza o tempo de resposta a orientações da diretoria, aumenta a previsibilidade na governança corporativa e assegura a execução fidedigna da visão estratégica do negócio.",
            "sugestoes_treinamento": [
                "Treino de gestão de stakeholders executivos com foco em antecipação de demandas da liderança.",
                "Workshop de autonomia decisória para equilibrar alinhamento vertical com iniciativa própria.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Delegar decisões de menor porte para estimular autonomia sem reduzir o alinhamento estratégico.",
                "Reconhecer quando a antecipação de uma demanda da liderança gerou ganho de tempo relevante.",
            ],
            "metas_comportamentais": [
                "Antecipa demandas previsíveis da liderança antes de serem formalmente solicitadas.",
                "Assume autonomia em decisões de menor porte sem depender de validação prévia em todos os casos.",
            ],
            "indicador_evolucao": "Mais demandas da liderança antecipadas com sucesso, com evidências de maior autonomia em decisões de menor impacto.",
            "acoes_praticas": [
                "Antecipar uma demanda previsível da liderança antes que ela seja formalmente solicitada.",
                "Em uma decisão de menor porte, assumir a escolha sem buscar validação prévia, comunicando depois o racional.",
                "Registrar um caso em que o alinhamento com a liderança acelerou a execução de uma diretriz estratégica.",
            ],
        },
        "bottom": {
            "impactos": "Seu desenvolvimento tende a reduzir fricções na interlocução com lideranças, aumentar a clareza de expectativas mútuas e fortalecer a confiança na relação vertical.",
            "dificuldades": "Baixa recorrência pode aparecer como desalinhamento de expectativas com a liderança, dificuldade de receber feedback ou comunicação reativa em momentos de orientação superior.",
            "orientacao": "Desenvolver a Relação com Autoridade equilibra a postura frente a lideranças, mitigando tanto a dependência excessiva de validação quanto o desalinhamento reativo, construindo uma comunicação baseada em autonomia responsável e feedback bidirecional.",
            "tendencia": "No cotidiano, pode reagir de forma defensiva a orientações de liderança ou, no extremo oposto, depender excessivamente de validação antes de qualquer ação.",
            "impacto_esperado": "Promove maturidade na interlocução vertical, permitindo posicionamentos maduros e alinhamento de expectativas sem fricções desnecessárias.",
            "sugestoes_treinamento": [
                "Treino de comunicação assertiva para interlocução com lideranças, com foco em feedback bidirecional.",
                "Prática de alinhamento de expectativas em conversas estruturadas com o gestor.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Criar momentos regulares de alinhamento de expectativas com a pessoa.",
                "Dar feedback de forma clara e específica, verificando o entendimento da pessoa sobre a orientação recebida.",
            ],
            "metas_comportamentais": [
                "Busca esclarecer expectativas com a liderança antes de assumir que está alinhado.",
                "Recebe feedback de liderança sem postura defensiva, buscando entender o racional por trás da orientação.",
            ],
            "indicador_evolucao": "Mais momentos de alinhamento de expectativas registrados, com redução de fricções ou desalinhamentos na interlocução vertical.",
            "acoes_praticas": [
                "Em uma próxima orientação recebida, parafrasear o entendimento para confirmar alinhamento com a liderança.",
                "Agendar uma conversa de alinhamento de expectativas com o gestor sobre um projeto em andamento.",
                "Registrar um caso de feedback recebido e como ele foi incorporado na prática.",
            ],
        },
    },
    "inquietacao fisica energia movimento": {
        "top": {
            "impactos": "Acelera a adaptação do time a mudanças de contexto, mantém o ritmo de trabalho elevado em períodos de transição e contagia o ambiente com energia produtiva.",
            "dificuldades": "Quando em excesso, a energia constante pode gerar dispersão entre múltiplas frentes simultâneas ou dificuldade de sustentar foco em tarefas de execução mais lenta.",
            "orientacao": "Potencializar a Inquietação Física canaliza a alta voltagem dinâmica e a resistência operacional nativa para a aceleração de transições e ciclos de mudança, atuando como o motor de ignição que tira o ecossistema da inércia.",
            "tendencia": "Tende a se manter em movimento constante, buscando novas frentes de ação e evitando períodos prolongados de rotina estática.",
            "impacto_esperado": "Aumenta a velocidade de resposta tática do setor, otimiza o dinamismo em rotinas de alta mobilidade e estabelece um ritmo dinâmico contagiante no ambiente de trabalho.",
            "sugestoes_treinamento": [
                "Treino de gestão de energia aplicada a múltiplas frentes simultâneas sem perda de foco.",
                "Prática de canalização de energia para ciclos de mudança e transição organizacional.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Direcionar a energia disponível para momentos de transição em que o dinamismo é mais necessário.",
                "Observar se a dispersão entre frentes está gerando perda de profundidade em alguma delas.",
            ],
            "metas_comportamentais": [
                "Concentra energia nas frentes de maior necessidade de dinamismo em cada momento.",
                "Reserva períodos de foco mais estático quando a tarefa exige profundidade em vez de velocidade.",
            ],
            "indicador_evolucao": "Maior aproveitamento da energia disponível em momentos de transição, com evidências de foco mantido em tarefas que exigem profundidade.",
            "acoes_praticas": [
                "Identificar a frente de trabalho que mais precisa de dinamismo nesta semana e direcionar energia para ela.",
                "Em uma tarefa que exige foco prolongado, definir blocos de tempo protegidos sem alternância entre frentes.",
                "Registrar um momento de transição em que a energia disponível acelerou a adaptação do time.",
            ],
        },
        "bottom": {
            "impactos": "Seu desenvolvimento tende a aumentar a constância de energia ao longo de tarefas longas, reduzir a sensação de inquietação e fortalecer a conclusão integral de ciclos de trabalho.",
            "dificuldades": "Baixa recorrência pode aparecer como necessidade frequente de pausa, dificuldade de sustentar energia em tarefas longas ou inquietação diante de rotinas pouco dinâmicas.",
            "orientacao": "Desenvolver a Inquietação Física foca em converter o dinamismo motor e o imediatismo em foco concentrado e perenidade de execução, mitigando a dispersão de energia ou a perda de tração antes da conclusão dos ciclos.",
            "tendencia": "No cotidiano, pode preferir alternar entre tarefas curtas e dinâmicas, evitando se aprofundar em atividades de execução mais longa e estática.",
            "impacto_esperado": "Aumenta a capacidade de foco sustentado em tarefas analíticas de longa duração e reduz a sensação de ansiedade ou pressa excessiva na rotina.",
            "sugestoes_treinamento": [
                "Treino de gestão de energia para sustentar foco em tarefas de longa duração.",
                "Prática de técnicas de concentração progressiva, com aumento gradual do tempo de foco contínuo.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Quebrar tarefas longas em blocos menores com entregas intermediárias visíveis.",
                "Reconhecer avanços quando uma tarefa longa for concluída com foco sustentado.",
            ],
            "metas_comportamentais": [
                "Sustenta foco em uma tarefa por blocos de tempo cada vez mais longos antes de alternar de atividade.",
                "Conclui ciclos de trabalho até o fim antes de iniciar uma nova frente, quando possível.",
            ],
            "indicador_evolucao": "Mais tarefas longas concluídas integralmente, com evidências de blocos de foco sustentado cada vez maiores.",
            "acoes_praticas": [
                "Definir um bloco de tempo protegido para uma tarefa longa, sem alternância para outras frentes.",
                "Antes de iniciar uma nova atividade, verificar se a anterior está realmente concluída ou apenas parcialmente avançada.",
                "Registrar a sensação de inquietação quando ela aparecer e o que ajudou a sustentar o foco mesmo assim.",
            ],
        },
    },
    "esforco no trabalho disciplina entrega": {
        "top": {
            "impactos": "Sustenta um volume elevado de entregas de qualidade, eleva o padrão de produtividade percebido pelo time e fortalece a resiliência da área frente a períodos de alta demanda.",
            "dificuldades": "Quando em excesso, a disciplina de entrega pode evoluir para sobrecarga voluntária, reduzindo tempo de recuperação e aumentando o risco de esgotamento no médio prazo.",
            "orientacao": "Potencializar o Esforço no Trabalho maximiza o foco obstinado em produtividade contínua e superação de metas, transformando a disciplina em uma vantagem competitiva sustentável para vencer mercados altamente agressivos.",
            "tendencia": "Tende a manter ritmo de produtividade elevado e constante, buscando superar metas mesmo em contextos de alta exigência.",
            "impacto_esperado": "Garante um volume constante de entregas de alta performance, eleva a barra de resiliência produtiva do time e blinda o setor contra oscilações de mercado.",
            "sugestoes_treinamento": [
                "Treino de gestão de energia produtiva com foco em sustentabilidade de longo prazo.",
                "Workshop de definição de metas desafiadoras com proteção contra sobrecarga voluntária.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Observar sinais de sobrecarga voluntária antes que afetem a saúde produtiva da pessoa.",
                "Reconhecer a disciplina de entrega como referência, equilibrando com incentivo a pausas de recuperação.",
            ],
            "metas_comportamentais": [
                "Mantém volume elevado de entregas sem abrir mão de pausas de recuperação programadas.",
                "Compartilha com o time práticas de disciplina produtiva que sustentam alta performance sem esgotamento.",
            ],
            "indicador_evolucao": "Volume de entregas mantido em alta performance, com evidências de pausas de recuperação programadas e ausência de sinais de esgotamento.",
            "acoes_praticas": [
                "Definir uma meta desafiadora para a semana e também programar um momento de recuperação após o esforço intenso.",
                "Compartilhar com um colega uma prática pessoal de disciplina que sustenta alta produtividade.",
                "Registrar sinais de cansaço acumulado e ajustar o ritmo antes que se tornem esgotamento.",
            ],
        },
        "bottom": {
            "impactos": "Seu desenvolvimento tende a estabilizar o volume de entregas ao longo do tempo, reduzir picos de sobrecarga no fim de ciclos e aumentar a previsibilidade da capacidade produtiva.",
            "dificuldades": "Baixa recorrência pode aparecer como esforço concentrado apenas perto do prazo final, picos erráticos de produtividade ou acúmulo de demandas que geram pressão evitável.",
            "orientacao": "Desenvolver o Esforço no Trabalho atua na estruturação da disciplina de entrega sustentável, substituindo picos erráticos de esforço por uma metodologia de constância prática, protegendo os prazos contra procrastinação ou sobrecargas táticas.",
            "tendencia": "No cotidiano, tende a distribuir o esforço de forma irregular, com picos de produtividade concentrados próximos aos prazos finais.",
            "impacto_esperado": "Estabiliza o volume produtivo mensal, promove previsibilidade de capacidade de entrega e mitiga gargalos causados por acúmulo de demandas no fim de ciclos.",
            "sugestoes_treinamento": [
                "Treino de gestão de constância produtiva, com técnicas de distribuição de esforço ao longo do ciclo.",
                "Prática de planejamento de entregas parciais para evitar concentração de esforço no fim do prazo.",
            ],
            "sugestoes_acompanhamento_gestor": [
                "Definir entregas parciais intermediárias para distribuir o esforço ao longo do ciclo.",
                "Reconhecer avanços quando o esforço for distribuído de forma mais constante, não apenas no fim do prazo.",
            ],
            "metas_comportamentais": [
                "Distribui o esforço de forma mais constante ao longo do ciclo, evitando concentração apenas no fim do prazo.",
                "Entrega partes intermediárias do trabalho antes da data final, reduzindo acúmulo de demanda.",
            ],
            "indicador_evolucao": "Volume produtivo mais distribuído ao longo do ciclo, com redução de picos de sobrecarga próximos aos prazos finais.",
            "acoes_praticas": [
                "Dividir uma entrega de prazo longo em partes menores com datas intermediárias de progresso.",
                "Reservar um bloco fixo de tempo produtivo no início do ciclo, em vez de concentrar esforço apenas no fim.",
                "Registrar o que mudou na qualidade da entrega ao distribuir o esforço de forma mais constante.",
            ],
        },
    },
}

PDI_TITLE_BY_NAME: Dict[str, Dict[str, str]] = {
    "lideranca": {
        "top": "Liderança e direcionamento",
        "bottom": "Posicionamento e condução de contexto",
    },
    "decisao de risco": {
        "top": "Gestão de risco e autonomia decisória",
        "bottom": "Tomada de decisão com risco calculado",
    },
    "obstinacao persistencia firmeza": {
        "top": "Resiliência e persistência com flexibilidade",
        "bottom": "Constância e sustentação sob pressão",
    },
    "ambicao resultados carreira": {
        "top": "Mobilização para resultado e crescimento",
        "bottom": "Tração para meta e progresso",
    },
    "confrontacao pessoal assertividade conflito": {
        "top": "Assertividade madura em conversas difíceis",
        "bottom": "Assertividade e enfrentamento funcional de divergências",
    },
    "repressao emocional autocontrole expressao": {
        "top": "Estabilidade emocional com presença funcional",
        "bottom": "Autogestão emocional e estabilidade de resposta",
    },
    "envolvimento afetivo empatia vinculo": {
        "top": "Empatia prática e qualidade de vínculo",
        "bottom": "Empatia prática e qualidade de vínculo profissional",
    },
    "gosto pela inovacao": {
        "top": "Abertura para inovação com critério",
        "bottom": "Adaptabilidade e inovação com segurança",
    },
}


def _copy_key(letter: str, name: str) -> str:
    normalized_name = _normalize_key(name)
    normalized_letter = _normalize_key(letter)

    if normalized_letter in COMPETENCY_COPY:
        return normalized_letter

    if normalized_name in COMPETENCY_COPY:
        return normalized_name

    return normalized_name


def _fallback_copy(*, name: str, area_label: str, eixo: str) -> Dict[str, Any]:
    name = str(name or "").strip() or "esta competência"
    area_label = str(area_label or "").strip() or "avaliada"

    if eixo == "POTENCIALIZAR":
        return {
            "impactos": f"Quando bem utilizada, {name} tende a ampliar consistência de desempenho e gerar valor mais claro dentro da área {area_label}.",
            "dificuldades": f"Quando pouco calibrada, {name} pode perder precisão de uso e gerar excesso, rigidez ou distorção de contexto.",
            "orientacao": f"Observar {name} em situações reais da rotina, verificando qualidade de uso, dosagem e impacto funcional no ambiente.",
            "tendencia": f"No cotidiano, tende a influenciar de forma perceptível a maneira como a pessoa atua dentro da área {area_label}.",
            "impacto_esperado": f"O fortalecimento de {name} tende a aumentar uso intencional, consistência prática e melhor aproveitamento desta força no contexto profissional.",
            "sugestoes_treinamento": [
                f"Prática guiada de {name} em situações reais da área {area_label}.",
                f"Feedback estruturado sobre dosagem, consistência e impacto do uso de {name}.",
            ],
            "sugestoes_acompanhamento_gestor": [
                f"Observar evidências concretas de uso mais consciente de {name}.",
                f"Dar feedback sobre onde {name} agregou resultado e onde ainda pede calibragem.",
            ],
            "metas_comportamentais": [
                f"Usa {name} de forma mais consciente e intencional em situações relevantes da rotina.",
                f"Mantém maior consistência prática desta competência ao longo das semanas.",
            ],
            "indicador_evolucao": f"Mais evidências observáveis de uso calibrado, consciente e funcional de {name} no contexto de trabalho.",
            "acoes_praticas": [
                f"Escolher uma situação real da semana para aplicar {name} de forma mais intencional.",
                f"Definir previamente o que caracterizará um uso funcional desta competência no contexto.",
                f"Registrar o efeito concreto do uso de {name} sobre resultado, relação ou andamento da rotina.",
            ],
        }

    return {
        "impactos": f"O desenvolvimento de {name} tende a ampliar qualidade de resposta, adaptação prática e efetividade funcional dentro da área {area_label}.",
        "dificuldades": f"Baixa recorrência desta competência pode limitar a forma como a pessoa responde às exigências reais do contexto.",
        "orientacao": f"Trabalhar {name} em episódios reais da rotina, com observação prática, feedback específico e revisão objetiva de progresso.",
        "tendencia": f"No dia a dia, a menor presença de {name} pode aparecer em situações que exigem resposta mais madura dentro da área {area_label}.",
        "impacto_esperado": f"O desenvolvimento de {name} tende a aumentar consistência comportamental e melhorar a forma como a pessoa responde às demandas concretas do trabalho.",
        "sugestoes_treinamento": [
            f"Treino aplicado de {name} em situações reais da área {area_label}.",
            f"Role play com feedback objetivo sobre resposta comportamental mais funcional.",
        ],
        "sugestoes_acompanhamento_gestor": [
            f"Acompanhar episódios concretos em que {name} faz diferença no resultado ou na relação.",
            f"Dar feedback específico sobre evolução prática desta competência ao longo do tempo.",
        ],
        "metas_comportamentais": [
            f"Demonstra evolução prática em {name} em situações reais da rotina.",
            f"Reduz automatismos e amplia escolha mais funcional do comportamento esperado.",
        ],
        "indicador_evolucao": f"Aumento de evidências práticas de {name}, confirmadas por observação do gestor e exemplos concretos da rotina.",
        "acoes_praticas": [
            f"Escolher uma situação recorrente da rotina em que {name} precisa aparecer com mais clareza.",
            f"Definir uma resposta comportamental simples e treinável para esse contexto.",
            f"Registrar ao final da semana em que momento {name} apareceu melhor do que no padrão anterior.",
        ],
    }


def _build_card(
    *,
    item: Dict[str, Any],
    eixo: str,
    paineis_area: List[Dict[str, Any]],
) -> Dict[str, Any]:
    key = _copy_key(item["letter"], item["name"])
    copy_block = COMPETENCY_COPY.get(key, {}).get("top" if eixo == "POTENCIALIZAR" else "bottom")
    if copy_block is None:
        copy_block = _fallback_copy(
            name=item["name"],
            area_label=item["area_label"],
            eixo=eixo,
        )

    base_text = item["text"] or copy_block["tendencia"]

    return {
        "letter": item["letter"],
        "name": item["name"],
        "band": _normalize_band_label(item["band"] or "Nível não disponível"),
        "score": item["score"],
        "area": _resolve_area_label(item["letter"], paineis_area) or item["area_label"],
        "base_text": base_text,
        "impactos": copy_block["impactos"],
        "dificuldades": copy_block["dificuldades"],
        "orientacao": copy_block["orientacao"],
        "tendencia": copy_block["tendencia"],
        "pdi_copy": copy_block,
    }


def _build_pdi_title(*, letter: str, name: str, eixo: str) -> str:
    name = str(name or "").strip() or "esta competência"
    key = _copy_key(letter, name)
    title_map = PDI_TITLE_BY_NAME.get(key, {})
    title = title_map.get("top" if eixo == "POTENCIALIZAR" else "bottom")
    if isinstance(title, str) and title.strip():
        return title.strip()

    if eixo == "POTENCIALIZAR":
        return f"Potencialização de {name}"
    return f"Desenvolvimento de {name}"


def _build_pdi_item(card: Dict[str, Any], eixo: str) -> Dict[str, Any]:
    copy_block = card["pdi_copy"]

    if eixo == "POTENCIALIZAR":
        desc_texto = "representa uma força já presente no perfil e pode ser usada com mais consciência e consistência."
    else:
        desc_texto = "aparece como prioridade objetiva de desenvolvimento e tende a influenciar a qualidade da resposta profissional."

    texto_final = (
        f"{_build_pdi_title(letter=card['letter'], name=card['name'], eixo=eixo)} é relevante porque "
        f"{desc_texto} {card['base_text']}"
    )

    return {
        "titulo": _build_pdi_title(letter=card["letter"], name=card["name"], eixo=eixo),
        "eixo": eixo,
        "area": card["area"],
        "competencia_letra": card["letter"],
        "competencia_nome": card["name"],
        "porque_relevante": texto_final,
        "impacto_esperado": copy_block["impacto_esperado"],
        "acoes_praticas": list(copy_block["acoes_praticas"]),
        "sugestoes_treinamento": list(copy_block["sugestoes_treinamento"]),
        "sugestoes_acompanhamento_gestor": list(copy_block["sugestoes_acompanhamento_gestor"]),
        "metas_comportamentais": list(copy_block["metas_comportamentais"]),
        "prazo_recomendado": (
            "4 a 8 semanas de prática observável com revisão quinzenal da evolução."
            if eixo == "POTENCIALIZAR"
            else "6 a 10 semanas de prática acompanhada com checkpoints quinzenais e revisão de evidências."
        ),
        "indicador_evolucao": copy_block["indicador_evolucao"],
    }


def _assert_unique_field(items: List[Dict[str, Any]], field: str) -> None:
    seen: Dict[str, str] = {}

    for item in items:
        title = str(item.get("titulo") or "").strip()

        raw = item.get(field)
        if isinstance(raw, list):
            value = " || ".join(str(x).strip() for x in raw if str(x).strip())
        else:
            value = str(raw or "").strip()

        normalized = _normalize_key(value)
        if not normalized:
            continue

        if normalized in seen:
            raise ValueError(
                f"Premium PDI uniqueness error: field '{field}' repeated between '{seen[normalized]}' and '{title}'."
            )
        seen[normalized] = title


def _assert_pdi_uniqueness(items: List[Dict[str, Any]]) -> None:
    fields = [
        "impacto_esperado",
        "metas_comportamentais",
        "indicador_evolucao",
        "sugestoes_treinamento",
        "sugestoes_acompanhamento_gestor",
    ]
    for field in fields:
        _assert_unique_field(items, field)


def _build_fallback_summary(
    *,
    participant_payload: Dict[str, Any],
    attempt_payload: Dict[str, Any],
    ranking: Dict[str, Any],
    dimension_index: Dict[str, Dict[str, Any]],
) -> str:
    nome = str(participant_payload.get("nome") or "").strip() or "O participante"
    cargo = str(attempt_payload.get("cargo") or "").strip()

    top3_names = [
        dimension_index[letter]["name"]
        for letter in ranking.get("top3", [])
        if letter in dimension_index
    ][:3]

    bottom3_names = [
        dimension_index[letter]["name"]
        for letter in ranking.get("bottom3", [])
        if letter in dimension_index
    ][:3]

    opening = nome
    if cargo:
        opening += f", no contexto do cargo de {cargo}"

    top_txt = ", ".join(top3_names) if top3_names else "competências de maior recorrência"
    bottom_txt = ", ".join(bottom3_names) if bottom3_names else "competências que pedem desenvolvimento"

    return (
        f"{opening}, apresenta maior destaque em {top_txt}, indicando tendências mais presentes na forma de atuar, decidir e sustentar entregas. "
        f"Os principais pontos de atenção concentram-se em {bottom_txt}, aspectos que merecem acompanhamento estruturado para ampliar consistência, adaptação e efetividade no contexto profissional."
    )


def _build_technical_opinion(
    *,
    top3_cards: List[Dict[str, Any]],
    bottom3_cards: List[Dict[str, Any]],
) -> str:
    top_names = ", ".join(card["name"] for card in top3_cards[:3]) or "competências de maior sustentação"
    bottom_names = ", ".join(card["name"] for card in bottom3_cards[:3]) or "competências prioritárias para desenvolvimento"

    return (
        f"Do ponto de vista técnico, o perfil apresenta maior sustentação em {top_names}, indicando base funcional para desempenho, posicionamento e resposta prática ao contexto profissional. "
        f"As prioridades de desenvolvimento concentram-se em {bottom_names}, pontos que merecem acompanhamento estruturado para ampliar consistência comportamental, qualidade de adaptação e efetividade nas relações e entregas."
    )


async def build_premium_report_context(
    session: AsyncSession,
    *,
    attempt: Attempt,
    computed_result: ComputedResult,
) -> Dict[str, Any]:
    scores = computed_result.scores or {}
    bands = computed_result.bands or {}
    interpretations = computed_result.interpretations or {}
    ranking = _ranking_from_computed(computed_result)

    participant_payload = await _build_participant_payload(session, attempt)
    attempt_payload = _build_attempt_payload(attempt)
    dims = _load_dimensions_map()

    raw_sintese = _build_sintese_executiva_payload(
        participant_payload=participant_payload,
        ranking=ranking,
        interpretations=interpretations,
        dims=dims,
    )

    dimension_index = _build_dimension_index(
        scores=scores,
        bands=bands,
        interpretations=interpretations,
        dims=dims,
    )

    paineis_area = _build_paineis_area_payload(
        scores=scores,
        bands=bands,
        interpretations=interpretations,
        dims=dims,
    )

    top5_cards: List[Dict[str, Any]] = []
    for letter in ranking.get("top5", []):
        item = dimension_index.get(letter)
        if item:
            top5_cards.append(_build_card(item=item, eixo="POTENCIALIZAR", paineis_area=paineis_area))

    bottom3_cards: List[Dict[str, Any]] = []
    for letter in ranking.get("bottom3", []):
        item = dimension_index.get(letter)
        if item:
            bottom3_cards.append(_build_card(item=item, eixo="DESENVOLVER", paineis_area=paineis_area))

    pdi_competencias: List[Dict[str, Any]] = []
    for card in top5_cards[:3]:
        pdi_competencias.append(_build_pdi_item(card, "POTENCIALIZAR"))
    for card in bottom3_cards[:3]:
        pdi_competencias.append(_build_pdi_item(card, "DESENVOLVER"))

    _assert_pdi_uniqueness(pdi_competencias)

    executive_summary_text = _extract_executive_summary_text(raw_sintese)
    executive_summary_text = _sanitize_executive_summary_text(executive_summary_text)
    if not executive_summary_text:
        executive_summary_text = _build_fallback_summary(
            participant_payload=participant_payload,
            attempt_payload=attempt_payload,
            ranking=ranking,
            dimension_index=dimension_index,
        )

    technical_opinion = _build_technical_opinion(
        top3_cards=top5_cards[:3],
        bottom3_cards=bottom3_cards[:3],
    )

    return {
        "token": "",
        "participant": participant_payload,
        "attempt": attempt_payload,
        "scores": scores,
        "bands": bands,
        "ranking": ranking,
        "interpretations": interpretations,
        "executive_summary_text": executive_summary_text,
        "assessment_datetime_display": _format_assessment_datetime(
            attempt_payload.get("data_conclusao") or attempt_payload.get("data_inicio")
        ),
        "brand_logo_path": "static/img/official_logo.png",
        "paineis_area": paineis_area,
        "top5_cards": top5_cards,
        "bottom3_cards": bottom3_cards,
        "pdi_competencias": pdi_competencias,
        "technical_opinion": technical_opinion,
        "report_template": "reports/report_premium.html",
    }
