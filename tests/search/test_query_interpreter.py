"""Tests for QueryInterpreter."""

from unittest.mock import MagicMock

import pytest

from smartfork.models.query import QueryInterpretation
from smartfork.search.query_interpreter import SYNONYM_MAP, QueryInterpreter


class TestQueryInterpreter:
    def test_interpret_with_llm_structured(self, mock_llm: MagicMock) -> None:
        mock_llm.complete_structured.return_value = QueryInterpretation(
            original_query="how did I fix the auth bug",
            keywords=["auth", "bug"],
            synonyms=["authentication", "error"],
            intent="solution_hunting",
            multi_session_confidence=0.60,
            project_hint=None,
            quality_boost=["solution_found"],
        )
        interpreter = QueryInterpreter(llm=mock_llm)
        result = interpreter.interpret("how did I fix the auth bug")
        assert isinstance(result, QueryInterpretation)
        assert result.original_query == "how did I fix the auth bug"
        assert result.keywords == ["auth", "bug"]
        assert result.synonyms == ["authentication", "error"]
        assert result.intent == "solution_hunting"
        assert result.multi_session_confidence == 0.60
        assert result.needs_deep_mode is False
        assert mock_llm.complete_structured.called

    def test_interpret_with_llm_fallback(self, mock_llm: MagicMock) -> None:
        mock_llm.complete_structured.side_effect = RuntimeError("LLM unavailable")
        interpreter = QueryInterpreter(llm=mock_llm)
        result = interpreter.interpret("fix the jwt bug")
        assert isinstance(result, QueryInterpretation)
        assert "jwt" in result.keywords or "bug" in result.keywords
        assert mock_llm.complete_structured.called

    def test_interpret_deterministic_extracts_keywords(self) -> None:
        interpreter = QueryInterpreter(llm=None)
        result = interpreter.interpret("how to implement database migration")
        assert "database" in result.keywords or "migration" in result.keywords

    def test_deterministic_expands_synonyms(self) -> None:
        interpreter = QueryInterpreter(llm=None)
        result = interpreter.interpret("auth configuration")
        assert "authentication" in result.synonyms
        assert "login" in result.synonyms
        assert "oauth" in result.synonyms
        assert "jwt" in result.synonyms

    def test_deterministic_detects_continuation_intent(self) -> None:
        interpreter = QueryInterpreter(llm=None)
        result = interpreter.interpret("continue my work")
        assert result.intent == "continuation"

    def test_deterministic_detects_error_intent(self) -> None:
        interpreter = QueryInterpreter(llm=None)
        result = interpreter.interpret("fix the jwt bug")
        assert result.intent == "error_recall"

    def test_deterministic_detects_temporal_intent(self) -> None:
        interpreter = QueryInterpreter(llm=None)
        result = interpreter.interpret("last week auth changes")
        assert result.intent == "temporal_lookup"

    def test_compute_confidence_temporal(self) -> None:
        interpreter = QueryInterpreter(llm=None)
        assert interpreter._compute_confidence("what happened last week") == 0.80

    def test_compute_confidence_continuation(self) -> None:
        interpreter = QueryInterpreter(llm=None)
        assert interpreter._compute_confidence("continue my work") == 0.85

    def test_compute_confidence_specific_keywords(self) -> None:
        interpreter = QueryInterpreter(llm=None)
        assert interpreter._compute_confidence("fix the jwt bug") == 0.30

    def test_needs_deep_mode_true(self) -> None:
        interpreter = QueryInterpreter(llm=None)
        result = interpreter.interpret("continue my work")
        assert result.needs_deep_mode is True

    def test_needs_deep_mode_false(self) -> None:
        interpreter = QueryInterpreter(llm=None)
        result = interpreter.interpret("fix the jwt bug")
        assert result.needs_deep_mode is False

    def test_expanded_query_format(self) -> None:
        interpreter = QueryInterpreter(llm=None)
        result = interpreter.interpret("auth bug")
        assert " OR " in result.expanded_query
        assert "auth" in result.expanded_query
        assert "authentication" in result.expanded_query
        assert "bug" in result.expanded_query
        assert "error" in result.expanded_query

    def test_deep_mode_flag_overrides_low_confidence(self) -> None:
        interpreter = QueryInterpreter(llm=None)
        result = interpreter.interpret("fix the jwt bug", deep_mode=True)
        assert result.needs_deep_mode is True

    def test_synonym_map_is_dict(self) -> None:
        assert isinstance(SYNONYM_MAP, dict)
        assert "auth" in SYNONYM_MAP
        assert "authentication" in SYNONYM_MAP["auth"]

    def test_llm_dict_result_parsing(self, mock_llm: MagicMock) -> None:
        mock_llm.complete_structured.return_value = {
            "keywords": ["auth", "bug"],
            "synonyms": ["authentication", "error"],
            "intent": "error_recall",
            "multi_session_confidence": 0.30,
            "project_hint": "my_project",
        }
        interpreter = QueryInterpreter(llm=mock_llm)
        result = interpreter.interpret("auth bug in my_project")
        assert result.keywords == ["auth", "bug"]
        assert result.synonyms == ["authentication", "error"]
        assert result.intent == "error_recall"
        assert result.project_hint == "my_project"

    def test_llm_text_result_parsing(self) -> None:
        mock_llm = MagicMock(spec=["complete"])
        mock_llm.complete.return_value = (
            '```json\n{"keywords": ["auth"], "intent": "error_recall", '
            '"multi_session_confidence": 0.3}\n```'
        )
        interpreter = QueryInterpreter(llm=mock_llm)
        result = interpreter.interpret("auth bug")
        assert result.keywords == ["auth"]
        assert result.intent == "error_recall"
        assert result.multi_session_confidence == 0.3

    def test_llm_text_result_invalid_json_fallback(self) -> None:
        mock_llm = MagicMock(spec=["complete"])
        mock_llm.complete.return_value = "not valid json at all"
        interpreter = QueryInterpreter(llm=mock_llm)
        result = interpreter.interpret("auth bug")
        # Should fall back to deterministic
        assert "auth" in result.keywords
        assert result.intent == "error_recall"
