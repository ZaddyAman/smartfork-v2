"""Shared pytest fixtures for SmartFork v2 tests."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

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
def temp_db() -> Path:
    """Temporary SQLite database for metadata store tests."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    yield path
    if path.exists():
        path.unlink()


@pytest.fixture
def temp_chroma_dir() -> Path:
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
def empty_session_data() -> dict:
    """Session with minimal/empty fields."""
    return {
        "task_raw": "",
        "files_edited": [],
        "files_read": [],
        "reasoning_docs": [],
        "domains": [],
    }


@pytest.fixture
def long_session_data() -> dict:
    """Session with very long content (stress test)."""
    return {
        "task_raw": "Fix the bug " * 500,
        "reasoning_docs": ["Analyzing the problem " * 100],
    }


@pytest.fixture
def unicode_session_data() -> dict:
    """Session with unicode/emoji content."""
    return {
        "task_raw": "Fix authentication 🔐 with emoji ✅ and Café Münster",
        "files_edited": ["src/auth_über.py", "tests/test_mañana.py"],
    }
