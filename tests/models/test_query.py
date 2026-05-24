"""Tests for query interpretation model."""

import pytest

from smartfork.models.query import QueryInterpretation


class TestQueryInterpretation:
    def test_basic_creation(self) -> None:
        qi = QueryInterpretation(
            original_query="what happened with auth last week",
            keywords=["auth"],
            synonyms=["authentication", "login"],
            expanded_query="auth OR authentication OR login",
            temporal_filter={"type": "relative", "value": "last_week"},
            intent="temporal_lookup",
            project_hint="myproject",
            multi_session_confidence=0.92,
            needs_deep_mode=True,
            quality_boost=["solution_found"],
        )
        assert qi.original_query == "what happened with auth last week"
        assert qi.keywords == ["auth"]
        assert qi.synonyms == ["authentication", "login"]
        assert qi.expanded_query == "auth OR authentication OR login"
        assert qi.temporal_filter == {"type": "relative", "value": "last_week"}
        assert qi.intent == "temporal_lookup"
        assert qi.project_hint == "myproject"
        assert qi.multi_session_confidence == 0.92
        assert qi.needs_deep_mode is True
        assert qi.quality_boost == ["solution_found"]

    def test_default_values(self) -> None:
        qi = QueryInterpretation(original_query="jwt bug")
        assert qi.keywords == []
        assert qi.synonyms == []
        assert qi.expanded_query == ""
        assert qi.temporal_filter is None
        assert qi.intent == "unknown"
        assert qi.project_hint is None
        assert qi.quality_boost == []
        assert qi.multi_session_confidence == 0.0
        assert qi.needs_deep_mode is False

    def test_multi_session_confidence_defaults_to_zero(self) -> None:
        qi = QueryInterpretation(original_query="test")
        assert qi.multi_session_confidence == 0.0

    def test_needs_deep_mode_defaults_to_false(self) -> None:
        qi = QueryInterpretation(original_query="test")
        assert qi.needs_deep_mode is False

    def test_temporal_filter_can_be_none(self) -> None:
        qi = QueryInterpretation(
            original_query="test",
            temporal_filter=None,
        )
        assert qi.temporal_filter is None

    def test_intent_values(self) -> None:
        valid_intents = [
            "solution_hunting",
            "error_recall",
            "continuation",
            "temporal_lookup",
            "decision_hunting",
            "implementation_lookup",
            "vague_memory",
            "unknown",
        ]
        for intent in valid_intents:
            qi = QueryInterpretation(original_query="test", intent=intent)
            assert qi.intent == intent

    def test_multi_session_confidence_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="multi_session_confidence must be between"):
            QueryInterpretation(
                original_query="test",
                multi_session_confidence=1.5,
            )
