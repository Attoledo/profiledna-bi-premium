from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_EMBEDDING_PROVIDER = "local_stub"
DEFAULT_EMBEDDING_MODEL = "deterministic-prep-v1"
DEFAULT_EMBEDDING_STATUS = "prepared"


@dataclass(frozen=True)
class EmbeddingIssue:
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EmbeddingRecord:
    embedding_id: str
    chunk_id: str
    document_id: str
    title: str
    theme: str
    file_path: str
    chunk_index: int
    text: str
    normalized_text: str
    text_length: int
    token_estimate: int
    fingerprint: str
    embedding_status: str
    embedding_provider: str
    embedding_model: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EmbeddingBuildReport:
    is_valid: bool
    chunks_received: int
    embeddings_created: int
    embeddings: list[EmbeddingRecord] = field(default_factory=list)
    errors: list[EmbeddingIssue] = field(default_factory=list)
    warnings: list[EmbeddingIssue] = field(default_factory=list)


def _normalize_text(value: str) -> str:
    text = str(value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _estimate_tokens(value: str) -> int:
    """
    Estimativa simples e determinística para auditabilidade.
    Usa aproximação por caracteres úteis / 4, com piso mínimo de 1
    quando houver texto não vazio.
    """
    normalized = _normalize_text(value)
    if not normalized:
        return 0
    return max(1, math.ceil(len(normalized) / 4))


def _build_fingerprint(
    *,
    chunk_id: str,
    document_id: str,
    theme: str,
    normalized_text: str,
) -> str:
    raw = "||".join(
        [
            str(chunk_id).strip(),
            str(document_id).strip(),
            str(theme).strip(),
            normalized_text,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _validate_chunk_payload(chunk: dict[str, Any]) -> list[EmbeddingIssue]:
    issues: list[EmbeddingIssue] = []

    if not str(chunk.get("chunk_id") or "").strip():
        issues.append(
            EmbeddingIssue(
                code="missing_chunk_id",
                message="Chunk sem chunk_id não pode entrar na preparação de embeddings.",
                context={"chunk": chunk},
            )
        )

    if not str(chunk.get("document_id") or "").strip():
        issues.append(
            EmbeddingIssue(
                code="missing_document_id",
                message="Chunk sem document_id não pode entrar na preparação de embeddings.",
                context={"chunk_id": chunk.get("chunk_id")},
            )
        )

    if not str(chunk.get("theme") or "").strip():
        issues.append(
            EmbeddingIssue(
                code="missing_theme",
                message="Chunk sem theme não pode entrar na preparação de embeddings.",
                context={
                    "chunk_id": chunk.get("chunk_id"),
                    "document_id": chunk.get("document_id"),
                },
            )
        )

    text = _normalize_text(str(chunk.get("text") or ""))
    if not text:
        issues.append(
            EmbeddingIssue(
                code="empty_chunk_text",
                message="Chunk sem texto útil foi rejeitado na preparação de embeddings.",
                context={
                    "chunk_id": chunk.get("chunk_id"),
                    "document_id": chunk.get("document_id"),
                },
            )
        )

    return issues


def build_embedding_records(
    chunks: list[dict[str, Any]],
    *,
    embedding_provider: str = DEFAULT_EMBEDDING_PROVIDER,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
) -> EmbeddingBuildReport:
    errors: list[EmbeddingIssue] = []
    warnings: list[EmbeddingIssue] = []
    embeddings: list[EmbeddingRecord] = []

    for chunk in chunks:
        chunk_errors = _validate_chunk_payload(chunk)
        if chunk_errors:
            errors.extend(chunk_errors)
            continue

        chunk_id = str(chunk.get("chunk_id") or "").strip()
        document_id = str(chunk.get("document_id") or "").strip()
        title = str(chunk.get("title") or "").strip()
        theme = str(chunk.get("theme") or "").strip()
        file_path = str(chunk.get("file_path") or "").strip()
        chunk_index = _safe_int(chunk.get("chunk_index"), default=0)
        text = str(chunk.get("text") or "")
        normalized_text = _normalize_text(text)
        text_length = _safe_int(chunk.get("text_length"), default=len(normalized_text))

        if text_length != len(normalized_text):
            warnings.append(
                EmbeddingIssue(
                    code="text_length_adjusted",
                    message="text_length informado não bateu com o texto normalizado; valor foi ajustado logicamente.",
                    context={
                        "chunk_id": chunk_id,
                        "declared_text_length": chunk.get("text_length"),
                        "normalized_text_length": len(normalized_text),
                    },
                )
            )
            text_length = len(normalized_text)

        token_estimate = _estimate_tokens(normalized_text)
        fingerprint = _build_fingerprint(
            chunk_id=chunk_id,
            document_id=document_id,
            theme=theme,
            normalized_text=normalized_text,
        )

        embedding_id = f"{chunk_id}::embedding"

        metadata = {
            "document_id": document_id,
            "chunk_id": chunk_id,
            "chunk_index": chunk_index,
            "theme": theme,
            "title": title,
            "file_path": file_path,
            "text_length": text_length,
            "token_estimate": token_estimate,
            "fingerprint": fingerprint,
        }

        embeddings.append(
            EmbeddingRecord(
                embedding_id=embedding_id,
                chunk_id=chunk_id,
                document_id=document_id,
                title=title,
                theme=theme,
                file_path=file_path,
                chunk_index=chunk_index,
                text=text,
                normalized_text=normalized_text,
                text_length=text_length,
                token_estimate=token_estimate,
                fingerprint=fingerprint,
                embedding_status=DEFAULT_EMBEDDING_STATUS,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
                metadata=metadata,
            )
        )

    return EmbeddingBuildReport(
        is_valid=len(errors) == 0,
        chunks_received=len(chunks),
        embeddings_created=len(embeddings),
        embeddings=embeddings,
        errors=errors,
        warnings=warnings,
    )


def _report_to_jsonable(report: EmbeddingBuildReport) -> dict[str, Any]:
    return {
        "is_valid": report.is_valid,
        "chunks_received": report.chunks_received,
        "embeddings_created": report.embeddings_created,
        "embeddings": [asdict(item) for item in report.embeddings],
        "errors": [asdict(item) for item in report.errors],
        "warnings": [asdict(item) for item in report.warnings],
    }


def main() -> None:
    """
    Execução local simples e auditável.
    Não lê banco nem serviços externos.
    Apenas demonstra o contrato do módulo com lista vazia por padrão.
    """
    report = build_embedding_records([])
    print(
        json.dumps(
            _report_to_jsonable(report),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
