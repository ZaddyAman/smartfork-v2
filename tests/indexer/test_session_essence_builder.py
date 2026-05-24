"""Tests for SessionEssenceBuilder."""

from smartfork.indexer.session_essence_builder import SessionEssenceBuilder
from smartfork.models.session import SessionDocument


def _make_session(**kwargs) -> SessionDocument:
    """Create a test SessionDocument with sensible defaults."""
    defaults = {
        "session_id": "test-sess",
        "agent": "kilocode",
        "project_name": "myproject",
        "project_root": "/home/dev",
        "task_raw": "Fix authentication bug",
        "summary_doc": "Resolved by updating middleware.",
        "reasoning_docs": [],
        "tech_tags": [],
    }
    defaults.update(kwargs)
    return SessionDocument(**defaults)


class TestBuildEssence:
    def test_build_essence_includes_all_sections(self) -> None:
        session = _make_session(
            reasoning_docs=[
                "Check token expiry.",
                "Verify timezone settings.",
            ],
            tech_tags=["FastAPI", "PostgreSQL"],
        )
        builder = SessionEssenceBuilder()
        essence = builder.build_essence(session)

        assert "Task: Fix authentication bug" in essence
        assert "Summary: Resolved by updating middleware." in essence
        assert "Reasoning 1: Check token expiry." in essence
        assert "Reasoning 2: Verify timezone settings." in essence
        assert "Technologies: FastAPI, PostgreSQL" in essence

    def test_build_essence_only_top_3_reasoning(self) -> None:
        session = _make_session(
            reasoning_docs=["R1", "R2", "R3", "R4", "R5"],
        )
        builder = SessionEssenceBuilder()
        essence = builder.build_essence(session)

        assert "Reasoning 1: R1" in essence
        assert "Reasoning 2: R2" in essence
        assert "Reasoning 3: R3" in essence
        assert "Reasoning 4:" not in essence
        assert "Reasoning 5:" not in essence

    def test_build_essence_no_reasoning_docs(self) -> None:
        session = _make_session(reasoning_docs=[])
        builder = SessionEssenceBuilder()
        essence = builder.build_essence(session)

        assert "Task:" in essence
        assert "Summary:" in essence
        assert "Reasoning" not in essence

    def test_build_essence_truncates_reasoning(self) -> None:
        long_reasoning = "x" * 2000
        session = _make_session(reasoning_docs=[long_reasoning])
        builder = SessionEssenceBuilder(max_reasoning_length=1500)
        essence = builder.build_essence(session)

        assert "Reasoning 1:" in essence
        expected = "x" * 1500 + "..."
        assert expected in essence

    def test_build_essence_no_tech_tags(self) -> None:
        session = _make_session(tech_tags=[])
        builder = SessionEssenceBuilder()
        essence = builder.build_essence(session)

        assert "Technologies:" not in essence

    def test_build_essence_with_instruction(self) -> None:
        session = _make_session()
        builder = SessionEssenceBuilder()
        essence = builder.build_essence_with_instruction(session)

        assert essence.startswith(
            "Represent this coding session for semantic retrieval: "
        )
        assert "Task:" in essence

    def test_custom_max_reasoning_docs(self) -> None:
        session = _make_session(reasoning_docs=["A", "B", "C"])
        builder = SessionEssenceBuilder(max_reasoning_docs=2)
        essence = builder.build_essence(session)

        assert "Reasoning 1: A" in essence
        assert "Reasoning 2: B" in essence
        assert "Reasoning 3:" not in essence

    def test_custom_max_reasoning_length(self) -> None:
        text = "y" * 500
        session = _make_session(reasoning_docs=[text])
        builder = SessionEssenceBuilder(max_reasoning_length=100)
        essence = builder.build_essence(session)

        expected = "y" * 100 + "..."
        assert expected in essence

    def test_max_total_tokens_truncation(self) -> None:
        long_text = "word " * 300  # ~1500 chars, ~375 tokens
        session = _make_session(
            task_raw=long_text,
            summary_doc=long_text,
            reasoning_docs=[long_text, long_text],
        )
        builder = SessionEssenceBuilder(max_total_tokens=400)
        essence = builder.build_essence(session)

        # 400 tokens * 4 chars/token ≈ 1600 chars
        assert len(essence) <= 1600
