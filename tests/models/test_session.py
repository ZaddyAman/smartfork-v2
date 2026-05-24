"""Tests for session models."""

from pathlib import Path

from smartfork.models.session import QualityTag, RawSessionData, RawTurn, SessionDocument


class TestRawTurn:
    def test_defaults(self) -> None:
        turn = RawTurn(role="user", content="hello")
        assert turn.timestamp == 0
        assert turn.is_tool_call is False
        assert turn.tool_name is None

    def test_role_values(self) -> None:
        for role in ("user", "assistant", "tool", "system"):
            turn = RawTurn(role=role, content="test")
            assert turn.role == role

    def test_tool_call(self) -> None:
        turn = RawTurn(
            role="assistant",
            content="tool result",
            is_tool_call=True,
            tool_name="read_file",
        )
        assert turn.is_tool_call is True
        assert turn.tool_name == "read_file"


class TestRawSessionData:
    def test_duration_minutes(self) -> None:
        data = RawSessionData(
            session_id="s1",
            agent_id="test",
            session_path=Path("/tmp"),
            session_start=60_000,  # 1 minute in ms
            session_end=180_000,  # 3 minutes in ms
        )
        assert data.duration_minutes == 2.0

    def test_duration_zero_when_invalid(self) -> None:
        data = RawSessionData(
            session_id="s1",
            agent_id="test",
            session_path=Path("/tmp"),
            session_start=0,
            session_end=0,
        )
        assert data.duration_minutes == 0.0

    def test_duration_zero_when_start_after_end(self) -> None:
        data = RawSessionData(
            session_id="s1",
            agent_id="test",
            session_path=Path("/tmp"),
            session_start=60000,
            session_end=0,
        )
        assert data.duration_minutes == 0.0

    def test_list_fields_default_empty(self) -> None:
        data = RawSessionData(session_id="s1", agent_id="test", session_path=Path("/tmp"))
        assert data.turns == []
        assert data.files_edited == []
        assert data.files_read == []
        assert data.files_mentioned == []
        assert data.files_user_edited == []
        assert data.final_files == []

    def test_extra_field_defaults_empty_dict(self) -> None:
        data = RawSessionData(session_id="s1", agent_id="test", session_path=Path("/tmp"))
        assert data.extra == {}

    def test_extra_field_can_store_additional_data(self) -> None:
        data = RawSessionData(
            session_id="s1",
            agent_id="test",
            session_path=Path("/tmp"),
            extra={"custom_key": "value"},
        )
        assert data.extra["custom_key"] == "value"

    def test_relationship_links_default_none(self) -> None:
        data = RawSessionData(session_id="s1", agent_id="test", session_path=Path("/tmp"))
        assert data.parent_id is None
        assert data.previous_session_id is None

    def test_relationship_links_can_be_set(self) -> None:
        data = RawSessionData(
            session_id="s1",
            agent_id="test",
            session_path=Path("/tmp"),
            parent_id="parent-1",
            previous_session_id="prev-1",
        )
        assert data.parent_id == "parent-1"
        assert data.previous_session_id == "prev-1"


class TestQualityTag:
    def test_enum_values(self) -> None:
        assert QualityTag.SOLUTION_FOUND == "solution_found"
        assert QualityTag.DEAD_END == "dead_end"
        assert QualityTag.PARTIAL == "partial"
        assert QualityTag.REFERENCE == "reference"
        assert QualityTag.UNKNOWN == "unknown"

    def test_is_string_enum(self) -> None:
        assert isinstance(QualityTag.SOLUTION_FOUND, str)
        assert QualityTag.SOLUTION_FOUND == "solution_found"


class TestSessionDocument:
    def test_defaults(self) -> None:
        doc = SessionDocument(
            session_id="s1",
            agent="kilocode",
            project_name="p1",
            project_root="/tmp",
        )
        assert doc.quality_tag == QualityTag.UNKNOWN
        assert doc.schema_version == 4
        assert doc.tech_tags == []
        assert doc.domains == []
        assert doc.duration_minutes == 0.0
        assert doc.session_pattern == "standard_implementation"

    def test_full_instantiation(self) -> None:
        doc = SessionDocument(
            session_id="abc123",
            agent="claudecode",
            project_name="myproject",
            project_root="/home/user/project",
            session_start=1_700_000_000_000,
            session_end=1_700_000_180_000,
            duration_minutes=3.0,
            model_used="claude-sonnet-4-20250514",
            files_edited=["src/main.py", "src/utils.py"],
            files_read=["README.md"],
            edit_count=2,
            quality_tag=QualityTag.SOLUTION_FOUND,
            tech_tags=["FastAPI", "Pydantic"],
            summary_doc="Built a FastAPI endpoint.",
            indexed_at=1_700_000_200_000,
        )
        assert doc.session_id == "abc123"
        assert doc.quality_tag == QualityTag.SOLUTION_FOUND
        assert doc.tech_tags == ["FastAPI", "Pydantic"]
        assert doc.edit_count == 2

    def test_relationship_links_default_none(self) -> None:
        doc = SessionDocument(
            session_id="s1",
            agent="kilocode",
            project_name="p1",
            project_root="/tmp",
        )
        assert doc.parent_id is None
        assert doc.previous_session_id is None

    def test_relationship_links_can_be_set(self) -> None:
        doc = SessionDocument(
            session_id="s1",
            agent="kilocode",
            project_name="p1",
            project_root="/tmp",
            parent_id="parent-1",
            previous_session_id="prev-1",
        )
        assert doc.parent_id == "parent-1"
        assert doc.previous_session_id == "prev-1"
