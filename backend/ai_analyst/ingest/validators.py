# /srv/profiledna/backend/ai_analyst/ingest/validators.py
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOCSIA_BASE_PATH = PROJECT_ROOT / "backend" / "ai_analyst" / "docsIA"
README_FILENAME = "README.md"
MANIFEST_FILENAME = "manifest.json"

REQUIRED_MANIFEST_KEYS = {
    "manifest_version",
    "base_path",
    "status",
    "themes",
    "allowed_source_types",
    "allowed_statuses",
    "documents",
}

REQUIRED_DOCUMENT_KEYS = {
    "document_id",
    "title",
    "theme",
    "source_type",
    "version",
    "status",
    "tags",
    "file_path",
    "hash",
    "included_at",
}

SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
ISO_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+\-]\d{2}:\d{2})$"
)


class DocsIAValidationError(Exception):
    """Erro fatal de validação da base docsIA."""


@dataclass(slots=True)
class ValidationMessage:
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ValidationSummary:
    docsia_path: str
    manifest_path: str
    readme_exists: bool
    manifest_exists: bool
    total_themes_declared: int
    total_theme_dirs_found: int
    total_documents: int
    total_approved_documents: int
    total_draft_documents: int
    total_archived_documents: int


@dataclass(slots=True)
class ValidationReport:
    is_valid: bool
    errors: list[ValidationMessage]
    warnings: list[ValidationMessage]
    summary: ValidationSummary

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": [asdict(item) for item in self.errors],
            "warnings": [asdict(item) for item in self.warnings],
            "summary": asdict(self.summary),
        }


def get_runtime_project_root() -> Path:
    """
    Retorna o root real do projeto no runtime atual.

    Exemplo:
    - host: /srv/profiledna
    - container: /app
    """
    return PROJECT_ROOT


def resolve_docsia_path(docsia_path: Path | None = None) -> Path:
    """
    Resolve o caminho da docsIA de forma portátil.

    - Se nada for passado, usa o caminho oficial calculado a partir do módulo.
    - Se vier caminho relativo, resolve contra o root do projeto atual.
    - Se vier absoluto, apenas normaliza.
    """
    base = docsia_path or DOCSIA_BASE_PATH

    if not base.is_absolute():
        base = get_runtime_project_root() / base

    return base.resolve()


def resolve_manifest_file_path(file_path: str) -> Path:
    """
    Resolve file_path relativo do manifesto para caminho físico no runtime atual.
    """
    normalized = str(file_path or "").strip()
    return (get_runtime_project_root() / normalized).resolve()


def _sha256_file(file_path: Path) -> str:
    sha = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_valid_iso_datetime(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    if not ISO_DATETIME_RE.match(value.strip()):
        return False
    normalized = value.strip().replace("Z", "+00:00")
    try:
        datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return True


def _load_json_file(file_path: Path) -> dict[str, Any]:
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DocsIAValidationError(f"Arquivo JSON não encontrado: {file_path}") from exc
    except json.JSONDecodeError as exc:
        raise DocsIAValidationError(
            f"JSON inválido em {file_path}: linha {exc.lineno}, coluna {exc.colno}"
        ) from exc


def _build_summary(
    docsia_path: Path,
    manifest_path: Path,
    readme_exists: bool,
    manifest_exists: bool,
    manifest_data: dict[str, Any] | None,
    theme_dirs_found: int,
) -> ValidationSummary:
    documents = manifest_data.get("documents", []) if isinstance(manifest_data, dict) else []
    declared_themes = manifest_data.get("themes", []) if isinstance(manifest_data, dict) else []

    total_approved = 0
    total_draft = 0
    total_archived = 0

    for item in documents:
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        if status == "approved":
            total_approved += 1
        elif status == "draft":
            total_draft += 1
        elif status == "archived":
            total_archived += 1

    return ValidationSummary(
        docsia_path=str(docsia_path),
        manifest_path=str(manifest_path),
        readme_exists=readme_exists,
        manifest_exists=manifest_exists,
        total_themes_declared=len(declared_themes) if isinstance(declared_themes, list) else 0,
        total_theme_dirs_found=theme_dirs_found,
        total_documents=len(documents) if isinstance(documents, list) else 0,
        total_approved_documents=total_approved,
        total_draft_documents=total_draft,
        total_archived_documents=total_archived,
    )


def validate_docsia_base(
    docsia_path: Path = DOCSIA_BASE_PATH,
) -> ValidationReport:
    errors: list[ValidationMessage] = []
    warnings: list[ValidationMessage] = []

    docsia_path = resolve_docsia_path(docsia_path)
    readme_path = docsia_path / README_FILENAME
    manifest_path = docsia_path / MANIFEST_FILENAME

    if not docsia_path.exists():
        raise DocsIAValidationError(f"Pasta docsIA não encontrada: {docsia_path}")

    if not docsia_path.is_dir():
        raise DocsIAValidationError(f"O caminho docsIA não é diretório: {docsia_path}")

    readme_exists = readme_path.exists()
    manifest_exists = manifest_path.exists()

    if not readme_exists:
        errors.append(
            ValidationMessage(
                code="missing_readme",
                message="README.md obrigatório não encontrado em docsIA.",
                context={"path": str(readme_path)},
            )
        )

    manifest_data: dict[str, Any] | None = None
    if not manifest_exists:
        errors.append(
            ValidationMessage(
                code="missing_manifest",
                message="manifest.json obrigatório não encontrado em docsIA.",
                context={"path": str(manifest_path)},
            )
        )
    else:
        try:
            manifest_data = _load_json_file(manifest_path)
        except DocsIAValidationError as exc:
            errors.append(
                ValidationMessage(
                    code="invalid_manifest_json",
                    message=str(exc),
                    context={"path": str(manifest_path)},
                )
            )

    theme_dirs_found = 0
    if isinstance(manifest_data, dict):
        theme_dirs_found = _validate_manifest(
            docsia_path=docsia_path,
            manifest_data=manifest_data,
            errors=errors,
            warnings=warnings,
        )

    summary = _build_summary(
        docsia_path=docsia_path,
        manifest_path=manifest_path,
        readme_exists=readme_exists,
        manifest_exists=manifest_exists,
        manifest_data=manifest_data,
        theme_dirs_found=theme_dirs_found,
    )

    return ValidationReport(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        summary=summary,
    )


def _validate_manifest(
    docsia_path: Path,
    manifest_data: dict[str, Any],
    errors: list[ValidationMessage],
    warnings: list[ValidationMessage],
) -> int:
    missing_manifest_keys = sorted(REQUIRED_MANIFEST_KEYS - set(manifest_data.keys()))
    if missing_manifest_keys:
        errors.append(
            ValidationMessage(
                code="manifest_missing_keys",
                message="manifest.json está sem chaves obrigatórias.",
                context={"missing_keys": missing_manifest_keys},
            )
        )

    manifest_version = manifest_data.get("manifest_version")
    base_path = manifest_data.get("base_path")
    status = manifest_data.get("status")
    themes = manifest_data.get("themes")
    allowed_source_types = manifest_data.get("allowed_source_types")
    allowed_statuses = manifest_data.get("allowed_statuses")
    documents = manifest_data.get("documents")

    if not _is_non_empty_string(manifest_version):
        errors.append(
            ValidationMessage(
                code="invalid_manifest_version",
                message="manifest_version deve ser string não vazia.",
                context={"value": manifest_version},
            )
        )

    expected_base_path = "backend/ai_analyst/docsIA"
    if base_path != expected_base_path:
        errors.append(
            ValidationMessage(
                code="invalid_base_path",
                message="base_path do manifesto diverge do caminho oficial esperado.",
                context={"expected": expected_base_path, "received": base_path},
            )
        )

    if not _is_non_empty_string(status):
        errors.append(
            ValidationMessage(
                code="invalid_manifest_status",
                message="status do manifesto deve ser string não vazia.",
                context={"value": status},
            )
        )

    if not isinstance(themes, list) or not all(_is_non_empty_string(item) for item in themes):
        errors.append(
            ValidationMessage(
                code="invalid_themes",
                message="themes deve ser lista de strings não vazias.",
                context={"value": themes},
            )
        )
        themes = []

    if not isinstance(allowed_source_types, list) or not all(
        _is_non_empty_string(item) for item in allowed_source_types
    ):
        errors.append(
            ValidationMessage(
                code="invalid_allowed_source_types",
                message="allowed_source_types deve ser lista de strings não vazias.",
                context={"value": allowed_source_types},
            )
        )
        allowed_source_types = []

    if not isinstance(allowed_statuses, list) or not all(
        _is_non_empty_string(item) for item in allowed_statuses
    ):
        errors.append(
            ValidationMessage(
                code="invalid_allowed_statuses",
                message="allowed_statuses deve ser lista de strings não vazias.",
                context={"value": allowed_statuses},
            )
        )
        allowed_statuses = []

    if not isinstance(documents, list):
        errors.append(
            ValidationMessage(
                code="invalid_documents",
                message="documents deve ser uma lista.",
                context={"value_type": type(documents).__name__},
            )
        )
        documents = []

    theme_dirs_found = _validate_theme_directories(
        docsia_path=docsia_path,
        themes=themes,
        errors=errors,
    )

    _validate_documents(
        docsia_path=docsia_path,
        themes=set(themes),
        allowed_source_types=set(item.strip() for item in allowed_source_types),
        allowed_statuses=set(item.strip() for item in allowed_statuses),
        documents=documents,
        errors=errors,
        warnings=warnings,
    )

    return theme_dirs_found


def _validate_theme_directories(
    docsia_path: Path,
    themes: list[str],
    errors: list[ValidationMessage],
) -> int:
    found = 0
    for theme in themes:
        theme_dir = docsia_path / theme
        if theme_dir.exists() and theme_dir.is_dir():
            found += 1
        else:
            errors.append(
                ValidationMessage(
                    code="missing_theme_directory",
                    message="Subpasta temática declarada no manifesto não existe fisicamente.",
                    context={"theme": theme, "path": str(theme_dir)},
                )
            )
    return found


def _validate_documents(
    docsia_path: Path,
    themes: set[str],
    allowed_source_types: set[str],
    allowed_statuses: set[str],
    documents: list[dict[str, Any]],
    errors: list[ValidationMessage],
    warnings: list[ValidationMessage],
) -> None:
    seen_document_ids: set[str] = set()

    for index, item in enumerate(documents):
        context_base = {"document_index": index}

        if not isinstance(item, dict):
            errors.append(
                ValidationMessage(
                    code="invalid_document_entry",
                    message="Cada item de documents deve ser um objeto JSON.",
                    context=context_base | {"value_type": type(item).__name__},
                )
            )
            continue

        missing_keys = sorted(REQUIRED_DOCUMENT_KEYS - set(item.keys()))
        if missing_keys:
            errors.append(
                ValidationMessage(
                    code="document_missing_keys",
                    message="Documento do manifesto está sem campos obrigatórios.",
                    context=context_base | {"missing_keys": missing_keys},
                )
            )

        document_id = item.get("document_id")
        title = item.get("title")
        theme = item.get("theme")
        source_type = item.get("source_type")
        version = item.get("version")
        status = item.get("status")
        tags = item.get("tags")
        file_path = item.get("file_path")
        file_hash = item.get("hash")
        included_at = item.get("included_at")

        if not _is_non_empty_string(document_id):
            errors.append(
                ValidationMessage(
                    code="invalid_document_id",
                    message="document_id deve ser string não vazia.",
                    context=context_base | {"value": document_id},
                )
            )
        else:
            if document_id in seen_document_ids:
                errors.append(
                    ValidationMessage(
                        code="duplicate_document_id",
                        message="document_id duplicado no manifesto.",
                        context=context_base | {"document_id": document_id},
                    )
                )
            seen_document_ids.add(document_id)

        if not _is_non_empty_string(title):
            errors.append(
                ValidationMessage(
                    code="invalid_document_title",
                    message="title deve ser string não vazia.",
                    context=context_base | {"document_id": document_id, "value": title},
                )
            )

        if not _is_non_empty_string(theme) or theme not in themes:
            errors.append(
                ValidationMessage(
                    code="invalid_document_theme",
                    message="theme do documento é inválido ou não declarado em themes.",
                    context=context_base | {"document_id": document_id, "theme": theme},
                )
            )

        if not _is_non_empty_string(source_type) or source_type not in allowed_source_types:
            errors.append(
                ValidationMessage(
                    code="invalid_document_source_type",
                    message="source_type inválido para o documento.",
                    context=context_base
                    | {"document_id": document_id, "source_type": source_type},
                )
            )

        if not _is_non_empty_string(version):
            errors.append(
                ValidationMessage(
                    code="invalid_document_version",
                    message="version deve ser string não vazia.",
                    context=context_base | {"document_id": document_id, "value": version},
                )
            )

        if not _is_non_empty_string(status) or status not in allowed_statuses:
            errors.append(
                ValidationMessage(
                    code="invalid_document_status",
                    message="status inválido para o documento.",
                    context=context_base | {"document_id": document_id, "status": status},
                )
            )

        if not isinstance(tags, list) or not all(_is_non_empty_string(tag) for tag in tags):
            errors.append(
                ValidationMessage(
                    code="invalid_document_tags",
                    message="tags deve ser lista de strings não vazias.",
                    context=context_base | {"document_id": document_id, "tags": tags},
                )
            )

        physical_path = _validate_document_file_path(
            docsia_path=docsia_path,
            document_id=document_id,
            theme=theme,
            file_path=file_path,
            errors=errors,
            context_base=context_base,
        )

        _validate_document_state(
            document_id=document_id,
            status=status,
            physical_path=physical_path,
            file_hash=file_hash,
            included_at=included_at,
            errors=errors,
            warnings=warnings,
            context_base=context_base,
        )


def _validate_document_file_path(
    docsia_path: Path,
    document_id: Any,
    theme: Any,
    file_path: Any,
    errors: list[ValidationMessage],
    context_base: dict[str, Any],
) -> Path | None:
    if not _is_non_empty_string(file_path):
        errors.append(
            ValidationMessage(
                code="invalid_document_file_path",
                message="file_path deve ser string não vazia.",
                context=context_base | {"document_id": document_id, "file_path": file_path},
            )
        )
        return None

    normalized_file_path = file_path.strip()
    expected_prefix = "backend/ai_analyst/docsIA/"
    if not normalized_file_path.startswith(expected_prefix):
        errors.append(
            ValidationMessage(
                code="invalid_document_file_path_prefix",
                message="file_path deve começar com backend/ai_analyst/docsIA/.",
                context=context_base
                | {"document_id": document_id, "file_path": normalized_file_path},
            )
        )

    if _is_non_empty_string(theme):
        expected_theme_prefix = f"backend/ai_analyst/docsIA/{theme}/"
        if not normalized_file_path.startswith(expected_theme_prefix):
            errors.append(
                ValidationMessage(
                    code="file_path_theme_mismatch",
                    message="file_path não aponta para a subpasta coerente com o theme.",
                    context=context_base
                    | {
                        "document_id": document_id,
                        "theme": theme,
                        "file_path": normalized_file_path,
                        "expected_prefix": expected_theme_prefix,
                    },
                )
            )

    physical_path = resolve_manifest_file_path(normalized_file_path)
    return physical_path


def _validate_document_state(
    document_id: Any,
    status: Any,
    physical_path: Path | None,
    file_hash: Any,
    included_at: Any,
    errors: list[ValidationMessage],
    warnings: list[ValidationMessage],
    context_base: dict[str, Any],
) -> None:
    context = context_base | {"document_id": document_id}

    if status == "approved":
        if physical_path is None or not physical_path.exists():
            errors.append(
                ValidationMessage(
                    code="approved_document_missing_file",
                    message="Documento approved precisa existir fisicamente.",
                    context=context | {"path": str(physical_path) if physical_path else None},
                )
            )
        elif not physical_path.is_file():
            errors.append(
                ValidationMessage(
                    code="approved_document_not_file",
                    message="Caminho físico do documento approved não é arquivo regular.",
                    context=context | {"path": str(physical_path)},
                )
            )

        if not _is_non_empty_string(file_hash) or not SHA256_RE.match(file_hash.strip()):
            errors.append(
                ValidationMessage(
                    code="approved_document_invalid_hash",
                    message="Documento approved precisa ter hash SHA-256 válido.",
                    context=context | {"hash": file_hash},
                )
            )
        elif physical_path and physical_path.exists() and physical_path.is_file():
            actual_hash = _sha256_file(physical_path)
            if actual_hash != file_hash.strip():
                errors.append(
                    ValidationMessage(
                        code="approved_document_hash_mismatch",
                        message="Hash informado no manifesto diverge do arquivo físico.",
                        context=context
                        | {
                            "expected_hash": file_hash.strip(),
                            "actual_hash": actual_hash,
                            "path": str(physical_path),
                        },
                    )
                )

        if not _is_valid_iso_datetime(included_at):
            errors.append(
                ValidationMessage(
                    code="approved_document_invalid_included_at",
                    message="Documento approved precisa ter included_at preenchido em ISO-8601.",
                    context=context | {"included_at": included_at},
                )
            )

    elif status in {"draft", "archived"}:
        if physical_path and physical_path.exists() and physical_path.is_file():
            if _is_non_empty_string(file_hash):
                if not SHA256_RE.match(file_hash.strip()):
                    warnings.append(
                        ValidationMessage(
                            code="non_approved_document_invalid_hash_format",
                            message="Documento não approved tem hash preenchido com formato inválido.",
                            context=context | {"hash": file_hash},
                        )
                    )
            else:
                warnings.append(
                    ValidationMessage(
                        code="non_approved_document_missing_hash",
                        message=(
                            "Documento físico draft/archived existe sem hash registrado. "
                            "Isso é tolerado, mas reduz rastreabilidade."
                        ),
                        context=context | {"path": str(physical_path)},
                    )
                )

            if included_at is not None and not _is_valid_iso_datetime(included_at):
                warnings.append(
                    ValidationMessage(
                        code="non_approved_document_invalid_included_at",
                        message=(
                            "included_at de documento draft/archived está preenchido, "
                            "mas não está em formato ISO-8601 válido."
                        ),
                        context=context | {"included_at": included_at},
                    )
                )
        else:
            if _is_non_empty_string(file_hash):
                warnings.append(
                    ValidationMessage(
                        code="non_approved_document_hash_without_file",
                        message="Documento draft/archived possui hash preenchido, mas arquivo físico não existe.",
                        context=context | {"path": str(physical_path) if physical_path else None},
                    )
                )
            if included_at is not None and not _is_valid_iso_datetime(included_at):
                warnings.append(
                    ValidationMessage(
                        code="non_approved_document_invalid_included_at",
                        message=(
                            "included_at de documento draft/archived está preenchido, "
                            "mas não está em formato ISO-8601 válido."
                        ),
                        context=context | {"included_at": included_at},
                    )
                )


def run_validation_as_json(docsia_path: Path = DOCSIA_BASE_PATH) -> str:
    report = validate_docsia_base(docsia_path=docsia_path)
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    print(run_validation_as_json())
