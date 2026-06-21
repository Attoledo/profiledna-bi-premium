from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.ai_analyst.retrieval import retrieve_relevant_chunks


DEFAULT_TOP_K = 5


@dataclass(frozen=True)
class SearchIssue:
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchMatch:
    index_entry_id: str
    document_id: str
    chunk_id: str
    title: str
    theme: str
    file_path: str
    chunk_index: int
    score: int
    matched_terms: list[str]
    preview: str
    text_length: int
    token_estimate: int
    fingerprint: str


@dataclass(frozen=True)
class SearchReport:
    is_valid: bool
    query: str
    normalized_query: str
    allowed_themes: list[str]
    entries_received: int
    entries_after_theme_filter: int
    matches_returned: int
    matches: list[SearchMatch] = field(default_factory=list)
    errors: list[SearchIssue] = field(default_factory=list)
    warnings: list[SearchIssue] = field(default_factory=list)


@dataclass(frozen=True)
class DanaSearchQuery:
    """
    Contrato compatível com o context_builder.

    Wrapper fino e estável sobre os parâmetros já suportados por search_docsia.
    """

    query: str
    top_k: int = DEFAULT_TOP_K
    allowed_themes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DanaSearchScopeResult:
    """
    Resultado compatível e auditável para consumo pelos demais módulos da DANA.
    """

    is_valid: bool
    query: str
    top_k: int
    allowed_themes: list[str]
    matches_returned: int
    matches: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).strip()


def _normalize_theme(value: Any) -> str:
    return _normalize_text(value).upper()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _filter_entries_by_theme(
    index_entries: list[dict[str, Any]],
    allowed_themes: list[str] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not allowed_themes:
        return index_entries, []

    normalized_allowed: list[str] = []
    seen: set[str] = set()

    for item in allowed_themes:
        normalized = _normalize_theme(item)
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        normalized_allowed.append(normalized)

    if not normalized_allowed:
        return index_entries, []

    filtered = [
        entry
        for entry in index_entries
        if _normalize_theme(entry.get("theme")) in normalized_allowed
    ]
    return filtered, normalized_allowed


def search_docsia(
    query: str,
    index_entries: list[dict[str, Any]],
    *,
    top_k: int = DEFAULT_TOP_K,
    allowed_themes: list[str] | None = None,
) -> SearchReport:
    errors: list[SearchIssue] = []
    warnings: list[SearchIssue] = []

    normalized_query = _normalize_text(query)
    entries_received = len(index_entries)

    if top_k <= 0:
        warnings.append(
            SearchIssue(
                code="top_k_adjusted",
                message="top_k inválido; valor ajustado para 1.",
                context={"received_top_k": top_k, "adjusted_top_k": 1},
            )
        )
        top_k = 1

    filtered_entries, normalized_allowed_themes = _filter_entries_by_theme(
        index_entries=index_entries,
        allowed_themes=allowed_themes,
    )

    if normalized_allowed_themes and not filtered_entries:
        warnings.append(
            SearchIssue(
                code="theme_filter_no_match",
                message="Nenhuma entrada do índice corresponde aos temas solicitados.",
                context={"allowed_themes": normalized_allowed_themes},
            )
        )

    retrieval_report = retrieve_relevant_chunks(
        query=normalized_query,
        index_entries=filtered_entries,
        top_k=top_k,
        allowed_themes=normalized_allowed_themes or None,
    )

    for item in retrieval_report.errors:
        errors.append(
            SearchIssue(
                code=item.code,
                message=item.message,
                context=item.context,
            )
        )

    for item in retrieval_report.warnings:
        warnings.append(
            SearchIssue(
                code=item.code,
                message=item.message,
                context=item.context,
            )
        )

    matches = [
        SearchMatch(
            index_entry_id=item.index_entry_id,
            document_id=item.document_id,
            chunk_id=item.chunk_id,
            title=item.title,
            theme=item.theme,
            file_path=item.file_path,
            chunk_index=item.chunk_index,
            score=item.score,
            matched_terms=item.matched_terms,
            preview=item.preview,
            text_length=item.text_length,
            token_estimate=item.token_estimate,
            fingerprint=item.fingerprint,
        )
        for item in retrieval_report.matches
    ]

    return SearchReport(
        is_valid=len(errors) == 0,
        query=query,
        normalized_query=normalized_query,
        allowed_themes=normalized_allowed_themes,
        entries_received=entries_received,
        entries_after_theme_filter=len(filtered_entries),
        matches_returned=len(matches),
        matches=matches,
        errors=errors,
        warnings=warnings,
    )


def search_scope(
    search_query: DanaSearchQuery,
    index_entries: list[dict[str, Any]],
) -> DanaSearchScopeResult:
    """
    Função de compatibilidade para o context_builder.

    Mantém a superfície pública esperada pelo módulo legado e delega a busca
    real para search_docsia, sem alterar a semântica já validada.
    """
    report = search_docsia(
        query=search_query.query,
        index_entries=index_entries,
        top_k=search_query.top_k,
        allowed_themes=search_query.allowed_themes,
    )

    return DanaSearchScopeResult(
        is_valid=report.is_valid,
        query=report.query,
        top_k=search_query.top_k,
        allowed_themes=report.allowed_themes,
        matches_returned=report.matches_returned,
        matches=[asdict(item) for item in report.matches],
        errors=[asdict(item) for item in report.errors],
        warnings=[asdict(item) for item in report.warnings],
    )


def _report_to_jsonable(report: SearchReport) -> dict[str, Any]:
    return {
        "is_valid": report.is_valid,
        "query": report.query,
        "normalized_query": report.normalized_query,
        "allowed_themes": report.allowed_themes,
        "entries_received": report.entries_received,
        "entries_after_theme_filter": report.entries_after_theme_filter,
        "matches_returned": report.matches_returned,
        "matches": [asdict(item) for item in report.matches],
        "errors": [asdict(item) for item in report.errors],
        "warnings": [asdict(item) for item in report.warnings],
    }


def main() -> None:
    report = search_docsia(
        query="",
        index_entries=[],
    )
    print(
        json.dumps(
            _report_to_jsonable(report),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
