# /srv/profiledna/backend/ai_analyst/ingest/extractor.py
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from backend.ai_analyst.ingest.validators import (
    DOCSIA_BASE_PATH,
    MANIFEST_FILENAME,
    resolve_manifest_file_path,
    validate_docsia_base,
)

try:
    from pypdf import PdfReader  # type: ignore

    PDF_ENGINE = "pypdf"
except Exception:  # pragma: no cover
    try:
        from PyPDF2 import PdfReader  # type: ignore

        PDF_ENGINE = "PyPDF2"
    except Exception:  # pragma: no cover
        PdfReader = None  # type: ignore
        PDF_ENGINE = "unavailable"


SUPPORTED_CONTENT_TYPES = {
    ".pdf": "application/pdf",
}


@dataclass(slots=True)
class ExtractionMessage:
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExtractionDocument:
    document_id: str
    title: str
    theme: str
    source_type: str
    version: str
    status: str
    tags: list[str]
    file_path: str
    sha256: str
    included_at: str | None
    content_type: str
    page_count: int
    char_count: int
    text: str
    extraction_engine: str


@dataclass(slots=True)
class ExtractionReport:
    is_valid: bool
    documents_extracted: int
    documents_skipped: int
    extracted_documents: list[ExtractionDocument]
    errors: list[ExtractionMessage]
    warnings: list[ExtractionMessage]

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "documents_extracted": self.documents_extracted,
            "documents_skipped": self.documents_skipped,
            "extracted_documents": [asdict(item) for item in self.extracted_documents],
            "errors": [asdict(item) for item in self.errors],
            "warnings": [asdict(item) for item in self.warnings],
        }


class DocsIAExtractionError(Exception):
    """Erro fatal durante extração documental."""


def _load_manifest(docsia_path: Path) -> dict[str, Any]:
    manifest_path = docsia_path / MANIFEST_FILENAME
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DocsIAExtractionError(
            f"manifest.json não encontrado em {manifest_path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise DocsIAExtractionError(
            f"manifest.json inválido em {manifest_path}: linha {exc.lineno}, coluna {exc.colno}"
        ) from exc


def _resolve_repo_path(file_path: str) -> Path:
    return resolve_manifest_file_path(file_path)


def _extract_pdf_text(file_path: Path) -> tuple[str, int]:
    if PdfReader is None:
        raise DocsIAExtractionError(
            "Nenhuma biblioteca de leitura de PDF disponível. Instale pypdf ou PyPDF2."
        )

    reader = PdfReader(str(file_path))
    page_count = len(reader.pages)
    page_texts: list[str] = []

    for page_index, page in enumerate(reader.pages):
        try:
            raw_text = page.extract_text() or ""
        except Exception as exc:
            raise DocsIAExtractionError(
                f"Falha ao extrair texto do PDF {file_path} na página {page_index + 1}: {exc}"
            ) from exc

        normalized = raw_text.replace("\x00", "").strip()
        if normalized:
            page_texts.append(normalized)

    text = "\n\n".join(page_texts).strip()
    return text, page_count


def _extract_document(
    doc: dict[str, Any],
    warnings: list[ExtractionMessage],
) -> ExtractionDocument:
    file_path_str = str(doc["file_path"]).strip()
    resolved_path = _resolve_repo_path(file_path_str)
    suffix = resolved_path.suffix.lower()

    if suffix not in SUPPORTED_CONTENT_TYPES:
        raise DocsIAExtractionError(
            f"Extensão não suportada para extração nesta fase: {suffix or '<sem extensão>'}"
        )

    content_type = SUPPORTED_CONTENT_TYPES[suffix]

    if not resolved_path.exists():
        raise DocsIAExtractionError(f"Arquivo não encontrado: {resolved_path}")

    if not resolved_path.is_file():
        raise DocsIAExtractionError(f"Caminho não é arquivo regular: {resolved_path}")

    if content_type == "application/pdf":
        text, page_count = _extract_pdf_text(resolved_path)
    else:  # pragma: no cover
        raise DocsIAExtractionError(f"content_type não suportado: {content_type}")

    if not text:
        warnings.append(
            ExtractionMessage(
                code="empty_extracted_text",
                message="Documento processado sem texto extraível.",
                context={
                    "document_id": doc["document_id"],
                    "file_path": file_path_str,
                },
            )
        )

    return ExtractionDocument(
        document_id=str(doc["document_id"]),
        title=str(doc["title"]),
        theme=str(doc["theme"]),
        source_type=str(doc["source_type"]),
        version=str(doc["version"]),
        status=str(doc["status"]),
        tags=list(doc.get("tags", [])),
        file_path=file_path_str,
        sha256=str(doc["hash"]),
        included_at=doc.get("included_at"),
        content_type=content_type,
        page_count=page_count,
        char_count=len(text),
        text=text,
        extraction_engine=PDF_ENGINE,
    )


def extract_docsia_documents(
    docsia_path: Path = DOCSIA_BASE_PATH,
    *,
    include_statuses: set[str] | None = None,
) -> ExtractionReport:
    """
    Extrai texto bruto dos documentos catalogados no manifest.json.

    Regras:
    - valida a base docsIA antes de extrair;
    - por padrão extrai apenas documentos approved;
    - nesta versão suporta PDF;
    - não interpreta nem resume conteúdo;
    - retorna estrutura auditável pronta para chunking.
    """
    docsia_path = docsia_path.resolve()
    include_statuses = include_statuses or {"approved"}

    errors: list[ExtractionMessage] = []
    warnings: list[ExtractionMessage] = []
    extracted_documents: list[ExtractionDocument] = []
    documents_skipped = 0

    validation_report = validate_docsia_base(docsia_path)
    if not validation_report.is_valid:
        for item in validation_report.errors:
            errors.append(
                ExtractionMessage(
                    code=f"validation::{item.code}",
                    message=item.message,
                    context=item.context,
                )
            )
        return ExtractionReport(
            is_valid=False,
            documents_extracted=0,
            documents_skipped=0,
            extracted_documents=[],
            errors=errors,
            warnings=warnings,
        )

    manifest = _load_manifest(docsia_path)
    documents = manifest.get("documents", [])

    for doc in documents:
        document_id = doc.get("document_id")
        status = str(doc.get("status", "")).strip()

        if status not in include_statuses:
            documents_skipped += 1
            warnings.append(
                ExtractionMessage(
                    code="document_skipped_by_status",
                    message="Documento não entrou na extração por causa do status.",
                    context={
                        "document_id": document_id,
                        "status": status,
                        "allowed_statuses": sorted(include_statuses),
                    },
                )
            )
            continue

        try:
            extracted = _extract_document(doc, warnings)
            extracted_documents.append(extracted)
        except DocsIAExtractionError as exc:
            errors.append(
                ExtractionMessage(
                    code="document_extraction_failed",
                    message=str(exc),
                    context={
                        "document_id": document_id,
                        "file_path": doc.get("file_path"),
                    },
                )
            )

    is_valid = len(errors) == 0

    return ExtractionReport(
        is_valid=is_valid,
        documents_extracted=len(extracted_documents),
        documents_skipped=documents_skipped,
        extracted_documents=extracted_documents,
        errors=errors,
        warnings=warnings,
    )


def run_extraction_as_json(
    docsia_path: Path = DOCSIA_BASE_PATH,
    *,
    include_statuses: set[str] | None = None,
) -> str:
    report = extract_docsia_documents(
        docsia_path=docsia_path,
        include_statuses=include_statuses,
    )
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    print(run_extraction_as_json())
