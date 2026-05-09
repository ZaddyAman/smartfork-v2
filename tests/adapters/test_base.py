"""Tests for SessionAdapter base class."""

from pathlib import Path
from typing import Optional

import pytest

from smartfork.adapters.base import SessionAdapter
from smartfork.models.session import RawSessionData


class TestSessionAdapterABC:
    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError, match="abstract"):
            SessionAdapter()  # type: ignore[abstract]

    def test_subclass_must_implement_abstract_methods(self) -> None:
        class IncompleteAdapter(SessionAdapter):
            agent_id = "incomplete"
            display_name = "Incomplete"
            session_type = "dir"
            # Missing abstract methods

        with pytest.raises(TypeError, match="abstract"):
            IncompleteAdapter()  # type: ignore[abstract]

    def test_concrete_subclass_can_instantiate(self) -> None:
        class CompleteAdapter(SessionAdapter):
            agent_id = "test"
            display_name = "Test"
            session_type = "dir"

            def is_valid_session(self, session_path: Path) -> bool:
                return True

            def get_session_files(self, session_path: Path) -> list[str]:
                return []

            def parse_raw(self, session_path: Path) -> Optional[RawSessionData]:
                return None

        adapter = CompleteAdapter()
        assert adapter.agent_id == "test"
        assert adapter.display_name == "Test"
        assert adapter.session_type == "dir"

    def test_default_methods_return_empty(self) -> None:
        class MinimalAdapter(SessionAdapter):
            agent_id = "minimal"
            display_name = "Minimal"
            session_type = "file"

            def is_valid_session(self, session_path: Path) -> bool:
                return False

            def get_session_files(self, session_path: Path) -> list[str]:
                return []

            def parse_raw(self, session_path: Path) -> Optional[RawSessionData]:
                return None

        adapter = MinimalAdapter()
        assert adapter.get_default_sessions_paths() == []
        assert adapter.get_ide_choices() == []
        assert adapter.get_default_path_for_ide("vscode") is None

    def test_subclass_can_override_default_paths(self) -> None:
        class PathAdapter(SessionAdapter):
            agent_id = "path_test"
            display_name = "Path Test"
            session_type = "dir"

            def is_valid_session(self, session_path: Path) -> bool:
                return True

            def get_session_files(self, session_path: Path) -> list[str]:
                return []

            def parse_raw(self, session_path: Path) -> Optional[RawSessionData]:
                return None

            def get_default_sessions_paths(self) -> list[Path]:
                return [Path("/custom/path")]

            def get_ide_choices(self) -> list[str]:
                return ["vscode", "cursor"]

        adapter = PathAdapter()
        assert adapter.get_default_sessions_paths() == [Path("/custom/path")]
        assert adapter.get_ide_choices() == ["vscode", "cursor"]
