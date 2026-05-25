"""Tests for eval metrics."""

import pytest

from smartfork.eval.metrics import compute_map, compute_mrr, compute_ndcg, compute_precision_at_k


class TestPrecisionAtK:
    def test_all_relevant(self) -> None:
        scores = [3.0, 3.0, 3.0, 3.0, 3.0]
        assert compute_precision_at_k(scores, 5) == 1.0

    def test_none_relevant(self) -> None:
        scores = [0.0, 1.0, 0.0, 1.0, 0.0]
        assert compute_precision_at_k(scores, 5) == 0.0

    def test_half_relevant(self) -> None:
        scores = [3.0, 0.0, 2.0, 1.0, 0.0]
        assert compute_precision_at_k(scores, 5) == 0.4

    def test_k_less_than_length(self) -> None:
        scores = [3.0, 3.0, 0.0, 0.0, 0.0]
        assert compute_precision_at_k(scores, 2) == 1.0

    def test_empty(self) -> None:
        assert compute_precision_at_k([], 5) == 0.0


class TestNDCG:
    def test_perfect_ranking(self) -> None:
        scores = [3.0, 2.0, 1.0, 0.0, 0.0]
        assert compute_ndcg(scores, 5) == pytest.approx(1.0, 0.01)

    def test_reversed_ranking(self) -> None:
        scores = [0.0, 0.0, 1.0, 2.0, 3.0]
        ndcg = compute_ndcg(scores, 5)
        assert ndcg < 0.5

    def test_all_same(self) -> None:
        scores = [2.0, 2.0, 2.0]
        assert compute_ndcg(scores, 3) == pytest.approx(1.0, 0.01)

    def test_empty(self) -> None:
        assert compute_ndcg([], 5) == 0.0


class TestMRR:
    def test_first_relevant(self) -> None:
        assert compute_mrr([3.0, 0.0, 0.0]) == 1.0

    def test_third_relevant(self) -> None:
        assert compute_mrr([1.0, 0.0, 2.0]) == 1.0 / 3.0

    def test_no_relevant(self) -> None:
        assert compute_mrr([0.0, 1.0, 0.0]) == 0.0

    def test_empty(self) -> None:
        assert compute_mrr([]) == 0.0


class TestMAP:
    def test_single_query(self) -> None:
        # 2 relevant out of 5: positions 1 and 3
        # AP = (1/1 + 2/3) / 2 = (1 + 0.667) / 2 = 0.833
        scores = [3.0, 0.0, 2.0, 0.0, 1.0]
        assert compute_map([scores]) == pytest.approx(0.833, 0.01)

    def test_multiple_queries(self) -> None:
        q1 = [3.0, 0.0, 2.0, 0.0, 0.0]
        q2 = [0.0, 3.0, 0.0, 0.0, 0.0]
        # AP(q1) = (1/1 + 2/3) / 2 = 0.833
        # AP(q2) = 1/2 = 0.5
        # MAP = (0.833 + 0.5) / 2 = 0.667
        assert compute_map([q1, q2]) == pytest.approx(0.667, 0.01)

    def test_no_relevant_anywhere(self) -> None:
        assert compute_map([[0.0, 0.0], [1.0, 0.0]]) == 0.0

    def test_empty(self) -> None:
        assert compute_map([]) == 0.0
