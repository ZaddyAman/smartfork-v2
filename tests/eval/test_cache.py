"""Tests for eval cache."""

from pathlib import Path

import pytest

from smartfork.eval.cache import EvalCache


class TestEvalCache:
    @pytest.fixture
    def tmp_cache(self, tmp_path: Path) -> EvalCache:
        return EvalCache(tmp_path / "eval_cache.json")

    def test_initial_state(self, tmp_cache: EvalCache) -> None:
        assert tmp_cache.get_sampled_sessions() is None
        assert tmp_cache.get_generated_queries("s1") is None
        assert tmp_cache.get_judgment("q", "s1", "fast") is None

    def test_sample_roundtrip(self, tmp_cache: EvalCache) -> None:
        tmp_cache.set_sampled_sessions(["a", "b", "c"])
        assert tmp_cache.get_sampled_sessions() == ["a", "b", "c"]

    def test_query_cache_valid(self, tmp_cache: EvalCache) -> None:
        tmp_cache.set_generated_queries("s1", [{"query": "foo", "query_type": "specific"}], 1000)
        assert tmp_cache.is_query_cache_valid("s1", 1000) is True
        assert tmp_cache.is_query_cache_valid("s1", 2000) is False

    def test_judgment_roundtrip(self, tmp_cache: EvalCache) -> None:
        tmp_cache.set_judgment("q1", "s1", "fast", 3, "direct hit")
        cached = tmp_cache.get_judgment("q1", "s1", "fast")
        assert cached is not None
        assert cached["score"] == 3
        assert cached["reason"] == "direct hit"

    def test_clear(self, tmp_cache: EvalCache) -> None:
        tmp_cache.set_sampled_sessions(["a"])
        tmp_cache.set_judgment("q", "s", "fast", 1, "r")
        tmp_cache.clear()
        assert tmp_cache.get_sampled_sessions() is None
        assert tmp_cache.get_judgment("q", "s", "fast") is None

    def test_persistence(self, tmp_path: Path) -> None:
        path = tmp_path / "eval_cache.json"
        c1 = EvalCache(path)
        c1.set_judgment("q1", "s1", "default", 2, "partial")

        c2 = EvalCache(path)
        cached = c2.get_judgment("q1", "s1", "default")
        assert cached is not None
        assert cached["score"] == 2
