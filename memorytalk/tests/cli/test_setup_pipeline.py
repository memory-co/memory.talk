"""Regression tests for the ``_wizard`` pipeline shape.

These pin down the invariant that bit us twice before refactoring: every
step in ``_STEPS`` runs exactly once on every wizard invocation, even
when ``settings.json`` doesn't change. New steps appended to ``_STEPS``
must be impossible to silently skip via an early-return added upstream.
"""
from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from memorytalk.cli import setup as setup_mod


def _wizard_stdin(*, model="stub", dim="384", vector="", relation="",
                  port="", sync_confirm="y", first_install=False) -> str:
    base = f"1\n{model}\n{dim}\n{vector}\n{relation}\n{port}\n{sync_confirm}\n"
    if first_install:
        base += "n\n"
    return base


def _register_dummy_embedder():
    from memorytalk.util import console
    if not any(o.value == "dummy" for o in setup_mod._EMB_OPTIONS):
        setup_mod._EMB_OPTIONS.insert(0, console.Option("dummy"))

    async def _validate_dummy(cfg):
        return None

    import memorytalk.provider.embedding as emb_mod
    emb_mod.validate_embedder = lambda cfg: _validate_dummy(cfg)


def test_every_step_runs_exactly_once(tmp_path, monkeypatch):
    """The wizard must invoke every entry in ``_STEPS`` once, in order.

    This is the core invariant guarding against the recurring bug class
    where an early-return in the middle of ``_wizard`` (e.g. "no diff —
    skip") silently dropped downstream steps.
    """
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    _register_dummy_embedder()

    calls: list[str] = []
    original_runs = {}
    for step in setup_mod._STEPS:
        original_runs[step.name] = step.run

    def _make_spy(name, original):
        def _spy(ctx):
            calls.append(name)
            return original(ctx)
        return _spy

    spied = tuple(
        setup_mod._Step(s.name, s.section, _make_spy(s.name, s.run))
        for s in setup_mod._STEPS
    )
    monkeypatch.setattr(setup_mod, "_STEPS", spied)

    from memorytalk.cli import main
    runner = CliRunner()
    result = runner.invoke(
        main, ["setup"], input=_wizard_stdin(first_install=True),
    )
    assert result.exit_code == 0, result.output
    assert calls == [s.name for s in spied], (
        f"step run order / completeness changed.\n"
        f"  expected: {[s.name for s in spied]}\n"
        f"  actual:   {calls}\n"
        f"  output:   {result.output}"
    )


def test_resetup_with_no_changes_still_runs_all_steps(tmp_path, monkeypatch):
    """The bug we shipped in 0.8.5: re-running setup with no field
    changes silently skipped the hooks step (and any other downstream
    step). After the pipeline refactor this MUST NOT happen."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    _register_dummy_embedder()

    from memorytalk.cli import main
    runner = CliRunner()

    # First install — writes settings.json.
    r1 = runner.invoke(main, ["setup"], input=_wizard_stdin(first_install=True))
    assert r1.exit_code == 0, r1.output
    settings_first = json.loads((tmp_path / "settings.json").read_text())

    # Second run — accept all defaults so settings.json is identical.
    calls: list[str] = []
    spied = tuple(
        setup_mod._Step(
            s.name, s.section,
            (lambda name, original: lambda ctx: (
                calls.append(name) or original(ctx)
            ))(s.name, s.run),
        )
        for s in setup_mod._STEPS
    )
    monkeypatch.setattr(setup_mod, "_STEPS", spied)
    r2 = runner.invoke(main, ["setup"], input=_wizard_stdin())
    assert r2.exit_code == 0, r2.output

    # Settings file must be unchanged
    settings_after = json.loads((tmp_path / "settings.json").read_text())
    assert settings_first == settings_after, "no-diff run must not rewrite settings"

    # And every step must still have run, including the hooks step at the end
    assert "hooks" in calls, (
        f"hooks step was skipped on no-diff re-run — early-return regression "
        f"is back. step order: {calls}\noutput: {r2.output}"
    )
    assert calls == [s.name for s in spied], (
        f"some steps were skipped on no-diff re-run.\n"
        f"  expected: {[s.name for s in spied]}\n"
        f"  actual:   {calls}"
    )


def test_persist_step_writes_only_when_diff_nonzero(tmp_path, monkeypatch):
    """The diff-guard isn't gone, it just moved into the persist step.
    Confirm that no-diff still does not rewrite the file."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    _register_dummy_embedder()

    from memorytalk.cli import main
    runner = CliRunner()
    r1 = runner.invoke(main, ["setup"], input=_wizard_stdin(first_install=True))
    assert r1.exit_code == 0, r1.output

    path = tmp_path / "settings.json"
    mtime_before = path.stat().st_mtime_ns

    r2 = runner.invoke(main, ["setup"], input=_wizard_stdin())
    assert r2.exit_code == 0, r2.output

    mtime_after = path.stat().st_mtime_ns
    assert mtime_before == mtime_after, (
        "no-diff re-run must not touch settings.json mtime"
    )
