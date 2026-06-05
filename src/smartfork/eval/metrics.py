"""IR metrics for search evaluation.

Precision@k, nDCG@k, MRR, MAP.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def compute_precision_at_k(relevance_scores: Sequence[float], k: int) -> float:
    """Compute Precision@k.

    Fraction of top-k results that are relevant (score >= 2).

    Args:
        relevance_scores: Ordered list of relevance scores for top-k results.
        k: Cutoff rank.

    Returns:
        Precision@k value in [0.0, 1.0].
    """
    if not relevance_scores or k <= 0:
        return 0.0
    top_k = relevance_scores[:k]
    relevant = sum(1.0 for s in top_k if s >= 2.0)
    return relevant / len(top_k)


def compute_ndcg(relevance_scores: Sequence[float], k: int) -> float:
    """Compute nDCG@k (normalized Discounted Cumulative Gain).

    Uses standard logarithmic discount: DCG = Σ (2^rel_i - 1) / log2(i + 2).

    Args:
        relevance_scores: Ordered relevance scores.
        k: Cutoff rank.

    Returns:
        nDCG@k in [0.0, 1.0].
    """
    if not relevance_scores or k <= 0:
        return 0.0

    top_k = relevance_scores[:k]

    def dcg(scores: Sequence[float]) -> float:
        return sum(
            (2 ** score - 1) / math.log2(i + 2)
            for i, score in enumerate(scores)
        )

    ideal = sorted(relevance_scores, reverse=True)[:k]
    ideal_dcg = dcg(ideal)
    actual_dcg = dcg(top_k)

    if ideal_dcg == 0:
        return 0.0
    return actual_dcg / ideal_dcg


def compute_mrr(relevance_scores: Sequence[float]) -> float:
    """Compute Mean Reciprocal Rank.

    Reciprocal rank of the first relevant result (score >= 2).

    Args:
        relevance_scores: Ordered relevance scores.

    Returns:
        MRR in [0.0, 1.0]. 0.0 if no relevant result found.
    """
    for i, score in enumerate(relevance_scores):
        if score >= 2.0:
            return 1.0 / (i + 1)
    return 0.0


def compute_map(query_relevances: Sequence[Sequence[float]]) -> float:
    """Compute Mean Average Precision.

    MAP = average of per-query Average Precision values.
    AP = average of precision values at each rank where a relevant result appears.

    Args:
        query_relevances: List of relevance score lists, one per query.

    Returns:
        MAP in [0.0, 1.0].
    """
    if not query_relevances:
        return 0.0

    aps: list[float] = []
    for scores in query_relevances:
        if not scores:
            continue
        precisions_at_rel: list[float] = []
        relevant_so_far = 0
        for i, score in enumerate(scores):
            if score >= 2.0:
                relevant_so_far += 1
                precisions_at_rel.append(relevant_so_far / (i + 1))
        if precisions_at_rel:
            aps.append(sum(precisions_at_rel) / len(precisions_at_rel))

    if not aps:
        return 0.0
    return sum(aps) / len(aps)
