from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from backend.scoring.engine import compute_scores


FIXTURES_DIR = Path("backend/scoring/fixtures")
INPUTS_PATH = FIXTURES_DIR / "golden_inputs.json"
OUTPUTS_PATH = FIXTURES_DIR / "golden_outputs.json"


def _vector_all(value: str) -> List[str]:
    return [value] * 100


def _vector_alternating(start: str = "A") -> List[str]:
    out: List[str] = []
    cur = start
    for _ in range(100):
        out.append(cur)
        cur = "B" if cur == "A" else "A"
    return out


def _vector_blocks(block_size: int = 10) -> List[str]:
    out: List[str] = []
    cur = "A"
    while len(out) < 100:
        out.extend([cur] * block_size)
        cur = "B" if cur == "A" else "A"
    return out[:100]


def build_inputs() -> List[Dict[str, Any]]:
    return [
        {"id": "all_A", "answers": _vector_all("A")},
        {"id": "all_B", "answers": _vector_all("B")},
        {"id": "alt_A_start", "answers": _vector_alternating("A")},
        {"id": "alt_B_start", "answers": _vector_alternating("B")},
        {"id": "blocks_10", "answers": _vector_blocks(10)},
        {"id": "blocks_5", "answers": _vector_blocks(5)},
    ]


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    inputs = build_inputs()

    outputs: List[Dict[str, Any]] = []
    for item in inputs:
        rid = item["id"]
        answers = item["answers"]
        res = compute_scores(answers)

        outputs.append(
            {
                "id": rid,
                "scores": res.scores,
                "bands": res.bands,
                "ranking": {
                    "top3": res.ranking.top3,
                    "top5": res.ranking.top5,
                    "bottom3": res.ranking.bottom3,
                },
            }
        )

    INPUTS_PATH.write_text(json.dumps(inputs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUTPUTS_PATH.write_text(json.dumps(outputs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"OK: wrote {INPUTS_PATH}")
    print(f"OK: wrote {OUTPUTS_PATH}")


if __name__ == "__main__":
    main()
