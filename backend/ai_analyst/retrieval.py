from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any


DEFAULT_TOP_K = 5
MIN_QUERY_TERM_LENGTH = 2
MAX_PREVIEW_LENGTH = 240


@dataclass(frozen=True)
class RetrievalIssue:
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievedChunk:
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
class RetrievalReport:
    is_valid: bool
    query: str
    query_terms: list[str]
    entries_received: int
    entries_scored: int
    entries_returned: int
    matches: list[RetrievedChunk] = field(default_factory=list)
    errors: list[RetrievalIssue] = field(default_factory=list)
    warnings: list[RetrievalIssue] = field(default_factory=list)


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _tokenize_query(query: str) -> list[str]:
    normalized = _normalize_text(query).lower()
    if not normalized:
        return []

    raw_terms = re.findall(r"[a-zà-ÿ0-9_]+", normalized, flags=re.IGNORECASE)
    unique_terms: list[str] = []
    seen: set[str] = set()

    for term in raw_terms:
        term = term.strip().lower()
        if len(term) < MIN_QUERY_TERM_LENGTH:
            continue
        if term in seen:
            continue
        seen.add(term)
        unique_terms.append(term)

    return unique_terms


def _build_preview(text: str, matched_terms: list[str]) -> str:
    normalized_text = _normalize_text(text)
    if not normalized_text:
        return ""

    if not matched_terms:
        return normalized_text[:MAX_PREVIEW_LENGTH].strip()

    lower_text = normalized_text.lower()
    first_pos = -1

    for term in matched_terms:
        pos = lower_text.find(term.lower())
        if pos >= 0 and (first_pos == -1 or pos < first_pos):
            first_pos = pos

    if first_pos == -1:
        return normalized_text[:MAX_PREVIEW_LENGTH].strip()

    start = max(first_pos - 50, 0)
    end = min(start + MAX_PREVIEW_LENGTH, len(normalized_text))
    preview = normalized_text[start:end].strip()

    if start > 0:
        preview = "..." + preview
    if end < len(normalized_text):
        preview = preview + "..."

    return preview


def _score_index_entry(
    entry: dict[str, Any],
    query_terms: list[str],
) -> tuple[int, list[str]]:
    normalized_text = _normalize_text(entry.get("normalized_text")).lower()
    title = _normalize_text(entry.get("title")).lower()
    theme = _normalize_text(entry.get("theme")).lower()

    if not normalized_text:
        return 0, []

    score = 0
    matched_terms: list[str] = []

    for term in query_terms:
        term_score = 0

        text_count = normalized_text.count(term)
        title_count = title.count(term)
        theme_count = theme.count(term)

        if text_count > 0:
            term_score += text_count * 3
        if title_count > 0:
            term_score += title_count * 5
        if theme_count > 0:
            term_score += theme_count * 4

        if term_score > 0:
            matched_terms.append(term)
            score += term_score

    return score, matched_terms


def retrieve_relevant_chunks(
    query: str,
    index_entries: list[dict[str, Any]],
    *,
    top_k: int = DEFAULT_TOP_K,
    allowed_themes: list[str] | None = None,
) -> RetrievalReport:
    errors: list[RetrievalIssue] = []
    warnings: list[RetrievalIssue] = []
    matches: list[RetrievedChunk] = []

    normalized_query = _normalize_text(query)
    query_terms = _tokenize_query(normalized_query)

    if not normalized_query:
        warnings.append(
            RetrievalIssue(
                code="empty_query",
                message="Consulta vazia; nenhum chunk foi recuperado.",
                context={},
            )
        )
        return RetrievalReport(
            is_valid=True,
            query=normalized_query,
            query_terms=[],
            entries_received=len(index_entries),
            entries_scored=0,
            entries_returned=0,
            matches=[],
            errors=[],
            warnings=warnings,
        )

    if top_k <= 0:
        warnings.append(
            RetrievalIssue(
                code="top_k_adjusted",
                message="top_k inválido; valor ajustado para 1.",
                context={"received_top_k": top_k, "adjusted_top_k": 1},
            )
        )
        top_k = 1

    normalized_allowed_themes: set[str] | None = None
    if allowed_themes:
        normalized_allowed_themes = {
            _normalize_text(item).upper()
            for item in allowed_themes
            if _normalize_text(item)
        }

    scored_entries: list[tuple[int, dict[str, Any], list[str]]] = []

    for entry in index_entries:
        theme = _normalize_text(entry.get("theme")).upper()
        if normalized_allowed_themes is not None and theme not in normalized_allowed_themes:
            continue

        index_entry_id = _normalize_text(entry.get("index_entry_id"))
        chunk_id = _normalize_text(entry.get("chunk_id"))
        document_id = _normalize_text(entry.get("document_id"))
        normalized_text = _normalize_text(entry.get("normalized_text"))

        if not index_entry_id or not chunk_id or not document_id or not normalized_text:
            errors.append(
                RetrievalIssue(
                    code="invalid_index_entry",
                    message="Entrada do índice inválida para recuperação.",
                    context={
                        "index_entry_id": index_entry_id,
                        "chunk_id": chunk_id,
                        "document_id": document_id,
                    },
                )
            )
            continue

        score, matched_terms = _score_index_entry(entry, query_terms)
        if score <= 0:
            continue

        scored_entries.append((score, entry, matched_terms))

    scored_entries.sort(
        key=lambda item: (
            -item[0],
            _safe_int(item[1].get("chunk_index"), default=0),
            _normalize_text(item[1].get("index_entry_id")),
        )
    )

    top_entries = scored_entries[:top_k]

    for score, entry, matched_terms in top_entries:
        normalized_text = _normalize_text(entry.get("normalized_text"))
        matches.append(
            RetrievedChunk(
                index_entry_id=_normalize_text(entry.get("index_entry_id")),
                document_id=_normalize_text(entry.get("document_id")),
                chunk_id=_normalize_text(entry.get("chunk_id")),
                title=_normalize_text(entry.get("title")),
                theme=_normalize_text(entry.get("theme")),
                file_path=_normalize_text(entry.get("file_path")),
                chunk_index=_safe_int(entry.get("chunk_index"), default=0),
                score=score,
                matched_terms=matched_terms,
                preview=_build_preview(normalized_text, matched_terms),
                text_length=_safe_int(entry.get("text_length"), default=len(normalized_text)),
                token_estimate=_safe_int(entry.get("token_estimate"), default=0),
                fingerprint=_normalize_text(entry.get("fingerprint")),
            )
        )

    return RetrievalReport(
        is_valid=len(errors) == 0,
        query=normalized_query,
        query_terms=query_terms,
        entries_received=len(index_entries),
        entries_scored=len(scored_entries),
        entries_returned=len(matches),
        matches=matches,
        errors=errors,
        warnings=warnings,
    )


def _report_to_jsonable(report: RetrievalReport) -> dict[str, Any]:
    return {
        "is_valid": report.is_valid,
        "query": report.query,
        "query_terms": report.query_terms,
        "entries_received": report.entries_received,
        "entries_scored": report.entries_scored,
        "entries_returned": report.entries_returned,
        "matches": [asdict(item) for item in report.matches],
        "errors": [asdict(item) for item in report.errors],
        "warnings": [asdict(item) for item in report.warnings],
    }


def main() -> None:
    report = retrieve_relevant_chunks(
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
