"""Tests for talk-memory CLI."""
import pytest
from click.testing import CliRunner
from talk_memory_cli.cli import main


def test_main_help():
    """Test that main command shows help."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "talk-memory" in result.output


def test_serve_command():
    """Test serve command help."""
    runner = CliRunner()
    result = runner.invoke(main, ["serve", "--help"])
    assert result.exit_code == 0
    assert "host" in result.output.lower()


def test_list_command():
    """Test list command help."""
    runner = CliRunner()
    result = runner.invoke(main, ["list", "--help"])
    assert result.exit_code == 0
    assert "platform" in result.output.lower()


def test_search_command():
    """Test search command help."""
    runner = CliRunner()
    result = runner.invoke(main, ["search", "--help"])
    assert result.exit_code == 0
    assert "query" in result.output.lower()


def test_export_command():
    """Test export command help."""
    runner = CliRunner()
    result = runner.invoke(main, ["export", "--help"])
    assert result.exit_code == 0
    assert "format" in result.output.lower()
