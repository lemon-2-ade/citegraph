"""Ranking and result-set metrics. Pure functions, no I/O."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import Any


def recall_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    """Fraction of the relevant items found in the top k (1.0 when nothing is relevant)."""
    if not relevant:
        return 1.0
    return len(set(ranked[:k]) & relevant) / len(relevant)


def hit_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    """1.0 if any relevant item appears in the top k."""
    return 1.0 if set(ranked[:k]) & relevant else 0.0


def reciprocal_rank(ranked: Sequence[str], relevant: set[str]) -> float:
    for position, item in enumerate(ranked, start=1):
        if item in relevant:
            return 1.0 / position
    return 0.0


def ndcg_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    """Binary-relevance nDCG: discounts relevant items found lower in the list."""
    if not relevant:
        return 1.0
    dcg = sum(
        1.0 / math.log2(i + 1) for i, item in enumerate(ranked[:k], start=1) if item in relevant
    )
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(relevant), k) + 1))
    return dcg / ideal


def mean(values: Iterable[float]) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0


def _cell(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return repr(value)


def rows_as_multiset(rows: Sequence[Mapping[str, Any]]) -> Counter[tuple[str, ...]]:
    """Rows as a multiset of value tuples, ignoring column names and row/column order."""
    return Counter(tuple(sorted(_cell(v) for v in row.values())) for row in rows)


def same_result(gold: Sequence[Mapping[str, Any]], got: Sequence[Mapping[str, Any]]) -> bool:
    return rows_as_multiset(gold) == rows_as_multiset(got)
