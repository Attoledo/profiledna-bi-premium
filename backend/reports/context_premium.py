from __future__ import annotations

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
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""

    replacements = [
        ("D (Liderança)", "Liderança"),
        ("F (Decisão de Risco)", "Decisão de Risco"),
        ("K (Obstinação (Persistência/Firmeza))", "Obstinação (Persistência/Firmeza)"),
        ("N (Repressão Emocional (Autocontrole/Expressão))", "Repressão Emocional (Autocontrole/Expressão)"),
        ("D — Liderança", "Liderança"),
        ("F — Decisão de Risco", "Decisão de Risco"),
        ("K — Obstinação (Persistência/Firmeza)", "Obstinação (Persistência/Firmeza)"),
        ("N — Repressão Emocional (Autocontrole/Expressão)", "Repressão Emocional (Autocontrole/Expressão)"),
        (" D ", " "),
        (" F ", " "),
        (" K ", " "),
        (" N ", " "),
    ]

    for old, new in replacements:
        cleaned = cleaned.replace(old, new)

    forbidden_inline = [
        "D (",
        "F (",
        "K (",
        "N (",
        "D —",
        "F —",
        "K —",
        "N —",
    ]
    for token in forbidden_inline:
        cleaned = cleaned.replace(token, "")

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
    return {
        "titulo": _build_pdi_title(letter=card["letter"], name=card["name"], eixo=eixo),
        "eixo": eixo,
        "area": card["area"],
        "competencia_letra": card["letter"],
        "competencia_nome": card["name"],
        "porque_relevante": (
            f"{_build_pdi_title(letter=card['letter'], name=card['name'], eixo=eixo)} é relevante porque "
            f"{'representa uma força já presente no perfil e pode ser usada com mais consciência e consistência.'
            if eixo == 'POTENCIALIZAR'
            else 'aparece como prioridade objetiva de desenvolvimento e tende a influenciar a qualidade da resposta profissional.'} "
            f"{card['base_text']}"
        ),
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
        "brand_logo_path": "backend/static/img/dna-logo.png",
        "paineis_area": paineis_area,
        "top5_cards": top5_cards,
        "bottom3_cards": bottom3_cards,
        "pdi_competencias": pdi_competencias,
        "technical_opinion": technical_opinion,
        "report_template": "reports/report_premium.html",
    }
