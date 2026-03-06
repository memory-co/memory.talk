"""Unit tests for CLI commands."""
import pytest
from click.testing import CliRunner

from memory_talk.cli import main


class TestCLI:
    """Test cases for CLI commands."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    def test_main_help(self, runner):
        """Test main help output."""
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "memory-talk" in result.output

    def test_serve_help(self, runner):
        """Test serve command help."""
        result = runner.invoke(main, ["serve", "--help"])
        assert result.exit_code == 0
        assert "Manage the memory-talk server" in result.output

    def test_serve_start_help(self, runner):
        """Test serve start help."""
        result = runner.invoke(main, ["serve", "start", "--help"])
        assert result.exit_code == 0
        assert "--host" in result.output
        assert "--port" in result.output

    def test_serve_stop_help(self, runner):
        """Test serve stop help."""
        result = runner.invoke(main, ["serve", "stop", "--help"])
        assert result.exit_code == 0

    def test_serve_status_help(self, runner):
        """Test serve status help."""
        result = runner.invoke(main, ["serve", "status", "--help"])
        assert result.exit_code == 0

    def test_status_help(self, runner):
        """Test status command help."""
        result = runner.invoke(main, ["status", "--help"])
        assert result.exit_code == 0
        assert "Show server status" in result.output

    def test_list_help(self, runner):
        """Test list command help."""
        result = runner.invoke(main, ["list", "--help"])
        assert result.exit_code == 0
        assert "List all conversations" in result.output

    def test_search_help(self, runner):
        """Test search command help."""
        result = runner.invoke(main, ["search", "--help"])
        assert result.exit_code == 0
        assert "Search conversations" in result.output

    def test_export_help(self, runner):
        """Test export command help."""
        result = runner.invoke(main, ["export", "--help"])
        assert result.exit_code == 0
        assert "Export a conversation" in result.output
