"""Shared pytest fixtures for SmartFork v2 tests."""

import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from smartfork.config import SmartForkConfig
from smartfork.indexer.metadata_store import MetadataStore
from smartfork.models.search import ResultCard
from smartfork.models.session import QualityTag, SessionDocument

TESTS_DIR = Path(__file__).parent
FIXTURES_DIR = TESTS_DIR / "fixtures"


@pytest.fixture
def mock_llm() -> MagicMock:
    """Mock LLM provider for testing."""
    llm = MagicMock()
    llm.complete.return_value = "Mocked LLM response"
    llm.complete_structured.return_value = None
    return llm


@pytest.fixture
def mock_embedder() -> MagicMock:
    """Mock embedding provider for testing."""
    embedder = MagicMock()
    embedder.embed.return_value = [0.1] * 512
    embedder.embed_query.return_value = [0.1] * 512
    embedder.embed_batch.return_value = [[0.1] * 512]
    embedder.get_dimensions.return_value = 512
    return embedder


@pytest.fixture
def temp_db() -> Iterator[Path]:
    """Temporary SQLite database for metadata store tests."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    yield path
    if path.exists():
        path.unlink()


@pytest.fixture
def temp_chroma_dir() -> Iterator[Path]:
    """Temporary directory for ChromaDB tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    """Temporary config directory with .smartfork structure."""
    config_dir = tmp_path / ".smartfork"
    config_dir.mkdir()
    return config_dir


# Edge case session fixtures

@pytest.fixture
def empty_session_data() -> dict[str, Any]:
    """Session with minimal/empty fields."""
    return {
        "task_raw": "",
        "files_edited": [],
        "files_read": [],
        "reasoning_docs": [],
        "domains": [],
    }


@pytest.fixture
def long_session_data() -> dict[str, Any]:
    """Session with very long content (stress test)."""
    return {
        "task_raw": "Fix the bug " * 500,
        "reasoning_docs": ["Analyzing the problem " * 100],
    }


@pytest.fixture
def unicode_session_data() -> dict[str, Any]:
    """Session with unicode/emoji content."""
    return {
        "task_raw": "Fix authentication 🔐 with emoji ✅ and Café Münster",
        "files_edited": ["src/auth_über.py", "tests/test_mañana.py"],
    }


# System-level testing fixtures

@pytest.fixture
def mock_config_dir(tmp_path: Path) -> Path:
    """Create a temp config directory with config.toml and secrets.env."""
    config_dir = tmp_path / ".smartfork"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[core]\nschema_version = 2\ntheme = "obsidian"\nlog_level = "INFO"\n',
        encoding="utf-8",
    )
    (config_dir / "secrets.env").write_text(
        "ANTHROPIC_API_KEY=test-key\nOPENAI_API_KEY=test-key\n",
        encoding="utf-8",
    )
    return config_dir


@pytest.fixture
def mock_config(mock_config_dir: Path) -> SmartForkConfig:
    """Return a SmartForkConfig with temp paths."""
    return SmartForkConfig(
        sqlite_db_path=mock_config_dir / "metadata.db",
        qdrant_db_path=mock_config_dir / "qdrant",
        cache_dir=mock_config_dir / "cache",
        log_file=mock_config_dir / "smartfork.log",
    )


@pytest.fixture
def cli_runner() -> CliRunner:
    """Return a Typer CliRunner for CLI testing."""
    return CliRunner()


@pytest.fixture
def mock_metadata_store(tmp_path: Path) -> MetadataStore:
    """Return a MetadataStore with a temp SQLite DB and 2-3 sample sessions pre-loaded."""
    db_path = tmp_path / "metadata.db"
    store = MetadataStore(db_path)
    for i in range(3):
        doc = SessionDocument(
            session_id=f"sess_{i}",
            agent="kilocode",
            project_name="test_project",
            project_root=str(tmp_path),
            quality_tag=QualityTag.SOLUTION_FOUND,
            task_raw=f"Task {i}",
        )
        store.upsert_session(doc)
    return store


@pytest.fixture
def populated_store(tmp_path: Path) -> MetadataStore:
    """Return a MetadataStore with 10+ sample sessions (various quality/projects/agents)."""
    db_path = tmp_path / "populated.db"
    store = MetadataStore(db_path)
    agents = ["kilocode", "claudecode", "opencode"]
    projects = ["alpha", "beta", "gamma"]
    qualities = [
        QualityTag.SOLUTION_FOUND,
        QualityTag.PARTIAL,
        QualityTag.DEAD_END,
        QualityTag.REFERENCE,
    ]
    for i in range(12):
        doc = SessionDocument(
            session_id=f"sess_{i:03d}",
            agent=agents[i % len(agents)],
            project_name=projects[i % len(projects)],
            project_root=str(tmp_path),
            quality_tag=qualities[i % len(qualities)],
            task_raw=f"Task {i}",
            languages=["python"] if i % 2 == 0 else ["javascript"],
            domains=["backend"] if i % 3 == 0 else ["frontend"],
        )
        store.upsert_session(doc)
    return store


@pytest.fixture
def mock_scanner() -> Iterator[MagicMock]:
    """Patch SessionScanner.scan to return controlled results."""
    with patch("smartfork.indexer.scanner.SessionScanner.scan", return_value=[]) as m:
        yield m


@pytest.fixture
def mock_indexer() -> Iterator[MagicMock]:
    """Patch FullIndexer.index_all to return predictable stats dict."""
    with patch(
        "smartfork.indexer.indexer.FullIndexer.index_all",
        return_value={
            "scanned": 0,
            "parsed": 0,
            "chunked": 0,
            "stored": 0,
            "enriched": 0,
            "errors": 0,
            "elapsed_seconds": 0.0,
        },
    ) as m:
        yield m


@pytest.fixture
def mock_search_engine() -> Iterator[MagicMock]:
    """Patch DeterministicSearchEngine.search to return controlled ResultCards."""
    with patch(
        "smartfork.search.deterministic.DeterministicSearchEngine.search",
        return_value=[
            ResultCard(
                rank=1,
                session_id="sess_001",
                title="Test Session",
                project_name="alpha",
                match_score=0.95,
                fork_command="smartfork fork sess_001",
            )
        ],
    ) as m:
        yield m


@pytest.fixture
def mock_fork_assembler() -> Iterator[MagicMock]:
    """Patch ForkAssembler.assemble to return controlled markdown."""
    with patch(
        "smartfork.fork.assembler.ForkAssembler.assemble",
        return_value="# Handoff: Test Session",
    ) as m:
        yield m


@pytest.fixture
def mock_vault_generator() -> Iterator[MagicMock]:
    """Patch ObsidianVaultGenerator.generate to return controlled path."""
    with patch(
        "smartfork.vault.obsidian.ObsidianVaultGenerator.generate",
        return_value=Path("/tmp/vault"),
    ) as m:
        yield m


@pytest.fixture
def mock_ollama_available() -> Iterator[MagicMock]:
    """Patch Ollama availability checks to return True."""
    with patch("smartfork.providers.helpers.OLLAMA_AVAILABLE", True), \
         patch("smartfork.providers.llm.OLLAMA_AVAILABLE", True), \
         patch("smartfork.providers.embedding.OLLAMA_AVAILABLE", True), \
         patch("smartfork.providers.helpers.check_ollama_available", return_value=True) as m:
        yield m
