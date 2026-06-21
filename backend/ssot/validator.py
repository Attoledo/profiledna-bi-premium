from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List

from backend.config import get_settings
from backend.ssot.loader import abs_path, file_exists, load_json, read_text, repo_root_str


@dataclass(frozen=True)
class SSOTValidationResult:
    ok: bool
    ssot_md_path: str
    canonical_questions_path: str
    required_json_paths: List[str]
    missing_files: List[str]
    invalid_json_files: List[str]
    semantic_errors: List[str]
    notes: List[str]


_JSON_RE = re.compile(r"[\w./-]+\.json")

# SSOT 6.5: dimensões válidas são as letras A..T (20 letras).
_VALID_DIMENSION_LETTERS = {chr(code) for code in range(ord("A"), ord("T") + 1)}

# SSOT 6.5: contrato de enum do campo `area` em dimensions_20.json (fail-fast, sem normalização).
_VALID_AREAS = {"GERENCIAL", "INTER PESSOAL", "PESSOAL"}


def _extract_json_paths_from_ssot(md_text: str) -> List[str]:
    return sorted(set(_JSON_RE.findall(md_text)))


def _normalize_path(p: str) -> str:
    """
    Normaliza caminhos conforme SSOT.

    Regras:
    - QUESTIONS_PDF_CORRIGIDO_CANONICAL.json -> docs/QUESTIONS_PDF_CORRIGIDO_CANONICAL.json
    - golden_inputs.json/golden_outputs.json -> backend/scoring/fixtures/
    - premium_library_0_3_4_6_7_10.json é ALIAS: tratar como library2_premium.json (SSOT)
    - demais json “soltos” -> data/ssot/profiledna/v1/
    """
    # Alias do SSOT: referências tipo "fixtures/golden_inputs.json"
    if p.startswith("fixtures/") and (p.endswith("golden_inputs.json") or p.endswith("golden_outputs.json")):
        return "backend/scoring/fixtures/" + p.split("/")[-1]

    # se já tem diretório, mantém (mas aplica alias se necessário)
    if "/" in p:
        if p.endswith("premium_library_0_3_4_6_7_10.json"):
            return p.replace("premium_library_0_3_4_6_7_10.json", "library2_premium.json")
        return p

    if p == "QUESTIONS_PDF_CORRIGIDO_CANONICAL.json":
        return "docs/QUESTIONS_PDF_CORRIGIDO_CANONICAL.json"

    if p in {"golden_inputs.json", "golden_outputs.json"}:
        return f"backend/scoring/fixtures/{p}"

    # alias de compatibilidade do SSOT
    if p == "premium_library_0_3_4_6_7_10.json":
        return "data/ssot/profiledna/v1/library2_premium.json"

    return f"data/ssot/profiledna/v1/{p}"


def _validate_questions_100(data: Any) -> List[str]:
    """
    SSOT 6.10: exatamente 100 questões, numeradas 1..100 sem repetição.
    """
    errors: List[str] = []

    if not isinstance(data, list):
        return ["questions_100.json: esperado uma lista de perguntas."]

    if len(data) != 100:
        errors.append(
            f"questions_100.json: esperado exatamente 100 perguntas, encontrado {len(data)}."
        )

    required_keys = {"number", "option_a", "option_b"}
    numbers: List[int] = []

    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            errors.append(f"questions_100.json[{idx}]: item não é um objeto.")
            continue

        missing_keys = required_keys - set(item.keys())
        if missing_keys:
            errors.append(
                f"questions_100.json[{idx}]: chaves obrigatórias ausentes {sorted(missing_keys)}."
            )
            continue

        numbers.append(item["number"])

    if numbers:
        if len(set(numbers)) != len(numbers):
            errors.append("questions_100.json: campo 'number' contém valores duplicados.")
        if sorted(numbers) != list(range(1, 101)):
            errors.append("questions_100.json: campo 'number' deve cobrir exatamente 1..100.")

    return errors


def _validate_gabarito_100(data: Any) -> List[str]:
    """
    SSOT 6.10: gabarito mapeia exatamente 100 entradas (1..100, sem repetição),
    cada uma com letter_if_A/letter_if_B válidas (A..T), somando 200 letras pontuadas.
    """
    errors: List[str] = []

    if not isinstance(data, list):
        return ["gabarito_100.json: esperado uma lista de entradas."]

    if len(data) != 100:
        errors.append(
            f"gabarito_100.json: esperado exatamente 100 entradas, encontrado {len(data)}."
        )

    required_keys = {"number", "letter_if_A", "letter_if_B"}
    numbers: List[int] = []
    total_letters = 0

    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            errors.append(f"gabarito_100.json[{idx}]: item não é um objeto.")
            continue

        missing_keys = required_keys - set(item.keys())
        if missing_keys:
            errors.append(
                f"gabarito_100.json[{idx}]: chaves obrigatórias ausentes {sorted(missing_keys)}."
            )
            continue

        numbers.append(item["number"])

        for key in ("letter_if_A", "letter_if_B"):
            letter = item[key]
            total_letters += 1
            if letter not in _VALID_DIMENSION_LETTERS:
                errors.append(
                    f"gabarito_100.json[{idx}].{key}: letra '{letter}' inválida "
                    f"(esperado A..T)."
                )

    if numbers:
        if len(set(numbers)) != len(numbers):
            errors.append("gabarito_100.json: campo 'number' contém valores duplicados.")
        if sorted(numbers) != list(range(1, 101)):
            errors.append("gabarito_100.json: campo 'number' deve cobrir exatamente 1..100.")

    if total_letters != 200:
        errors.append(
            f"gabarito_100.json: soma de letras pontuadas (letter_if_A + letter_if_B) "
            f"deve ser 200, encontrado {total_letters}."
        )

    return errors


def _validate_dimensions_20(data: Any) -> List[str]:
    """
    SSOT 6.10/6.5: exatamente 20 dimensões, letras A..T sem repetição,
    enum `area` estritamente em {GERENCIAL, INTER PESSOAL, PESSOAL} (fail-fast).
    """
    errors: List[str] = []

    if not isinstance(data, list):
        return ["dimensions_20.json: esperado uma lista de dimensões."]

    if len(data) != 20:
        errors.append(
            f"dimensions_20.json: esperado exatamente 20 dimensões, encontrado {len(data)}."
        )

    required_keys = {"letter", "name", "area", "competency_rh"}
    letters: List[str] = []

    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            errors.append(f"dimensions_20.json[{idx}]: item não é um objeto.")
            continue

        missing_keys = required_keys - set(item.keys())
        if missing_keys:
            errors.append(
                f"dimensions_20.json[{idx}]: chaves obrigatórias ausentes {sorted(missing_keys)}."
            )
            continue

        letter = item["letter"]
        letters.append(letter)

        if letter not in _VALID_DIMENSION_LETTERS:
            errors.append(
                f"dimensions_20.json[{idx}]: letra '{letter}' fora do intervalo A..T."
            )

        area = item["area"]
        if area not in _VALID_AREAS:
            errors.append(
                f"dimensions_20.json[{idx}] (letter={letter!r}): area '{area}' inválida "
                f"(esperado um de {sorted(_VALID_AREAS)})."
            )

    if letters:
        if len(set(letters)) != len(letters):
            duplicated = sorted({letter for letter in letters if letters.count(letter) > 1})
            errors.append(
                f"dimensions_20.json: letras duplicadas (sem repetição esperado): {duplicated}."
            )

        missing_letters = sorted(_VALID_DIMENSION_LETTERS - set(letters))
        if missing_letters:
            errors.append(
                f"dimensions_20.json: letras ausentes para cobertura A..T: {missing_letters}."
            )

    return errors


# Validações semânticas/matemáticas (SSOT 6.10), aplicadas apenas se o arquivo
# correspondente existir e for JSON válido.
_SEMANTIC_VALIDATORS = {
    "data/ssot/profiledna/v1/questions_100.json": _validate_questions_100,
    "data/ssot/profiledna/v1/gabarito_100.json": _validate_gabarito_100,
    "data/ssot/profiledna/v1/dimensions_20.json": _validate_dimensions_20,
}


def validate_ssot(strict: bool = False) -> SSOTValidationResult:
    settings = get_settings()
    ssot_md = "docs/SSOT_PROFILEDNA_v2_0.md"
    canonical = settings.QUESTIONS_PDF_CORRIGIDO_CANONICAL

    notes: List[str] = []
    missing: List[str] = []
    invalid: List[str] = []
    semantic_errors: List[str] = []

    if not file_exists(ssot_md):
        missing.append(ssot_md)
        res = SSOTValidationResult(
            ok=False,
            ssot_md_path=abs_path(ssot_md),
            canonical_questions_path=abs_path(canonical),
            required_json_paths=[],
            missing_files=missing,
            invalid_json_files=[],
            semantic_errors=[],
            notes=["SSOT markdown não encontrado no repo."],
        )
        if strict:
            raise RuntimeError(f"SSOT validation failed: missing {missing}")
        return res

    md_text = read_text(ssot_md)
    raw_required = _extract_json_paths_from_ssot(md_text)

    # Garante canonical na validação (SSOT)
    if canonical not in raw_required and "QUESTIONS_PDF_CORRIGIDO_CANONICAL.json" not in raw_required:
        raw_required.append("QUESTIONS_PDF_CORRIGIDO_CANONICAL.json")

    required = sorted({_normalize_path(p) for p in raw_required})

    loaded: Dict[str, Any] = {}

    for p in required:
        if not file_exists(p):
            missing.append(p)
            continue
        try:
            loaded[p] = load_json(p)
        except json.JSONDecodeError:
            invalid.append(p)
        except Exception:
            invalid.append(p)

    # Validações semânticas/matemáticas do motor psicométrico (SSOT 6.10).
    # Política de qualidade: rejeita (fail-fast) divergências, sem normalizar silenciosamente.
    for path, validator_fn in _SEMANTIC_VALIDATORS.items():
        if path in loaded:
            semantic_errors.extend(validator_fn(loaded[path]))

    ok = (len(missing) == 0 and len(invalid) == 0 and len(semantic_errors) == 0)

    res = SSOTValidationResult(
        ok=ok,
        ssot_md_path=abs_path(ssot_md),
        canonical_questions_path=abs_path(_normalize_path("QUESTIONS_PDF_CORRIGIDO_CANONICAL.json")),
        required_json_paths=required,
        missing_files=missing,
        invalid_json_files=invalid,
        semantic_errors=semantic_errors,
        notes=notes + [f"repo_root={repo_root_str()}"],
    )

    if strict and not ok:
        raise RuntimeError(
            f"SSOT validation failed. missing={missing} invalid={invalid} semantic={semantic_errors}"
        )

    return res
