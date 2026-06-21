from __future__ import annotations

from collections import Counter
from typing import Dict, Iterable, List, Mapping, Sequence

from backend.scoring.types import AnswerAB, BandKey, DimensionLetter


def score_to_band(score: int) -> BandKey:
    """
    SSOT:
      0–3 => low
      4–6 => mid
      7–10 => high
    """
    if score <= 3:
        return "low"
    if score <= 6:
        return "mid"
    return "high"


def get_top_n(scores: Mapping[DimensionLetter, int], n: int) -> List[DimensionLetter]:
    """
    SSOT:
      - maiores scores primeiro
      - desempate determinístico: letra ASC
    """
    if n <= 0:
        return []
    items = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return [k for k, _ in items[:n]]


def get_bottom_n(scores: Mapping[DimensionLetter, int], n: int) -> List[DimensionLetter]:
    """
    SSOT:
      - menores scores primeiro
      - desempate determinístico: letra ASC
    """
    if n <= 0:
        return []
    items = sorted(scores.items(), key=lambda kv: (kv[1], kv[0]))
    return [k for k, _ in items[:n]]


def ab_to_letters(
    answers: Sequence[AnswerAB],
    gabarito_number_to_letters: Mapping[int, tuple[DimensionLetter, DimensionLetter]],
) -> List[DimensionLetter]:
    """
    Converte respostas A/B (len=100) em letras A..T via gabarito.

    `gabarito_number_to_letters` deve mapear:
      question_number (1..100) -> (letter_if_A, letter_if_B)
    """
    if len(answers) != 100:
        raise ValueError(f"Expected 100 answers, got {len(answers)}")

    letters: List[DimensionLetter] = []
    for idx, ab in enumerate(answers, start=1):
        if idx not in gabarito_number_to_letters:
            raise ValueError(f"Missing gabarito mapping for question {idx}")

        la, lb = gabarito_number_to_letters[idx]
        letters.append(la if ab == "A" else lb)

    return letters


def count_scores(
    letters: Iterable[DimensionLetter],
    expected_letters: Iterable[DimensionLetter],
) -> Dict[DimensionLetter, int]:
    """
    Conta ocorrências por letra.

    SSOT: score = count (0..10).
    Validamos que:
      - o total de letras é 100
      - todas as letras esperadas existem no output (mesmo se score 0)
    """
    letters_list = list(letters)
    if len(letters_list) != 100:
        raise ValueError(f"Expected 100 letters, got {len(letters_list)}")

    counts = Counter(letters_list)

    out: Dict[DimensionLetter, int] = {l: int(counts.get(l, 0)) for l in expected_letters}
    if sum(out.values()) != 100:
        # pode ocorrer se expected_letters não cobrir todas as letras presentes
        # ou se houver letra inválida no gabarito.
        extra = set(counts.keys()) - set(out.keys())
        raise ValueError(f"Score sum != 100. Extra letters present: {sorted(extra)}")

    return out


def compute_bands(scores: Mapping[DimensionLetter, int]) -> Dict[DimensionLetter, BandKey]:
    """
    Calcula band_key por letra.
    """
    return {k: score_to_band(v) for k, v in scores.items()}
