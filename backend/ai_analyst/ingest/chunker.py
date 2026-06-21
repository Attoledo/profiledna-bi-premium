from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any


DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 150


@dataclass(frozen=True)
class ChunkerMessage:
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChunkRecord:
    chunk_id: str
    document_id: str
    title: str
    theme: str
    file_path: str
    chunk_index: int
    chunk_char_start: int
    chunk_char_end: int
    text: str
    text_length: int
    status: str | None = None
    version: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ChunkingReport:
    is_valid: bool
    documents_received: int
    documents_chunked: int
    chunks_created: int
    chunks: list[ChunkRecord] = field(default_factory=list)
    errors: list[ChunkerMessage] = field(default_factory=list)
    warnings: list[ChunkerMessage] = field(default_factory=list)


def _normalize_text(value: str) -> str:
    text = str(value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _safe_dict(item: Any) -> dict[str, Any]:
    if item is None:
        return {}
    if isinstance(item, dict):
        return dict(item)
    if is_dataclass(item):
        return asdict(item)
    if hasattr(item, "__dict__"):
        return {
            key: value
            for key, value in vars(item).items()
            if not key.startswith("_")
        }
    fields = [
        "document_id",
        "title",
        "theme",
        "file_path",
        "content",
        "status",
        "version",
        "tags",
    ]
    data: dict[str, Any] = {}
    for field_name in fields:
        if hasattr(item, field_name):
            data[field_name] = getattr(item, field_name)
    return data


def _build_chunk_id(document_id: str, chunk_index: int) -> str:
    safe_document_id = str(document_id or "").strip() or "unknown_document"
    return f"{safe_document_id}::chunk::{chunk_index:04d}"


def _split_text_with_overlap(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[tuple[int, int, str]]:
    if not text:
        return []

    chunks: list[tuple[int, int, str]] = []
    text_length = len(text)
    start = 0

    while start < text_length:
        end = min(start + chunk_size, text_length)

        if end < text_length:
            window = text[start:end]
            split_candidates = [
                window.rfind("\n\n"),
                window.rfind("\n"),
                window.rfind(". "),
                window.rfind("; "),
                window.rfind(", "),
                window.rfind(" "),
            ]
            best_split = max(split_candidates)
            if best_split >= int(chunk_size * 0.55):
                end = start + best_split + 1

        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append((start, end, chunk_text))

        if end >= text_length:
            break

        next_start = max(end - chunk_overlap, start + 1)
        if next_start <= start:
            break
        start = next_start

    return chunks


def chunk_extracted_documents(
    extracted_documents: list[Any],
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> ChunkingReport:
    errors: list[ChunkerMessage] = []
    warnings: list[ChunkerMessage] = []
    chunks: list[ChunkRecord] = []

    if chunk_size <= 0:
        errors.append(
            ChunkerMessage(
                code="invalid_chunk_size",
                message="chunk_size deve ser maior que zero.",
                context={"chunk_size": chunk_size},
            )
        )

    if chunk_overlap < 0:
        errors.append(
            ChunkerMessage(
                code="invalid_chunk_overlap",
                message="chunk_overlap não pode ser negativo.",
                context={"chunk_overlap": chunk_overlap},
            )
        )

    if chunk_overlap >= chunk_size and chunk_size > 0:
        errors.append(
            ChunkerMessage(
                code="invalid_chunk_overlap_range",
                message="chunk_overlap deve ser menor que chunk_size.",
                context={
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                },
            )
        )

    if errors:
        return ChunkingReport(
            is_valid=False,
            documents_received=len(extracted_documents or []),
            documents_chunked=0,
            chunks_created=0,
            chunks=[],
            errors=errors,
            warnings=warnings,
        )

    documents_received = len(extracted_documents or [])
    documents_chunked = 0

    for raw_item in extracted_documents or []:
        item = _safe_dict(raw_item)

        document_id = str(item.get("document_id") or "").strip()
        title = str(item.get("title") or "").strip()
        theme = str(item.get("theme") or "").strip()
        file_path = str(item.get("file_path") or "").strip()
        status = item.get("status")
        version = item.get("version")
        tags_raw = item.get("tags") or []
        content = _normalize_text(str(item.get("content") or ""))

        if not document_id:
            warnings.append(
                ChunkerMessage(
                    code="document_missing_document_id",
                    message="Documento ignorado por ausência de document_id.",
                    context={"title": title, "file_path": file_path},
                )
            )
            continue

        if not content:
            warnings.append(
                ChunkerMessage(
                    code="document_without_content",
                    message="Documento ignorado por não possuir conteúdo textual.",
                    context={
                        "document_id": document_id,
                        "title": title,
                        "file_path": file_path,
                    },
                )
            )
            continue

        if len(content) < 120:
            warnings.append(
                ChunkerMessage(
                    code="document_content_too_short",
                    message="Documento com conteúdo muito curto; será chunkado em bloco único.",
                    context={
                        "document_id": document_id,
                        "content_length": len(content),
                    },
                )
            )

        tags: list[str] = []
        if isinstance(tags_raw, list):
            tags = [str(tag).strip() for tag in tags_raw if str(tag).strip()]

        split_result = _split_text_with_overlap(
            content,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        if not split_result:
            warnings.append(
                ChunkerMessage(
                    code="document_split_result_empty",
                    message="Documento não gerou chunks após processamento.",
                    context={
                        "document_id": document_id,
                        "title": title,
                    },
                )
            )
            continue

        documents_chunked += 1

        for chunk_index, (char_start, char_end, chunk_text) in enumerate(split_result, start=1):
            chunks.append(
                ChunkRecord(
                    chunk_id=_build_chunk_id(document_id, chunk_index),
                    document_id=document_id,
                    title=title,
                    theme=theme,
                    file_path=file_path,
                    chunk_index=chunk_index,
                    chunk_char_start=char_start,
                    chunk_char_end=char_end,
                    text=chunk_text,
                    text_length=len(chunk_text),
                    status=str(status) if status is not None else None,
                    version=str(version) if version is not None else None,
                    tags=tags,
                )
            )

    return ChunkingReport(
        is_valid=len(errors) == 0,
        documents_received=documents_received,
        documents_chunked=documents_chunked,
        chunks_created=len(chunks),
        chunks=chunks,
        errors=errors,
        warnings=warnings,
    )


def chunk_docsia_documents_from_json_payload(
    extracted_payload: dict[str, Any],
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> ChunkingReport:
    documents = extracted_payload.get("extracted_documents") or []
    return chunk_extracted_documents(
        documents,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


def _load_demo_documents_from_extractor() -> list[Any]:
    try:
        from backend.ai_analyst.ingest.extractor import extract_docsia_documents
    except Exception:
        return []

    docsia_path = Path("/srv/profiledna/backend/ai_analyst/docsIA")
    report = extract_docsia_documents(docsia_path)

    if not getattr(report, "is_valid", False):
        return []

    return list(getattr(report, "extracted_documents", []) or [])


def _report_to_json(report: ChunkingReport) -> str:
    payload = {
        "is_valid": report.is_valid,
        "documents_received": report.documents_received,
        "documents_chunked": report.documents_chunked,
        "chunks_created": report.chunks_created,
        "chunks": [asdict(item) for item in report.chunks],
        "errors": [asdict(item) for item in report.errors],
        "warnings": [asdict(item) for item in report.warnings],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def main() -> None:
    extracted_documents = _load_demo_documents_from_extractor()
    report = chunk_extracted_documents(extracted_documents)
    print(_report_to_json(report))


if __name__ == "__main__":
    main()
