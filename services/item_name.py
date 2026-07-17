from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Iterable

from services.items import get_item_names, normalize_item_name

_EDGE_NOISE = re.compile(r"^[^A-Za-z0-9\[]+|[^A-Za-z0-9%\])}+'-]+$")
_LEADING_TOKEN = re.compile(r"^(?:[#@€©®§£*=|~^]+|[A-Za-z0-9]{1,2}[)\]}>]+)\s+")
_TRAILING_TOKEN = re.compile(r"\s+(?:[#@€©®§£*=|~^]+|[A-Za-z0-9]{1,2}[)\]}>]+)$")


def clean_ocr_item_name(value: str) -> str:
    """Remove icon-shaped OCR garbage from either edge of an item title."""
    value = " ".join(str(value).strip().split())
    if not value:
        return ""

    previous = None
    while previous != value:
        previous = value
        value = _EDGE_NOISE.sub("", value).strip()
        value = _LEADING_TOKEN.sub("", value).strip()
        value = _TRAILING_TOKEN.sub("", value).strip()

    return " ".join(value.split())


def score_item_candidate(query: str, candidate: str) -> float:
    q = normalize_item_name(clean_ocr_item_name(query))
    c = normalize_item_name(candidate)
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0

    sequence = SequenceMatcher(None, q, c).ratio()
    q_tokens = q.split()
    c_tokens = c.split()
    q_set = set(q_tokens)
    c_set = set(c_tokens)
    overlap = len(q_set & c_set) / max(1, len(q_set | c_set))
    containment = 1.0 if q in c or c in q else 0.0

    # Give discriminating short tokens (DEX/LUK/INT/STR and percentages)
    # enough influence that "DEX" does not drift to "Dark".
    exact_token_ratio = sum(token in c_set for token in q_tokens) / max(1, len(q_tokens))
    return 0.50 * sequence + 0.25 * overlap + 0.20 * exact_token_ratio + 0.05 * containment


def resolve_local_item_name(value: str, names: Iterable[str] | None = None, *, minimum_score: float = 0.72) -> str:
    cleaned = clean_ocr_item_name(value)
    catalog = list(names) if names is not None else get_item_names()
    if not cleaned or not catalog:
        return cleaned

    scored = sorted(
        ((score_item_candidate(cleaned, name), name) for name in catalog),
        key=lambda pair: (-pair[0], pair[1].casefold()),
    )
    best_score, best_name = scored[0]
    return best_name if best_score >= minimum_score else cleaned
