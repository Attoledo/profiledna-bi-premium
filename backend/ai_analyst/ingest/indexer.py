from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any


DEFAULT_INDEX_VERSION = "1.0.0"
DEFAULT_INDEX_STATUS = "indexed"


@dataclass(frozen=True)
class IndexIssue:
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IndexEntry:
    index_entry_id: str
    index_status: str
    embedding_id: str
    chunk_id: str
    document_id: str
    title: str
    theme: str
    file_path: str
    chunk_index: int
    normalized_text: str
    text_length: int
    token_estimate: int
    fingerprint: str
    embedding_provider: str
    embedding_model: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IndexManifest:
    index_version: str
    index_hash: str
    total_documents: int
    total_chunks: int
    total_entries: int
    themes: list[str]
    embedding_provider: str
    embedding_model: str


@dataclass(frozen=True)
class IndexBuildReport:
    is_valid: bool
    embeddings_received: int
    indexed_documents: int
    indexed_chunks: int
    index_entries_created: int
    index_manifest: IndexManifest | None = None
    index_entries: list[IndexEntry] = field(default_factory=list)
    errors: list[IndexIssue] = field(default_factory=list)
    warnings: list[IndexIssue] = field(default_factory=list)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _validate_embedding_payload(embedding: dict[str, Any]) -> list[IndexIssue]:
    issues: list[IndexIssue] = []

    required_fields = [
        "embedding_id",
        "chunk_id",
        "document_id",
        "theme",
        "normalized_text",
        "fingerprint",
    ]

    for field_name in required_fields:
        if not _normalize_text(embedding.get(field_name)):
            issues.append(
                IndexIssue(
                    code=f"missing_{field_name}",
                    message=f"Embedding sem {field_name} não pode ser indexado.",
                    context={
                        "embedding_id": embedding.get("embedding_id"),
                        "chunk_id": embedding.get("chunk_id"),
                        "document_id": embedding.get("document_id"),
                    },
                )
            )

    return issues


def _build_index_hash(entries: list[IndexEntry]) -> str:
    raw_items: list[str] = []
    for entry in sorted(entries, key=lambda item: item.index_entry_id):
        raw_items.append(
            "||".join(
                [
                    entry.index_entry_id,
                    entry.embedding_id,
                    entry.chunk_id,
                    entry.document_id,
                    entry.theme,
                    entry.file_path,
                    str(entry.chunk_index),
                    entry.fingerprint,
                    entry.embedding_provider,
                    entry.embedding_model,
                ]
            )
        )
    raw = "\n".join(raw_items)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_index_from_embeddings(
    embeddings: list[dict[str, Any]],
    *,
    index_version: str = DEFAULT_INDEX_VERSION,
) -> IndexBuildReport:
    errors: list[IndexIssue] = []
    warnings: list[IndexIssue] = []
    index_entries: list[IndexEntry] = []

    for embedding in embeddings:
        embedding_errors = _validate_embedding_payload(embedding)
        if embedding_errors:
            errors.extend(embedding_errors)
            continue

        embedding_id = _normalize_text(embedding.get("embedding_id"))
        chunk_id = _normalize_text(embedding.get("chunk_id"))
        document_id = _normalize_text(embedding.get("document_id"))
        title = _normalize_text(embedding.get("title"))
        theme = _normalize_text(embedding.get("theme"))
        file_path = _normalize_text(embedding.get("file_path"))
        chunk_index = _safe_int(embedding.get("chunk_index"), default=0)
        normalized_text = _normalize_text(embedding.get("normalized_text"))
        text_length = _safe_int(embedding.get("text_length"), default=len(normalized_text))
        token_estimate = _safe_int(embedding.get("token_estimate"), default=0)
        fingerprint = _normalize_text(embedding.get("fingerprint"))
        embedding_provider = _normalize_text(embedding.get("embedding_provider"))
        embedding_model = _normalize_text(embedding.get("embedding_model"))
        metadata = embedding.get("metadata") or {}

        if not isinstance(metadata, dict):
            warnings.append(
                IndexIssue(
                    code="metadata_not_dict",
                    message="metadata do embedding não veio como dict; valor foi normalizado para dict vazio.",
                    context={"embedding_id": embedding_id},
                )
            )
            metadata = {}

        index_entry_id = f"{chunk_id}::index"

        index_entries.append(
            IndexEntry(
                index_entry_id=index_entry_id,
                index_status=DEFAULT_INDEX_STATUS,
                embedding_id=embedding_id,
                chunk_id=chunk_id,
                document_id=document_id,
                title=title,
                theme=theme,
                file_path=file_path,
                chunk_index=chunk_index,
                normalized_text=normalized_text,
                text_length=text_length,
                token_estimate=token_estimate,
                fingerprint=fingerprint,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
                metadata={
                    **metadata,
                    "index_entry_id": index_entry_id,
                    "index_status": DEFAULT_INDEX_STATUS,
                },
            )
        )

    indexed_documents = len({item.document_id for item in index_entries})
    indexed_chunks = len({item.chunk_id for item in index_entries})
    themes = sorted({item.theme for item in index_entries})

    index_manifest: IndexManifest | None = None
    if index_entries:
        provider_values = sorted({item.embedding_provider for item in index_entries if item.embedding_provider})
        model_values = sorted({item.embedding_model for item in index_entries if item.embedding_model})

        if len(provider_values) > 1:
            warnings.append(
                IndexIssue(
                    code="multiple_embedding_providers",
                    message="Foram encontrados múltiplos providers no mesmo lote de indexação.",
                    context={"providers": provider_values},
                )
            )

        if len(model_values) > 1:
            warnings.append(
                IndexIssue(
                    code="multiple_embedding_models",
                    message="Foram encontrados múltiplos modelos no mesmo lote de indexação.",
                    context={"models": model_values},
                )
            )

        index_manifest = IndexManifest(
            index_version=index_version,
            index_hash=_build_index_hash(index_entries),
            total_documents=indexed_documents,
            total_chunks=indexed_chunks,
            total_entries=len(index_entries),
            themes=themes,
            embedding_provider=provider_values[0] if provider_values else "",
            embedding_model=model_values[0] if model_values else "",
        )

    return IndexBuildReport(
        is_valid=len(errors) == 0,
        embeddings_received=len(embeddings),
        indexed_documents=indexed_documents,
        indexed_chunks=indexed_chunks,
        index_entries_created=len(index_entries),
        index_manifest=index_manifest,
        index_entries=index_entries,
        errors=errors,
        warnings=warnings,
    )


def _report_to_jsonable(report: IndexBuildReport) -> dict[str, Any]:
    return {
        "is_valid": report.is_valid,
        "embeddings_received": report.embeddings_received,
        "indexed_documents": report.indexed_documents,
        "indexed_chunks": report.indexed_chunks,
        "index_entries_created": report.index_entries_created,
        "index_manifest": asdict(report.index_manifest) if report.index_manifest else None,
        "index_entries": [asdict(item) for item in report.index_entries],
        "errors": [asdict(item) for item in report.errors],
        "warnings": [asdict(item) for item in report.warnings],
    }


def main() -> None:
    report = build_index_from_embeddings([])
    print(
        json.dumps(
            _report_to_jsonable(report),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
