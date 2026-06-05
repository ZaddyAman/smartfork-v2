"""Tests for Obsidian vault generator."""

from pathlib import Path

from smartfork.models.session import QualityTag, SessionDocument
from smartfork.vault.obsidian import ObsidianVaultGenerator, _escape_yaml, _generate_frontmatter


def _make_session(**kwargs) -> SessionDocument:
    defaults = {
        "session_id": "sess-001",
        "agent": "kilocode",
        "project_name": "myproject",
        "project_root": "/tmp",
        "task_raw": "Fix authentication bug",
        "summary_doc": "Fixed the auth bug.",
        "reasoning_docs": ["JWT token was expired."],
        "domains": ["auth"],
        "languages": ["python"],
        "tech_tags": ["JWT", "FastAPI"],
        "files_edited": ["src/auth.py"],
        "files_read": ["README.md"],
        "quality_tag": QualityTag.SOLUTION_FOUND,
        "duration_minutes": 15.0,
        "session_start": 1700000000000,
        "session_end": 1700000900000,
    }
    defaults.update(kwargs)
    return SessionDocument(**defaults)


class TestHelpers:
    def test_escape_yaml_plain(self) -> None:
        assert _escape_yaml("simple") == "simple"

    def test_escape_yaml_quotes(self) -> None:
        result = _escape_yaml('contains "quotes"')
        assert '\\"' in result

    def test_generate_frontmatter(self) -> None:
        session = _make_session()
        fm = _generate_frontmatter(session)
        assert "---" in fm
        assert "session_id: sess-001" in fm
        assert "agent: kilocode" in fm


class TestObsidianVaultGenerator:
    def test_generate_creates_vault_structure(self, tmp_path: Path) -> None:
        generator = ObsidianVaultGenerator()
        sessions = [
            _make_session(session_id="s1", project_name="proj-a"),
            _make_session(session_id="s2", project_name="proj-b"),
        ]
        vault_dir = tmp_path / "test_vault"
        result = generator.generate(sessions, vault_dir)

        assert result.exists()
        assert (vault_dir / ".obsidian").exists()
        assert (vault_dir / "MOC.md").exists()
        assert (vault_dir / "Graph View.md").exists()
        assert (vault_dir / "s1.md").exists()
        assert (vault_dir / "s2.md").exists()

    def test_generate_project_folders(self, tmp_path: Path) -> None:
        generator = ObsidianVaultGenerator()
        sessions = [
            _make_session(session_id="s1", project_name="proj-a"),
            _make_session(session_id="s2", project_name="proj-b"),
        ]
        vault_dir = tmp_path / "test_vault_folders"
        generator.generate(sessions, vault_dir, project_folders=True)

        assert (vault_dir / "proj-a" / "s1.md").exists()
        assert (vault_dir / "proj-b" / "s2.md").exists()

    def test_generate_empty_vault(self, tmp_path: Path) -> None:
        generator = ObsidianVaultGenerator()
        vault_dir = tmp_path / "empty_vault"
        generator.generate([], vault_dir)

        assert vault_dir.exists()
        assert (vault_dir / ".obsidian").exists()
        assert (vault_dir / "README.md").exists()

    def test_note_contains_frontmatter(self, tmp_path: Path) -> None:
        generator = ObsidianVaultGenerator()
        sessions = [_make_session()]
        vault_dir = tmp_path / "test_vault_fm"
        generator.generate(sessions, vault_dir)

        note = (vault_dir / "sess-001.md").read_text()
        assert "---" in note
        assert "session_id:" in note
        assert "Summary" in note
