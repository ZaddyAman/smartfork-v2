"""Tests for adapter registry."""

from pathlib import Path

import pytest

from smartfork.adapters.base import SessionAdapter
from smartfork.adapters.registry import (
    _REGISTRY,
    clear_registry,
    get_adapter,
    get_adapter_or_raise,
    is_registered,
    list_adapters,
    list_agent_ids,
    register,
)
from smartfork.models.session import RawSessionData


# Minimal concrete adapter for testing
class _TestAdapter(SessionAdapter):
    agent_id = "test_agent"
    display_name = "Test Adapter"
    session_type = "dir"

    def is_valid_session(self, session_path: Path) -> bool:
        return True

    def get_session_files(self, session_path: Path) -> list[str]:
        return []

    def parse_raw(self, session_path: Path) -> RawSessionData | None:
        return None


class TestRegisterDecorator:
    def setup_method(self) -> None:
        clear_registry()

    def teardown_method(self) -> None:
        clear_registry()

    def test_register_adds_to_registry(self) -> None:
        @register
        class Adapter1(SessionAdapter):
            agent_id = "adapter_1"
            display_name = "A1"
            session_type = "dir"

            def is_valid_session(self, session_path: Path) -> bool:
                return True

            def get_session_files(self, session_path: Path) -> list[str]:
                return []

            def parse_raw(self, session_path: Path) -> RawSessionData | None:
                return None

        assert "adapter_1" in _REGISTRY
        assert isinstance(_REGISTRY["adapter_1"], Adapter1)

    def test_register_preserves_class(self) -> None:
        @register
        class Adapter2(SessionAdapter):
            agent_id = "adapter_2"
            display_name = "A2"
            session_type = "file"

            def is_valid_session(self, session_path: Path) -> bool:
                return False

            def get_session_files(self, session_path: Path) -> list[str]:
                return ["a.txt"]

            def parse_raw(self, session_path: Path) -> RawSessionData | None:
                return None

        assert Adapter2 is not None  # Class still usable

    def test_register_raises_for_non_adapter(self) -> None:
        with pytest.raises(TypeError, match="SessionAdapter"):
            @register
            class NotAnAdapter:
                agent_id = "bad"

    def test_register_raises_for_empty_agent_id(self) -> None:
        with pytest.raises(ValueError, match="agent_id"):
            @register
            class EmptyId(SessionAdapter):
                agent_id = ""
                display_name = "Empty"
                session_type = "dir"

                def is_valid_session(self, session_path: Path) -> bool:
                    return True

                def get_session_files(self, session_path: Path) -> list[str]:
                    return []

                def parse_raw(self, session_path: Path) -> RawSessionData | None:
                    return None

    def test_register_overwrites_duplicate(self) -> None:
        @register
        class First(SessionAdapter):
            agent_id = "duplicate"
            display_name = "First"
            session_type = "dir"

            def is_valid_session(self, session_path: Path) -> bool:
                return True

            def get_session_files(self, session_path: Path) -> list[str]:
                return []

            def parse_raw(self, session_path: Path) -> RawSessionData | None:
                return None

        @register
        class Second(SessionAdapter):
            agent_id = "duplicate"
            display_name = "Second"
            session_type = "file"

            def is_valid_session(self, session_path: Path) -> bool:
                return False

            def get_session_files(self, session_path: Path) -> list[str]:
                return ["x"]

            def parse_raw(self, session_path: Path) -> RawSessionData | None:
                return None

        assert isinstance(_REGISTRY["duplicate"], Second)


class TestGetAdapter:
    def setup_method(self) -> None:
        clear_registry()
        register(_TestAdapter)

    def teardown_method(self) -> None:
        clear_registry()

    def test_returns_adapter_when_registered(self) -> None:
        adapter = get_adapter("test_agent")
        assert adapter is not None
        assert adapter.agent_id == "test_agent"

    def test_returns_none_when_not_registered(self) -> None:
        adapter = get_adapter("nonexistent")
        assert adapter is None


class TestGetAdapterOrRaise:
    def setup_method(self) -> None:
        clear_registry()
        register(_TestAdapter)

    def teardown_method(self) -> None:
        clear_registry()

    def test_returns_adapter_when_found(self) -> None:
        adapter = get_adapter_or_raise("test_agent")
        assert adapter.agent_id == "test_agent"

    def test_raises_key_error_when_not_found(self) -> None:
        with pytest.raises(KeyError, match="No adapter registered"):
            get_adapter_or_raise("missing")


class TestListAdapters:
    def setup_method(self) -> None:
        clear_registry()

    def teardown_method(self) -> None:
        clear_registry()

    def test_returns_empty_when_none_registered(self) -> None:
        assert list_adapters() == []

    def test_returns_all_registered(self) -> None:
        @register
        class A(SessionAdapter):
            agent_id = "a"
            display_name = "A"
            session_type = "dir"

            def is_valid_session(self, session_path: Path) -> bool:
                return True

            def get_session_files(self, session_path: Path) -> list[str]:
                return []

            def parse_raw(self, session_path: Path) -> RawSessionData | None:
                return None

        @register
        class B(SessionAdapter):
            agent_id = "b"
            display_name = "B"
            session_type = "file"

            def is_valid_session(self, session_path: Path) -> bool:
                return False

            def get_session_files(self, session_path: Path) -> list[str]:
                return ["x"]

            def parse_raw(self, session_path: Path) -> RawSessionData | None:
                return None

        adapters = list_adapters()
        assert len(adapters) == 2


class TestListAgentIds:
    def setup_method(self) -> None:
        clear_registry()
        register(_TestAdapter)

    def teardown_method(self) -> None:
        clear_registry()

    def test_returns_sorted_ids(self) -> None:
        ids = list_agent_ids()
        assert "test_agent" in ids
        assert ids == sorted(ids)


class TestIsRegistered:
    def setup_method(self) -> None:
        clear_registry()
        register(_TestAdapter)

    def teardown_method(self) -> None:
        clear_registry()

    def test_returns_true_when_registered(self) -> None:
        assert is_registered("test_agent") is True

    def test_returns_false_when_not_registered(self) -> None:
        assert is_registered("missing") is False


class TestClearRegistry:
    def test_clears_all_entries(self) -> None:
        register(_TestAdapter)
        assert len(_REGISTRY) > 0
        clear_registry()
        assert len(_REGISTRY) == 0
