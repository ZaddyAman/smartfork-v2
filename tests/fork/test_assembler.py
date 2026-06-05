"""Tests for fork assembly system."""

from pathlib import Path

from smartfork.fork.assembler import ArtifactDetector, ForkAssembler, ForkExporter
from smartfork.models.fork import ForkIntent
from smartfork.models.session import QualityTag, SessionDocument


def _make_session(**kwargs) -> SessionDocument:
    defaults = {
        "session_id": "test-sess",
        "agent": "kilocode",
        "project_name": "myproject",
        "project_root": "/tmp",
        "task_raw": "Fix authentication bug in login",
        "summary_doc": "Fixed JWT validation causing 401 errors.",
        "reasoning_docs": [
            "The JWT token was expired due to timezone mismatch.",
            "Fixed by using UTC timestamps in token generation.",
        ],
        "files_edited": ["src/auth.py", "src/jwt.py"],
        "files_read": ["src/spec.md", "config.toml"],
        "languages": ["python"],
        "domains": ["auth", "backend"],
        "quality_tag": QualityTag.SOLUTION_FOUND,
        "edit_count": 3,
        "final_files": ["src/auth.py"],
        "duration_minutes": 15.0,
        "session_start": 1700000000000,
    }
    defaults.update(kwargs)
    return SessionDocument(**defaults)


class TestArtifactDetector:
    def test_detects_spec_files(self) -> None:
        artifacts = ArtifactDetector.detect(["src/spec.md", "src/auth.py"], "task")
        spec_artifacts = [a for a in artifacts if a["type"] == "spec"]
        assert len(spec_artifacts) >= 1

    def test_detects_config_files(self) -> None:
        artifacts = ArtifactDetector.detect(["config.toml", "src/main.py"], "task")
        config_artifacts = [a for a in artifacts if a["type"] == "config"]
        assert len(config_artifacts) >= 1


class TestForkAssembler:
    def test_assemble_continue_intent(self) -> None:
        assembler = ForkAssembler()
        session = _make_session()
        result = assembler.assemble(session, ForkIntent.CONTINUE)
        assert "Handoff:" in result
        assert "Artifacts to Reference" in result
        assert "What Was Happening" in result
        assert "Next Steps" in result

    def test_assemble_debug_intent(self) -> None:
        assembler = ForkAssembler()
        session = _make_session()
        result = assembler.assemble(session, ForkIntent.DEBUG)
        assert "Error Encountered" in result
        assert "Root Cause" in result

    def test_assemble_synthesize_intent(self) -> None:
        assembler = ForkAssembler()
        session = _make_session()
        result = assembler.assemble(session, ForkIntent.SYNTHESIZE)
        assert "Overview" in result
        assert "Timeline" in result

    def test_assemble_reference_intent(self) -> None:
        assembler = ForkAssembler()
        session = _make_session()
        result = assembler.assemble(session, ForkIntent.REFERENCE)
        assert "Skills Suggested" in result

    def test_assemble_with_supersession_warning(self) -> None:
        assembler = ForkAssembler()
        session = _make_session()
        result = assembler.assemble(
            session, ForkIntent.CONTINUE,
            supersession_warning="This session was superseded by abc123"
        )
        assert "abc123" in result


class TestForkExporter:
    def test_save_to_file(self, tmp_path: Path) -> None:
        content = "# Test Handoff"
        path = ForkExporter.save_to_file(
            content, "sess-1", ForkIntent.CONTINUE, tmp_path
        )
        assert path.exists()
        assert path.read_text() == content
        assert "handoff_sess-1_continue.md" in str(path)
