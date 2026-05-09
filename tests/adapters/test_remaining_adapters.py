"""Tests for remaining adapters (AntiGravity, Cursor Agent, Cline, Gemini)."""

from smartfork.adapters.registry import clear_registry, get_adapter, list_agent_ids


class TestAllAdaptersRegistered:
    def setup_method(self) -> None:
        clear_registry()
        import importlib

        import smartfork.adapters.antigravity as ag
        import smartfork.adapters.claudecode as cc
        import smartfork.adapters.cline as cl
        import smartfork.adapters.cursor_agent as ca
        import smartfork.adapters.gemini as gm
        import smartfork.adapters.kilocode as kc
        import smartfork.adapters.opencode as oc
        # Reload base classes before subclasses so isinstance checks work
        importlib.reload(kc)
        importlib.reload(cc)
        importlib.reload(oc)
        importlib.reload(ag)
        importlib.reload(cl)
        importlib.reload(ca)
        importlib.reload(gm)

    def teardown_method(self) -> None:
        clear_registry()

    def test_all_seven_adapters_registered(self) -> None:
        ids = list_agent_ids()
        assert "kilocode" in ids
        assert "claudecode" in ids
        assert "opencode" in ids
        assert "antigravity" in ids
        assert "cursor_agent" in ids
        assert "cline" in ids
        assert "gemini" in ids
        assert len(ids) == 7

    def test_antigravity_inherits_kilocode(self) -> None:
        from smartfork.adapters.kilocode import KiloCodeAdapter
        adapter = get_adapter("antigravity")
        assert adapter is not None
        assert isinstance(adapter, KiloCodeAdapter)
        assert adapter.agent_id == "antigravity"
        assert adapter.session_type == "dir"

    def test_placeholder_adapters_are_inactive(self) -> None:
        from pathlib import Path
        for agent_id in ["cursor_agent", "cline", "gemini"]:
            adapter = get_adapter(agent_id)
            assert adapter is not None
            assert adapter.is_valid_session(Path("/tmp")) is False

    def test_all_display_names_set(self) -> None:
        for agent_id in ["cursor_agent", "cline", "gemini", "antigravity"]:
            adapter = get_adapter(agent_id)
            assert adapter is not None
            assert adapter.display_name != ""
