from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _repo_root() -> Path:
    # backend/ssot/loader.py -> backend -> repo root
    return Path(__file__).resolve().parents[2]


def _abs_path(rel_or_abs: str) -> Path:
    p = Path(rel_or_abs)
    if p.is_absolute():
        return p
    return _repo_root() / p


@lru_cache(maxsize=256)
def load_json(path: str) -> Any:
    """
    Carrega JSON de forma determinística e cacheada.
    `path` pode ser absoluto ou relativo ao repo root.
    """
    p = _abs_path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    return data


def load_many_json(paths: List[str]) -> Dict[str, Any]:
    """
    Carrega vários JSONs e retorna dict path->data.
    """
    out: Dict[str, Any] = {}
    for pp in paths:
        out[pp] = load_json(pp)
    return out


def file_exists(path: str) -> bool:
    return _abs_path(path).exists()


def read_text(path: str) -> str:
    return _abs_path(path).read_text(encoding="utf-8")


def abs_path(path: str) -> str:
    return str(_abs_path(path))


def repo_root_str() -> str:
    return str(_repo_root())
