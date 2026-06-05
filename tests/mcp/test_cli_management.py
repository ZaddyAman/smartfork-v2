"""Tests for MCP CLI management commands (MCP-08)."""

from typer.testing import CliRunner

from smartfork.cli.commands import app

runner = CliRunner()


class TestMCPCLIManagement:
    """CLI tests for `smartfork mcp` sub-command."""

    def test_mcp_install(self) -> None:
        """MCP-08.1: Install command reports config updated."""
        result = runner.invoke(app, ["mcp", "install"])
        assert result.exit_code == 0
        assert "installed" in result.output

    def test_mcp_serve(self) -> None:
        """MCP-08.2: Serve command reports server start."""
        result = runner.invoke(app, ["mcp", "serve"])
        assert result.exit_code == 0
        assert "running" in result.output

    def test_mcp_status(self) -> None:
        """MCP-08.3: Status command shows server status info."""
        result = runner.invoke(app, ["mcp", "status"])
        assert result.exit_code == 0
        assert "MCP server" in result.output

    def test_mcp_uninstall(self) -> None:
        """MCP-08.4: Uninstall command reports removal and confirms."""
        result = runner.invoke(app, ["mcp", "uninstall"])
        assert result.exit_code == 0
        assert "uninstalled" in result.output
