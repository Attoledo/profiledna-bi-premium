from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.ai_analyst.models import AIInteractionLog
from backend.ai_analyst.prompts import PROMPT_VERSION, build_system_prompt
from backend.ai_analyst.services import DanaPreparedInput, DanaQuestionInput, prepare_question_input
from backend.ai_analyst.tools import (
    TOOL_DEFINITIONS,
    TOOL_GET_ATTEMPT_CONTEXT,
    TOOL_GET_BI_CLIENTE,
    TOOL_GET_BI_OVERVIEW,
    TOOL_GET_REPORT_CONTEXT,
    execute_tool_calls,
)
from backend.config import get_settings


class DanaAgentError(RuntimeError):
    """
    Erro base do agente DANA.
    """


class DanaAgentDisabledError(DanaAgentError):
    """
    Lançado quando AI_ENABLED=false.
    """


class DanaAgentConfigurationError(DanaAgentError):
    """
    Lançado quando falta configuração essencial para o agente.
    """


@dataclass(frozen=True)
class DanaAgentResult:
    """
    Resultado final entregue pela camada de agent orchestration.
    """

    response_text: str
    question_sanitized: str
    tools_called: dict[str, Any]
    prompt_version: str
    model_used: str
    tokens_input: int
    tokens_output: int
    cost_usd: Decimal
    duration_ms: int
    query_mode: str
    analysis_scope: dict[str, Any]
    filters_active: dict[str, Any]


class DanaAgent:
    """
    Orquestrador principal da DANA.

    Responsabilidades:
    - preparar a pergunta com sanitização e escopo;
    - montar o system prompt;
    - pré-carregar contexto factual do sistema;
    - incorporar memória curta da conversa quando disponível;
    - chamar o modelo;
    - executar tools autorizadas adicionais;
    - consolidar a resposta final;
    - gravar auditoria em AIInteractionLog.
    """

    def __init__(
        self,
        *,
        client: Any | None = None,
        model: str | None = None,
        max_tool_rounds: int = 5,
    ) -> None:
        self.settings = get_settings()
        self.model = model or self.settings.OPENAI_MODEL
        self.max_tool_rounds = max_tool_rounds
        self._client = client

    def _ensure_enabled(self) -> None:
        if not bool(self.settings.AI_ENABLED):
            raise DanaAgentDisabledError("Módulo DANA desabilitado (AI_ENABLED=false).")

    def _ensure_configured(self) -> None:
        if not self.model or not str(self.model).strip():
            raise DanaAgentConfigurationError("OPENAI_MODEL não configurado.")
        if not self.settings.OPENAI_API_KEY:
            raise DanaAgentConfigurationError("OPENAI_API_KEY não configurada.")

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        self._ensure_configured()

        try:
            from openai import AsyncOpenAI
        except Exception as exc:
            raise DanaAgentConfigurationError(
                "Biblioteca OpenAI não disponível no runtime."
            ) from exc

        self._client = AsyncOpenAI(api_key=self.settings.OPENAI_API_KEY)
        return self._client

    @staticmethod
    def _to_uuid(value: str | None) -> uuid.UUID | None:
        if not value:
            return None
        try:
            return uuid.UUID(str(value))
        except Exception:
            return None

    @staticmethod
    def _extract_output_text(response: Any) -> str:
        """
        Extrai o texto final da resposta da API da OpenAI de forma resiliente.
        """
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        texts: list[str] = []
        output = getattr(response, "output", None) or []

        for item in output:
            item_type = getattr(item, "type", None)
            if item_type == "message":
                content = getattr(item, "content", None) or []
                for part in content:
                    if getattr(part, "type", None) in {"output_text", "text"}:
                        text_value = getattr(part, "text", None)
                        if isinstance(text_value, str) and text_value.strip():
                            texts.append(text_value.strip())

        joined = "\n\n".join(t for t in texts if t.strip()).strip()
        return joined or "[SEM RESPOSTA TEXTUAL DO MODELO]"

    @staticmethod
    def _extract_tool_calls(response: Any) -> list[dict[str, Any]]:
        """
        Extrai function calls da Responses API em formato estável para o dispatcher local.
        """
        calls: list[dict[str, Any]] = []
        output = getattr(response, "output", None) or []

        for item in output:
            if getattr(item, "type", None) != "function_call":
                continue

            arguments_raw = getattr(item, "arguments", None)
            arguments: dict[str, Any] = {}

            if isinstance(arguments_raw, str) and arguments_raw.strip():
                try:
                    parsed = json.loads(arguments_raw)
                    if isinstance(parsed, dict):
                        arguments = parsed
                except Exception:
                    arguments = {}
            elif isinstance(arguments_raw, dict):
                arguments = dict(arguments_raw)

            calls.append(
                {
                    "call_id": getattr(item, "call_id", None),
                    "name": getattr(item, "name", None),
                    "arguments": arguments,
                }
            )

        return calls

    @staticmethod
    def _extract_usage(response: Any) -> tuple[int, int]:
        """
        Extrai tokens de entrada/saída de forma resiliente.
        """
        usage = getattr(response, "usage", None)
        if not usage:
            return 0, 0

        input_tokens = (
            getattr(usage, "input_tokens", None)
            or getattr(usage, "prompt_tokens", None)
            or 0
        )
        output_tokens = (
            getattr(usage, "output_tokens", None)
            or getattr(usage, "completion_tokens", None)
            or 0
        )

        try:
            return int(input_tokens), int(output_tokens)
        except Exception:
            return 0, 0

    @staticmethod
    def _estimate_cost_usd(tokens_input: int, tokens_output: int) -> Decimal:
        """
        Estimativa conservadora de custo.
        """
        if tokens_input <= 0 and tokens_output <= 0:
            return Decimal("0.000000")

        estimated = (
            Decimal(tokens_input) * Decimal("0.0000005")
            + Decimal(tokens_output) * Decimal("0.0000015")
        )
        return estimated.quantize(Decimal("0.000001"))

    @staticmethod
    def _extract_bi_preload_filters(prepared: DanaPreparedInput) -> dict[str, Any]:
        filters = dict(prepared.scope.filters_active or {})
        return {
            "rodada_id": filters.get("rodada_id"),
            "setor_id": filters.get("setor_id"),
            "cargo": filters.get("cargo"),
            "tipo_aplicacao": filters.get("tipo_aplicacao"),
            "status": filters.get("status"),
            "only_completed": bool(filters.get("only_completed")),
        }

    @staticmethod
    def _build_preloaded_tool_calls(prepared: DanaPreparedInput) -> list[dict[str, Any]]:
        calls: list[dict[str, Any]] = []

        if prepared.scope.attempt_id:
            calls.append(
                {
                    "name": TOOL_GET_ATTEMPT_CONTEXT,
                    "arguments": {
                        "attempt_id": prepared.scope.attempt_id,
                    },
                }
            )
            calls.append(
                {
                    "name": TOOL_GET_REPORT_CONTEXT,
                    "arguments": {
                        "attempt_id": prepared.scope.attempt_id,
                    },
                }
            )

        calls.append(
            {
                "name": TOOL_GET_BI_CLIENTE,
                "arguments": DanaAgent._extract_bi_preload_filters(prepared),
            }
        )

        return calls

    @staticmethod
    def _format_bi_as_text_from_executed_calls(
        executed_calls: list[dict[str, Any]],
    ) -> str | None:
        """
        Renders raw BI payload from preloaded tool calls as explicit readable prose
        so the model receives sector names, counts and percentages as direct text —
        not only buried inside a JSON blob.
        """
        lines: list[str] = []

        for call in executed_calls:
            name = str(call.get("name") or "")
            if name not in (TOOL_GET_BI_CLIENTE, TOOL_GET_BI_OVERVIEW):
                continue

            result = dict(call.get("result") or {})
            if result.get("error"):
                continue

            payload = dict(result.get("payload") or {})

            setor_dist = list(payload.get("setor_distribution") or [])
            if setor_dist:
                total = sum(int(r.get("count", 0)) for r in setor_dist)
                lines.append("Distribuição real por setor (dados do banco de dados):")
                for r in sorted(setor_dist, key=lambda x: -int(x.get("count", 0))):
                    setor_name = (
                        r.get("setor") or r.get("label") or r.get("name") or "Sem Setor"
                    )
                    count = int(r.get("count", 0))
                    pct = round(count / total * 100, 1) if total else 0.0
                    lines.append(f"  Setor {setor_name}: {count} avaliações ({pct}%)")

            top5 = list(payload.get("top5_frequency") or [])[:5]
            if top5:
                lines.append("Top 5 forças mais frequentes no recorte atual:")
                for i, r in enumerate(top5, 1):
                    dim_label = (
                        r.get("dimension_label")
                        or r.get("label")
                        or r.get("dimension")
                        or "?"
                    )
                    pct = round(float(r.get("pct") or 0), 1)
                    count_r = int(r.get("count") or 0)
                    lines.append(f"  {i}. {dim_label}: {count_r} registros ({pct}%)")

            overview_cards = list(payload.get("overview_cards") or [])[:4]
            if overview_cards:
                lines.append("Indicadores gerais do recorte:")
                for card in overview_cards:
                    key = card.get("key") or card.get("label") or "?"
                    val = card.get("value")
                    lines.append(f"  {key}: {val}")

            break  # use only the first BI result found

        return "\n".join(lines) if lines else None

    @staticmethod
    def _summarize_bi_ranking_rows(
        rows: list[dict[str, Any]] | None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        summarized: list[dict[str, Any]] = []
        for row in list(rows or [])[:limit]:
            summarized.append(
                {
                    "dimension": row.get("dimension"),
                    "label": row.get("label"),
                    "area": row.get("area"),
                    "count": row.get("count"),
                    "pct": row.get("pct"),
                    "pct_label": row.get("pct_label"),
                }
            )
        return summarized

    @staticmethod
    def _summarize_bi_payload_for_model(result: dict[str, Any]) -> dict[str, Any]:
        payload = dict(result.get("payload") or {})

        return {
            "tool": result.get("tool"),
            "cliente_id": result.get("cliente_id"),
            "filters": dict(result.get("filters") or {}),
            "payload": {
                "meta": dict(payload.get("meta") or {}),
                "overview_cards": list(payload.get("overview_cards") or [])[:3],
                "radar_area": {
                    "has_data": bool(dict(payload.get("radar_area") or {}).get("has_data")),
                    "details": list(dict(payload.get("radar_area") or {}).get("details") or [])[:3],
                },
                "setor_distribution": list(payload.get("setor_distribution") or []),
                "top5_frequency": DanaAgent._summarize_bi_ranking_rows(
                    payload.get("top5_frequency"),
                    limit=5,
                ),
                "bottom3_frequency": DanaAgent._summarize_bi_ranking_rows(
                    payload.get("bottom3_frequency"),
                    limit=5,
                ),
            },
        }

    @staticmethod
    def _summarize_preloaded_call_for_model(executed_call: dict[str, Any]) -> dict[str, Any]:
        name = str(executed_call.get("name") or "")
        arguments = dict(executed_call.get("arguments") or {})
        result = dict(executed_call.get("result") or {})

        if name == TOOL_GET_REPORT_CONTEXT:
            report_snapshot = dict(result.get("report_snapshot") or {})
            pontos_atencao_oficiais = list(
                report_snapshot.get("pontos_atencao_oficiais")
                or report_snapshot.get("bottom3_titulos")
                or report_snapshot.get("bottom3")
                or []
            )[:3]

            result = {
                "tool": result.get("tool"),
                "cliente_id": result.get("cliente_id"),
                "attempt_id": result.get("attempt_id"),
                "report_snapshot": {
                    "has_report_snapshot": bool(report_snapshot.get("has_report_snapshot")),
                    "generated_at": report_snapshot.get("generated_at"),
                    "identificacao_resumida": dict(report_snapshot.get("identificacao_resumida") or {}),
                    "sintese_executiva": report_snapshot.get("sintese_executiva"),
                    "top5_titulos": list(
                        report_snapshot.get("top5_titulos")
                        or report_snapshot.get("top5")
                        or []
                    )[:5],
                    "pontos_atencao_oficiais": pontos_atencao_oficiais,
                    "usar_exatamente_pontos_atencao_oficiais": pontos_atencao_oficiais,
                    "competencias_pdi": list(report_snapshot.get("competencias_pdi") or [])[:6],
                    "nota_tecnica_resumida": report_snapshot.get("nota_tecnica_resumida"),
                },
            }

        if name == TOOL_GET_BI_CLIENTE:
            result = DanaAgent._summarize_bi_payload_for_model(result)

        if name == TOOL_GET_BI_OVERVIEW:
            result = DanaAgent._summarize_bi_payload_for_model(result)

        return {
            "name": name,
            "arguments": arguments,
            "result": result,
        }

    @staticmethod
    def _build_preloaded_context_message(executed_calls: list[dict[str, Any]]) -> str | None:
        if not executed_calls:
            return None

        summarized_calls = [
            DanaAgent._summarize_preloaded_call_for_model(call)
            for call in executed_calls
        ]

        context_json = json.dumps(
            {"preloaded_factual_context": summarized_calls},
            ensure_ascii=False,
            default=str,
        )

        bi_readable = DanaAgent._format_bi_as_text_from_executed_calls(executed_calls)
        bi_section = (
            "\n\nDADOS REAIS DE BI EXTRAÍDOS DO BANCO DE DADOS"
            " — USE ESTES NÚMEROS DIRETAMENTE NAS SUAS RESPOSTAS:\n"
            + bi_readable
            + "\n"
        ) if bi_readable else ""

        return (
            "CONTEXTO FACTUAL PRÉ-CARREGADO DO SISTEMA\n"
            "- O participante selecionado é o eixo principal da resposta.\n"
            "- Em modo participante, use o resultado oficial individual como prioridade máxima.\n"
            "- Use resultado consolidado e relatório estruturado como base factual primária.\n"
            "- Considere como forças principais do participante os destaques oficiais do relatório e do resultado consolidado.\n"
            "- Considere como pontos de atenção principais do participante os pontos de atenção oficiais do relatório final, quando estes forem os pontos oficiais presentes no contexto.\n"
            "- Quando o contexto factual trouxer nomes oficiais de destaques, pontos de atenção ou competências, reproduza esses nomes de forma fiel e prioritária.\n"
            "- Não reagrupe pontos oficiais em macrotemas genéricos, categorias interpretativas amplas ou rótulos inventados.\n"
            "- Não substitua os pontos de atenção oficiais por temas laterais, medianos ou apenas contextuais.\n"
            "- Ao recomendar ações ao gestor, conecte cada ação explicitamente ao ponto de atenção correspondente do participante.\n"
            "- Cada recomendação prática ao gestor deve trazer, sempre que possível: o que fazer, o que observar e qual sinal concreto de evolução acompanhar.\n"
            "- Não usar recomendações genéricas de coaching, RH amplo ou desenvolvimento abstrato sem vínculo claro com o resultado oficial do participante.\n"
            "- Use o BI do cliente apenas como apoio secundário ao gestor.\n"
            "- Não force comparação com o cliente. Só cite convergência, divergência ou atenção contextual quando houver evidência clara no BI.\n"
            "- Se houver tensão entre contexto do cliente e resultado individual oficial, prevalece sempre o resultado individual oficial.\n"
            "- Priorize utilidade prática para o gestor: condução, feedback, acompanhamento, riscos e desenvolvimento.\n"
            "- Não peça novamente IDs, attempt_id ou contexto já disponíveis neste bloco.\n"
            "- Responda obrigatoriamente com os blocos: Síntese executiva; Pontos de atenção; Recomendações práticas ao gestor; Contexto do cliente; Bases consideradas\n"
            f"{bi_section}"
            f"{context_json}"
        )

    @staticmethod
    def _build_conversation_history_message(
        conversation_history: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    ) -> str | None:
        """
        Constrói contexto curto de continuidade conversacional.

        Regras:
        - não substitui a base factual oficial do sistema;
        - serve apenas para continuidade, evitando repetição e reabertura artificial;
        - usa histórico curto já sanitizado.
        """
        items = list(conversation_history or [])
        if not items:
            return None

        normalized_items: list[dict[str, Any]] = []

        for item in items:
            if not isinstance(item, dict):
                continue

            question_sanitized = str(item.get("question_sanitized") or "").strip()
            response_text = str(item.get("response_text") or "").strip()
            created_at = item.get("created_at")

            if not question_sanitized and not response_text:
                continue

            normalized_items.append(
                {
                    "question_sanitized": question_sanitized,
                    "response_text": response_text,
                    "created_at": created_at,
                }
            )

        if not normalized_items:
            return None

        history_json = json.dumps(
            {"conversation_history": normalized_items},
            ensure_ascii=False,
            default=str,
        )

        return (
            "MEMÓRIA CURTA DA CONVERSA COM O GESTOR\n"
            "- Este bloco existe apenas para continuidade conversacional.\n"
            "- Use-o para evitar repetir abertura, reexplicar o mesmo resumo já dado ou reiniciar a conversa como se fosse o primeiro turno.\n"
            "- Se a nova pergunta for continuação direta da anterior, responda de forma mais fluida, assumindo que o gestor já leu a análise imediatamente anterior.\n"
            "- Não trate o histórico da conversa como fonte factual superior ao resultado oficial do sistema.\n"
            "- Quando houver qualquer tensão entre a conversa anterior e a base oficial do sistema, prevalece a base oficial do sistema.\n"
            "- Use o histórico para continuidade, aprofundamento e encadeamento da explicação.\n"
            "- Evite repetir apresentação da DANA, preâmbulos longos e blocos redundantes quando o histórico já mostrar interação em andamento.\n"
            f"{history_json}"
        )

    @staticmethod
    def _build_initial_input(
        prepared: DanaPreparedInput,
        system_prompt: str,
        preloaded_context_message: str | None = None,
        conversation_history_message: str | None = None,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            }
        ]

        if preloaded_context_message:
            items.append(
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": preloaded_context_message}],
                }
            )

        if conversation_history_message:
            items.append(
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": conversation_history_message}],
                }
            )

        items.append(
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prepared.question_sanitized}],
            }
        )

        return items

    @staticmethod
    def _build_tool_outputs_payload(
        executed_calls: list[dict[str, Any]],
        original_tool_calls: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Converte resultados locais em payload aceito pela Responses API.
        """
        by_name_and_args: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        for executed in executed_calls:
            by_name_and_args.append(
                (
                    str(executed.get("name") or ""),
                    dict(executed.get("arguments") or {}),
                    dict(executed.get("result") or {}),
                )
            )

        outputs: list[dict[str, Any]] = []

        for call in original_tool_calls:
            call_name = str(call.get("name") or "")
            call_args = dict(call.get("arguments") or {})
            call_id = call.get("call_id")

            matched_result: dict[str, Any] = {}
            for name, args, result in by_name_and_args:
                if name == call_name and args == call_args:
                    matched_result = result
                    break

            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(matched_result, ensure_ascii=False, default=str),
                }
            )

        return outputs

    async def _create_initial_response(
        self,
        *,
        prepared: DanaPreparedInput,
        system_prompt: str,
        preloaded_context_message: str | None,
        conversation_history_message: str | None,
    ) -> Any:
        client = self._get_client()
        return await client.responses.create(
            model=self.model,
            input=self._build_initial_input(
                prepared,
                system_prompt,
                preloaded_context_message,
                conversation_history_message,
            ),
            tools=TOOL_DEFINITIONS,
        )

    async def _continue_with_tool_outputs(
        self,
        *,
        previous_response_id: str,
        tool_outputs: list[dict[str, Any]],
    ) -> Any:
        client = self._get_client()
        return await client.responses.create(
            model=self.model,
            previous_response_id=previous_response_id,
            input=tool_outputs,
            tools=TOOL_DEFINITIONS,
        )

    async def _persist_log(
        self,
        *,
        db: AsyncSession,
        prepared: DanaPreparedInput,
        response_text: str,
        tools_called: dict[str, Any],
        tokens_input: int,
        tokens_output: int,
        cost_usd: Decimal,
        duration_ms: int,
        model_used: str,
    ) -> None:
        admin_user_uuid = self._to_uuid(prepared.scope.admin_user_id)
        cliente_uuid = self._to_uuid(prepared.scope.cliente_id)
        attempt_uuid = self._to_uuid(prepared.scope.attempt_id)

        if admin_user_uuid is None:
            raise DanaAgentError("admin_user_id inválido para auditoria da DANA.")
        if cliente_uuid is None:
            raise DanaAgentError("cliente_id inválido para auditoria da DANA.")

        bi_used = any(
            item.get("name") in {"get_bi_overview", "get_bi_cliente", "compare_bi_snapshots"}
            for item in tools_called.get("calls", [])
        )

        report_used = any(
            item.get("name") in {"get_report_context", "get_attempt_context"}
            for item in tools_called.get("calls", [])
        )

        report_sections_used: list[str] = []
        if report_used:
            report_sections_used = [
                "Identificação",
                "Síntese Executiva",
                "Painel de Resultados por Área",
                "Pontos Fortes (Top 5)",
                "Oportunidades de Desenvolvimento (Bottom 3)",
                "Competências-Chave para PDI",
                "Recomendações para Gestor / RH",
                "Dimensões Detalhadas (20)",
                "Nota Técnica",
            ]

        log = AIInteractionLog(
            admin_user_id=admin_user_uuid,
            cliente_id=cliente_uuid,
            attempt_id=attempt_uuid,
            question_sanitized=prepared.question_sanitized,
            tools_called=tools_called,
            response_text=response_text,
            prompt_version=PROMPT_VERSION,
            model_used=model_used,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            analysis_scope=prepared.analysis_scope_payload,
            filters_active=prepared.scope.filters_active,
            report_sections_used=report_sections_used,
            docsia_documents_used=[],
            docsia_chunks_used=[],
            bi_context_used={"used": bi_used},
            query_mode=prepared.scope.query_mode,
        )

        db.add(log)
        await db.flush()

    async def run(
        self,
        payload: DanaQuestionInput,
        db: AsyncSession,
    ) -> DanaAgentResult:
        """
        Executa o fluxo principal da DANA.
        """
        self._ensure_enabled()
        self._ensure_configured()

        started_at = time.perf_counter()

        prepared = prepare_question_input(payload)

        effective_prompt_context = replace(
            prepared.prompt_context,
            has_docsia_context=False,
        )
        system_prompt = build_system_prompt(effective_prompt_context)

        preloaded_tool_calls = self._build_preloaded_tool_calls(prepared)
        preloaded_executed_calls: list[dict[str, Any]] = []

        if preloaded_tool_calls:
            preloaded_executed_calls = await execute_tool_calls(
                db,
                cliente_id=prepared.scope.cliente_id,
                tool_calls=preloaded_tool_calls,
            )

        preloaded_context_message = self._build_preloaded_context_message(
            preloaded_executed_calls
        )
        conversation_history_message = self._build_conversation_history_message(
            prepared.conversation_history
        )

        response = await self._create_initial_response(
            prepared=prepared,
            system_prompt=system_prompt,
            preloaded_context_message=preloaded_context_message,
            conversation_history_message=conversation_history_message,
        )

        all_executed_calls: list[dict[str, Any]] = list(preloaded_executed_calls)
        total_input_tokens = 0
        total_output_tokens = 0

        input_tokens, output_tokens = self._extract_usage(response)
        total_input_tokens += input_tokens
        total_output_tokens += output_tokens

        round_count = 0
        while round_count < self.max_tool_rounds:
            tool_calls = self._extract_tool_calls(response)
            if not tool_calls:
                break

            local_calls = [
                {
                    "name": item["name"],
                    "arguments": item["arguments"],
                }
                for item in tool_calls
            ]

            executed = await execute_tool_calls(
                db,
                cliente_id=prepared.scope.cliente_id,
                tool_calls=local_calls,
            )
            all_executed_calls.extend(executed)

            tool_outputs = self._build_tool_outputs_payload(
                executed_calls=executed,
                original_tool_calls=tool_calls,
            )

            response = await self._continue_with_tool_outputs(
                previous_response_id=str(getattr(response, "id")),
                tool_outputs=tool_outputs,
            )

            input_tokens, output_tokens = self._extract_usage(response)
            total_input_tokens += input_tokens
            total_output_tokens += output_tokens

            round_count += 1

        response_text = self._extract_output_text(response)
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        cost_usd = self._estimate_cost_usd(total_input_tokens, total_output_tokens)

        conversation_items_count = len(list(prepared.conversation_history or []))

        tools_called_payload = {
            "calls": all_executed_calls,
            "tool_rounds": round_count,
            "docsia_runtime_used": False,
            "knowledge_mode": "official_system_only",
            "conversation_memory": {
                "used": bool(conversation_history_message),
                "items_count": conversation_items_count,
            },
        }

        await self._persist_log(
            db=db,
            prepared=prepared,
            response_text=response_text,
            tools_called=tools_called_payload,
            tokens_input=total_input_tokens,
            tokens_output=total_output_tokens,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            model_used=self.model,
        )

        return DanaAgentResult(
            response_text=response_text,
            question_sanitized=prepared.question_sanitized,
            tools_called=tools_called_payload,
            prompt_version=PROMPT_VERSION,
            model_used=self.model,
            tokens_input=total_input_tokens,
            tokens_output=total_output_tokens,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            query_mode=prepared.scope.query_mode,
            analysis_scope=prepared.analysis_scope_payload,
            filters_active=prepared.scope.filters_active,
        )
