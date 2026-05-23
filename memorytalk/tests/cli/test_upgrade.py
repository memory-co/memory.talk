"""upgrade command — fully mocked. We never actually hit PyPI or pip."""
from __future__ import annotations

import subprocess
import sys
from unittest import mock

import pytest
from click.testing import CliRunner

from memorytalk.cli import upgrade as upgrade_mod
from memorytalk.cli.upgrade import upgrade


@pytest.fixture
def runner():
    return CliRunner()


def _patch_current(version: str | None):
    return mock.patch.object(upgrade_mod, "_current_version", return_value=version)


def _patch_latest(version: str | None):
    return mock.patch.object(upgrade_mod, "_fetch_latest_pypi_version", return_value=version)


def _patch_query_fresh(version: str | None):
    return mock.patch.object(upgrade_mod, "_query_installed_version_fresh", return_value=version)


class TestUpgrade:
    # ── already on latest ────────────────────────────────────────────

    def test_already_latest_skips_prompt_and_pip(self, runner):
        with _patch_current("0.5.1"), _patch_latest("0.5.1"), \
             mock.patch.object(subprocess, "run") as run_mock:
            result = runner.invoke(upgrade, [])
        assert result.exit_code == 0
        assert "Already on the latest" in result.output
        run_mock.assert_not_called()

    # ── --check mode ─────────────────────────────────────────────────

    def test_check_flag_does_not_install(self, runner):
        with _patch_current("0.5.1"), _patch_latest("0.5.2"), \
             mock.patch.object(subprocess, "run") as run_mock:
            result = runner.invoke(upgrade, ["--check"])
        assert result.exit_code == 0
        # The available-version banner appears.
        assert "0.5.1" in result.output and "0.5.2" in result.output
        assert "--check" in result.output
        run_mock.assert_not_called()

    # ── --yes (scripted upgrade) ─────────────────────────────────────

    def test_yes_flag_skips_prompt_and_invokes_pip(self, runner):
        completed = subprocess.CompletedProcess(args=[], returncode=0)
        with _patch_current("0.5.1"), _patch_latest("0.5.2"), \
             _patch_query_fresh("0.5.2"), \
             mock.patch.object(subprocess, "run", return_value=completed) as run_mock:
            result = runner.invoke(upgrade, ["--yes"])
        assert result.exit_code == 0
        # Pip was invoked exactly once with the expected shape.
        assert run_mock.call_count == 1
        cmd = run_mock.call_args.args[0]
        # **Critical**: command MUST start with sys.executable (not bare ``pip``)
        # so the upgrade hits THIS interpreter's site-packages.
        assert cmd[0] == sys.executable
        assert cmd[1:5] == ["-m", "pip", "install", "--upgrade"]
        assert cmd[-1] == "memorytalk"

    # ── interactive confirm — yes ────────────────────────────────────

    def test_interactive_confirm_yes_invokes_pip(self, runner):
        completed = subprocess.CompletedProcess(args=[], returncode=0)
        with _patch_current("0.5.1"), _patch_latest("0.5.2"), \
             _patch_query_fresh("0.5.2"), \
             mock.patch.object(subprocess, "run", return_value=completed) as run_mock:
            result = runner.invoke(upgrade, [], input="y\n")
        assert result.exit_code == 0
        run_mock.assert_called_once()

    # ── interactive confirm — no ─────────────────────────────────────

    def test_interactive_confirm_no_does_not_install(self, runner):
        with _patch_current("0.5.1"), _patch_latest("0.5.2"), \
             mock.patch.object(subprocess, "run") as run_mock:
            result = runner.invoke(upgrade, [], input="n\n")
        assert result.exit_code == 0
        assert "Cancelled" in result.output
        run_mock.assert_not_called()

    # ── PyPI unreachable ─────────────────────────────────────────────

    def test_pypi_unreachable_errors_out(self, runner):
        with _patch_current("0.5.1"), _patch_latest(None):
            result = runner.invoke(upgrade, [])
        assert result.exit_code == 1
        # Friendly error mentions a fallback path.
        assert "PyPI" in result.output or "pip install" in result.output

    # ── pip failure ──────────────────────────────────────────────────

    def test_pip_failure_propagates_exit_code(self, runner):
        completed = subprocess.CompletedProcess(args=[], returncode=2)
        with _patch_current("0.5.1"), _patch_latest("0.5.2"), \
             mock.patch.object(subprocess, "run", return_value=completed):
            result = runner.invoke(upgrade, ["--yes"])
        assert result.exit_code == 2
        assert "pip exited" in result.output

    # ── pip ok but version didn't change ─────────────────────────────

    def test_pip_success_but_version_unchanged_errors(self, runner):
        completed = subprocess.CompletedProcess(args=[], returncode=0)
        # pip claims success, but post-install verify still reports old.
        with _patch_current("0.5.1"), _patch_latest("0.5.2"), \
             _patch_query_fresh("0.5.1"), \
             mock.patch.object(subprocess, "run", return_value=completed):
            result = runner.invoke(upgrade, ["--yes"])
        assert result.exit_code == 1
        # Specific guidance: pip may have hit a different Python.
        assert "different Python" in result.output or "show memorytalk" in result.output

    # ── package not installed (defensive — shouldn't happen) ─────────

    def test_package_not_installed_errors_out(self, runner):
        with _patch_current(None):
            result = runner.invoke(upgrade, [])
        assert result.exit_code == 1
        assert "not installed" in result.output


class TestHelpers:
    """Lightweight checks on the helper internals — keep them honest."""

    def test_current_version_returns_string(self):
        # In the test environment, memorytalk is installed (we're testing
        # against the dev copy), so _current_version should return.
        v = upgrade_mod._current_version()
        assert isinstance(v, str) and v

    def test_query_installed_version_fresh_uses_sys_executable(self):
        # Ensure the verification subprocess targets the same interpreter
        # we're running on — not a stray ``python`` on PATH.
        with mock.patch.object(subprocess, "run") as run_mock:
            run_mock.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="0.5.1", stderr="",
            )
            v = upgrade_mod._query_installed_version_fresh()
        assert v == "0.5.1"
        cmd = run_mock.call_args.args[0]
        assert cmd[0] == sys.executable
        assert cmd[1] == "-c"
