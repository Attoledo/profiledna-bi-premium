from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal, TypedDict


# Resposta por questão (A/B)
AnswerAB = Literal["A", "B"]

# Letras das dimensões (A..T no SSOT)
DimensionLetter = str  # validaremos em runtime via dimensions_20.json


class GabaritoEntry(TypedDict):
    number: int
    letter_if_A: str
    letter_if_B: str


class QuestionEntry(TypedDict):
    number: int
    option_a: str
    option_b: str


class DimensionEntry(TypedDict):
    letter: str
    name: str
    area: str
    competency_rh: str


BandKey = Literal["low", "mid", "high"]


@dataclass(frozen=True)
class DimensionScore:
    letter: DimensionLetter
    score: int  # 0..10
    band_key: BandKey  # low/mid/high


@dataclass(frozen=True)
class TopBottom:
    top3: List[DimensionLetter]
    top5: List[DimensionLetter]
    bottom3: List[DimensionLetter]


@dataclass(frozen=True)
class EngineResult:
    """
    Resultado puro do motor de scoring (sem DB/HTTP).
    """
    # scores por letra (20 dimensões)
    scores: Dict[DimensionLetter, int]

    # faixa por letra
    bands: Dict[DimensionLetter, BandKey]

    # top/bottom (letras)
    ranking: TopBottom
