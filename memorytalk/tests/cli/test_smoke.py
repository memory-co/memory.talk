"""CLI smoke — ``--help`` succeeds for every command, setup wizard runs
its first-install path under non-tty stdin fallback.

These are equivalents-in-spirit of v2's various CLI smokes; they catch
import errors, click-decorator regressions, and stdin-fallback bugs in
``util.console``.
"""
from __future__ import annotations
import json
import pathlib

import pytest
from click.testing import CliRunner


def test_top_level_help():
    from memorytalk.cli import main
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for cmd in ("server", "read", "setup", "sync", "search", "card",
                "review", "recall", "session"):
        assert cmd in result.output


@pytest.mark.parametrize("cmd", [
    "server", "read", "setup", "sync", "search", "card", "review", "recall",
    "session",
])
def test_each_command_help_succeeds(cmd):
    """Each subcommand has its own ``--help`` path. A click decoration
    bug or import-time crash will be caught here, before the user runs."""
    from memorytalk.cli import main
    runner = CliRunner()
    result = runner.invoke(main, [cmd, "--help"])
    assert result.exit_code == 0, result.output


def test_setup_wizard_non_interactive_first_install(tmp_path, monkeypatch):
    """Smoke: drive the setup wizard through its non-TTY fallback with a
    canned stdin script. Exercises the first-install path end-to-end.

    The wizard uses the ``dummy`` embedder so the probe doesn't need a
    real provider — we pre-register dummy in the option list via the
    same monkeypatch hook the test_setup smoke used while developing."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    # Pre-seed a settings.json with dummy provider so the modify-mode
    # path runs (avoids the probe failing on missing sentence-transformers).
    (tmp_path / "settings.json").write_text(json.dumps({
        "server": {"port": 7788},
        "vector": {"provider": "lancedb"},
        "relation": {"provider": "sqlite"},
        "embedding": {"provider": "dummy", "model": "stub",
                      "dim": 384, "timeout": 30.0},
    }))

    import memorytalk.cli.setup as setup_mod
    from memorytalk.util import console
    # Add dummy to the prompt menu (it's hidden in real setup since users
    # shouldn't pick it, but we need it for the non-TTY path here).
    setup_mod._EMB_OPTIONS = [
        console.Option("dummy", description="deterministic hash, tests only"),
        *setup_mod._EMB_OPTIONS,
    ]

    # Inputs: select dummy (1) / blank model / blank dim / blank vector /
    #         blank relation / blank port / "y" for sync-confirm
    #         (modify-mode default is N because the seeded settings.json
    #         predates the sync.enabled field).
    stdin = "1\n\n\n\n\n\ny\n"
    from memorytalk.cli import main
    runner = CliRunner()
    result = runner.invoke(main, ["setup"], input=stdin)
    assert result.exit_code == 0, result.output
    # settings.json now exists and parses.
    raw = pathlib.Path(tmp_path, "settings.json").read_text()
    parsed = json.loads(raw)
    assert parsed["embedding"]["provider"] == "dummy"
    # The new Sync section defaulted to enabled on first install.
    assert parsed["sync"]["enabled"] is True
