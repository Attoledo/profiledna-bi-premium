from __future__ import annotations

from typing import Dict, List, Tuple

from backend.scoring.rules import (
    ab_to_letters,
    compute_bands,
    count_scores,
    get_bottom_n,
    get_top_n,
)
from backend.scoring.types import AnswerAB, DimensionLetter, EngineResult, TopBottom
from backend.ssot.loader import load_json


def _load_dimensions_letters() -> List[DimensionLetter]:
    """
    Carrega dimensions_20.json e retorna a lista de letras esperadas (20).
    O formato exato do JSON é definido pelo SSOT; aqui aceitamos:
      - lista de objetos com campo "letter"
      - ou dict { "A": {...}, "B": {...} }
    """
    data = load_json("data/ssot/profiledna/v1/dimensions_20.json")

    letters: List[str] = []
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict) or "letter" not in item:
                raise ValueError("dimensions_20.json: expected list of objects with 'letter'")
            letters.append(str(item["letter"]))
    elif isinstance(data, dict):
        letters = [str(k) for k in data.keys()]
    else:
        raise ValueError("dimensions_20.json: invalid JSON shape")

    letters_sorted = sorted(letters)
    if len(letters_sorted) != 20:
        raise ValueError(f"dimensions_20.json: expected 20 dimensions, got {len(letters_sorted)}")

    # SSOT diz letras A..T (20 letras)
    return letters_sorted


def _load_gabarito_map() -> Dict[int, Tuple[DimensionLetter, DimensionLetter]]:
    """
    Carrega gabarito_100.json e monta mapa:
      q_number (1..100) -> (letter_if_A, letter_if_B)

    Aceitamos formato:
      - lista de objetos: {"number": 1, "letter_if_A": "L", "letter_if_B": "T"}
      - ou {"1": ["L","T"], ...} / {"1": {"A":"L","B":"T"}, ...}
    """
    data = load_json("data/ssot/profiledna/v1/gabarito_100.json")

    m: Dict[int, Tuple[str, str]] = {}

    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                raise ValueError("gabarito_100.json: expected list of dicts")
            if "number" not in item:
                raise ValueError("gabarito_100.json: missing 'number'")
            n = int(item["number"])
            la = item.get("letter_if_A")
            lb = item.get("letter_if_B")
            if la is None or lb is None:
                raise ValueError(f"gabarito_100.json: missing letter_if_A/letter_if_B for {n}")
            m[n] = (str(la), str(lb))

    elif isinstance(data, dict):
        # chaves podem ser strings "1".."100"
        for k, v in data.items():
            n = int(k)
            if isinstance(v, (list, tuple)) and len(v) == 2:
                m[n] = (str(v[0]), str(v[1]))
            elif isinstance(v, dict):
                if "A" in v and "B" in v:
                    m[n] = (str(v["A"]), str(v["B"]))
                else:
                    raise ValueError(f"gabarito_100.json: dict entry for {n} missing A/B")
            else:
                raise ValueError(f"gabarito_100.json: invalid entry for {n}")
    else:
        raise ValueError("gabarito_100.json: invalid JSON shape")

    if len(m) != 100:
        raise ValueError(f"gabarito_100.json: expected 100 entries, got {len(m)}")

    # garante presença de 1..100
    missing = [i for i in range(1, 101) if i not in m]
    if missing:
        raise ValueError(f"gabarito_100.json: missing question numbers {missing[:10]}...")

    return {int(k): (v[0], v[1]) for k, v in m.items()}


def compute_scores(answers: List[AnswerAB]) -> EngineResult:
    """
    Motor determinístico (SSOT):
      1) A/B -> letras via gabarito
      2) count -> score (0..10)
      3) band: low/mid/high (0–3 / 4–6 / 7–10)
      4) top3/top5/bottom3 com desempate letra ASC
    """
    expected_letters = _load_dimensions_letters()
    gabarito_map = _load_gabarito_map()

    letters = ab_to_letters(answers=answers, gabarito_number_to_letters=gabarito_map)
    scores = count_scores(letters=letters, expected_letters=expected_letters)
    bands = compute_bands(scores)

    ranking = TopBottom(
        top3=get_top_n(scores, 3),
        top5=get_top_n(scores, 5),
        bottom3=get_bottom_n(scores, 3),
    )

    return EngineResult(scores=scores, bands=bands, ranking=ranking)
