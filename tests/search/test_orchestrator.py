"""Tests for the rewritten SearchOrchestrator (US-025)."""

from unittest.mock import MagicMock

import pytest

from smartfork.models.query import QueryInterpretation
from smartfork.models.search import ResultCard
from smartfork.search.orchestrator import SearchOrchestrator


def _make_qi(
    original: str = "test query",
    expanded: str = "test query OR testing",
    needs_deep: bool = False,
) -> QueryInterpretation:
    return QueryInterpretation(
        original_query=original,
        keywords=["test", "query"],
        synonyms=["testing"],
        expanded_query=expanded,
        intent="vague_memory",
        needs_deep_mode=needs_deep,
    )


def _make_card(session_id: str, rank: int = 1) -> ResultCard:
    return ResultCard(
        rank=rank,
        session_id=session_id,
        title=session_id,
        project_name="test_project",
        match_score=0.9,
        fork_command=f"smartfork fork {session_id}",
    )


@pytest.fixture
def orchestrator() -> SearchOrchestrator:
    return SearchOrchestrator(
        embedder=MagicMock(),
        metadata_store=MagicMock(),
        llm=MagicMock(),
    )


# ── Default mode tests ─────────────────────────────────────────────────────


class TestDefaultMode:
    def test_interpreter_then_engine(self, orchestrator: SearchOrchestrator) -> None:
        qi = _make_qi()
        orchestrator.interpreter = MagicMock()  # type: ignore[assignment]
        orchestrator.interpreter.interpret.return_value = qi  # type: ignore[union-attr]
        orchestrator.engine = MagicMock()  # type: ignore[assignment]
        orchestrator.engine.search.return_value = [  # type: ignore[union-attr]
            _make_card("s1"),
            _make_card("s2", rank=2),
        ]

        result = orchestrator.search("test query", top_k=2)

        assert len(result) == 2
        assert result[0].session_id == "s1"
        assert result[1].session_id == "s2"
        orchestrator.interpreter.interpret.assert_called_once_with("test query", deep_mode=False)  # type: ignore[union-attr]
        orchestrator.engine.search.assert_called_once_with(  # type: ignore[union-attr]
            qi.expanded_query, 2, None, None
        )

    def test_returns_result_cards(self, orchestrator: SearchOrchestrator) -> None:
        qi = _make_qi()
        orchestrator.interpreter = MagicMock()  # type: ignore[assignment]
        orchestrator.interpreter.interpret.return_value = qi  # type: ignore[union-attr]
        orchestrator.engine = MagicMock()  # type: ignore[assignment]
        orchestrator.engine.search.return_value = [_make_card("s1")]  # type: ignore[union-attr]

        result = orchestrator.search("test query")

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], ResultCard)

    def test_slices_to_top_k(self, orchestrator: SearchOrchestrator) -> None:
        qi = _make_qi()
        orchestrator.interpreter = MagicMock()  # type: ignore[assignment]
        orchestrator.interpreter.interpret.return_value = qi  # type: ignore[union-attr]
        orchestrator.engine = MagicMock()  # type: ignore[assignment]
        orchestrator.engine.search.return_value = [  # type: ignore[union-attr]
            _make_card(f"s{i}", rank=i) for i in range(1, 11)
        ]

        result = orchestrator.search("test query", top_k=3)

        assert len(result) == 3

    def test_filter_passthrough(self, orchestrator: SearchOrchestrator) -> None:
        qi = _make_qi()
        orchestrator.interpreter = MagicMock()  # type: ignore[assignment]
        orchestrator.interpreter.interpret.return_value = qi  # type: ignore[union-attr]
        orchestrator.engine = MagicMock()  # type: ignore[assignment]
        orchestrator.engine.search.return_value = [_make_card("s1")]  # type: ignore[union-attr]

        orchestrator.search(
            "test query",
            top_k=5,
            project_filter="alpha",
            quality_filter="solution_found",
        )

        orchestrator.engine.search.assert_called_once_with(  # type: ignore[union-attr]
            qi.expanded_query, 5, "alpha", "solution_found"
        )


# ── Fast mode tests ──────────────────────────────────────────────────────────


class TestFastMode:
    def test_zero_llm_calls(self) -> None:
        engine = MagicMock()
        engine.search.return_value = [_make_card("s1")]
        orch = SearchOrchestrator(
            embedder=MagicMock(),
            metadata_store=MagicMock(),
            llm=MagicMock(),
            use_fast=True,
        )
        orch.engine = engine  # type: ignore[assignment]

        result = orch.search("test query", top_k=5)

        assert len(result) == 1
        engine.search.assert_called_once_with("test query", 5, None, None)

    def test_interpreter_not_called(self) -> None:
        engine = MagicMock()
        engine.search.return_value = [_make_card("s1")]
        interpreter = MagicMock()
        orch = SearchOrchestrator(
            embedder=MagicMock(),
            metadata_store=MagicMock(),
            llm=MagicMock(),
            use_fast=True,
        )
        orch.engine = engine  # type: ignore[assignment]
        orch.interpreter = interpreter  # type: ignore[assignment]

        orch.search("test query")

        interpreter.interpret.assert_not_called()

    def test_no_llm_required(self) -> None:
        engine = MagicMock()
        engine.search.return_value = [_make_card("s1")]
        orch = SearchOrchestrator(
            embedder=None,
            metadata_store=None,
            llm=None,
            use_fast=True,
        )
        orch.engine = engine  # type: ignore[assignment]

        result = orch.search("test query")

        assert len(result) == 1
        assert orch.interpreter is None


# ── Deep mode tests ──────────────────────────────────────────────────────────


class TestDeepMode:
    def test_deep_flag_triggers_deep_path(self, orchestrator: SearchOrchestrator) -> None:
        qi = _make_qi(needs_deep=False)
        orchestrator.use_deep = True
        orchestrator.interpreter = MagicMock()  # type: ignore[assignment]
        orchestrator.interpreter.interpret.return_value = qi  # type: ignore[union-attr]
        orchestrator.engine = MagicMock()  # type: ignore[assignment]
        orchestrator.engine.search.return_value = [_make_card("s1")]  # type: ignore[union-attr]

        result = orchestrator.search("test query")

        assert len(result) == 1
        # Deep mode is a placeholder; cards should still be returned.
        assert result[0].relevance_explanation == "Deep mode: multi-session analysis requested."

    def test_qi_needs_deep_triggers_deep_path(self, orchestrator: SearchOrchestrator) -> None:
        qi = _make_qi(needs_deep=True)
        orchestrator.interpreter = MagicMock()  # type: ignore[assignment]
        orchestrator.interpreter.interpret.return_value = qi  # type: ignore[union-attr]
        orchestrator.engine = MagicMock()  # type: ignore[assignment]
        orchestrator.engine.search.return_value = [_make_card("s1")]  # type: ignore[union-attr]

        result = orchestrator.search("test query")

        assert len(result) == 1
        assert result[0].relevance_explanation == "Deep mode: multi-session analysis requested."


# ── Failure handling tests ───────────────────────────────────────────────────


class TestInterpreterFallback:
    def test_exception_uses_deterministic_fallback(self, orchestrator: SearchOrchestrator) -> None:
        orchestrator.interpreter = MagicMock()  # type: ignore[assignment]
        orchestrator.interpreter.interpret.side_effect = RuntimeError("LLM down")  # type: ignore[union-attr]
        orchestrator.engine = MagicMock()  # type: ignore[assignment]
        orchestrator.engine.search.return_value = [_make_card("s1")]  # type: ignore[union-attr]

        result = orchestrator.search("original query")

        assert len(result) == 1
        # Fallback deterministic interpreter extracts keywords and builds
        # expanded_query "original OR query".
        call_args = orchestrator.engine.search.call_args  # type: ignore[union-attr]
        assert "original" in call_args.args[0]
        assert "query" in call_args.args[0]

    def test_no_interpreter_uses_deterministic_fallback(
        self, orchestrator: SearchOrchestrator,
    ) -> None:
        orchestrator.interpreter = None
        orchestrator.engine = MagicMock()  # type: ignore[assignment]
        orchestrator.engine.search.return_value = [_make_card("s1")]  # type: ignore[union-attr]

        result = orchestrator.search("original query")

        assert len(result) == 1
        call_args = orchestrator.engine.search.call_args  # type: ignore[union-attr]
        assert "original" in call_args.args[0]
        assert "query" in call_args.args[0]


class TestEngineFallback:
    def test_exception_returns_empty(self, orchestrator: SearchOrchestrator) -> None:
        orchestrator.interpreter = MagicMock()  # type: ignore[assignment]
        orchestrator.interpreter.interpret.return_value = _make_qi()  # type: ignore[union-attr]
        orchestrator.engine = MagicMock()  # type: ignore[assignment]
        orchestrator.engine.search.side_effect = RuntimeError("DB error")  # type: ignore[union-attr]

        result = orchestrator.search("test query")

        assert result == []


class TestDeepSynthesisFallback:
    def test_exception_returns_results_without_narrative(
        self, orchestrator: SearchOrchestrator,
    ) -> None:
        qi = _make_qi(needs_deep=True)
        orchestrator.interpreter = MagicMock()  # type: ignore[assignment]
        orchestrator.interpreter.interpret.return_value = qi  # type: ignore[union-attr]
        orchestrator.engine = MagicMock()  # type: ignore[assignment]
        orchestrator.engine.search.return_value = [_make_card("s1")]  # type: ignore[union-attr]
        orchestrator._deep_synthesis = MagicMock(side_effect=RuntimeError("synth failed"))  # type: ignore[assignment]

        result = orchestrator.search("test query")

        assert len(result) == 1
        assert result[0].relevance_explanation == ""


class TestEmptyResults:
    def test_empty_candidates_returns_empty_list(self, orchestrator: SearchOrchestrator) -> None:
        orchestrator.interpreter = MagicMock()  # type: ignore[assignment]
        orchestrator.interpreter.interpret.return_value = _make_qi()  # type: ignore[union-attr]
        orchestrator.engine = MagicMock()  # type: ignore[assignment]
        orchestrator.engine.search.return_value = []  # type: ignore[union-attr]

        result = orchestrator.search("test query")

        assert result == []
        assert orchestrator.last_empty_reasoning != ""


# ── Progress output tests ──────────────────────────────────────────────────


class TestProgressOutput:
    def test_default_mode_prints_phases(
        self, orchestrator: SearchOrchestrator, capsys: pytest.CaptureFixture
    ) -> None:
        orchestrator.interpreter = MagicMock()  # type: ignore[assignment]
        orchestrator.interpreter.interpret.return_value = _make_qi()  # type: ignore[union-attr]
        orchestrator.engine = MagicMock()  # type: ignore[assignment]
        orchestrator.engine.search.return_value = [  # type: ignore[union-attr]
            _make_card(f"s{i}", rank=i) for i in range(1, 4)
        ]

        orchestrator.search("test query", top_k=2)

        captured = capsys.readouterr()
        assert "Interpreting query..." in captured.out
        assert "Searching..." in captured.out
        assert "Synthesizing" not in captured.out  # deep mode not triggered

    def test_fast_mode_prints_fast_search(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        engine = MagicMock()
        engine.search.return_value = [_make_card("s1")]
        orch = SearchOrchestrator(
            embedder=MagicMock(),
            metadata_store=MagicMock(),
            llm=MagicMock(),
            use_fast=True,
        )
        orch.engine = engine  # type: ignore[assignment]

        orch.search("test query")

        captured = capsys.readouterr()
        assert "Fast search..." in captured.out
        assert "Interpreting query..." not in captured.out

    def test_deep_mode_prints_synthesis(
        self, orchestrator: SearchOrchestrator, capsys: pytest.CaptureFixture
    ) -> None:
        qi = _make_qi(needs_deep=True)
        orchestrator.interpreter = MagicMock()  # type: ignore[assignment]
        orchestrator.interpreter.interpret.return_value = qi  # type: ignore[union-attr]
        orchestrator.engine = MagicMock()  # type: ignore[assignment]
        orchestrator.engine.search.return_value = [  # type: ignore[union-attr]
            _make_card("s1"),
        ]

        orchestrator.search("test query", top_k=1)

        captured = capsys.readouterr()
        assert "Interpreting query..." in captured.out
        assert "Searching..." in captured.out
        assert "Deep synthesis..." in captured.out
