"""filter list / run / mark / unmark — invalid input + error paths."""
from __future__ import annotations
import json


async def _run(cli_env, *args: str):
    return cli_env.runner.invoke(cli_env.main, [
        *args, "--data-root", str(cli_env.config.data_root),
    ])


async def test_filter_run_unknown_name(cli_env):
    result = await _run(cli_env, "filter", "run", "no-such-filter")
    assert result.exit_code != 0
    assert "filter not found" in (result.output or str(result.exception))


async def test_filter_run_invalid_name_pattern(cli_env):
    # Uppercase + dot — fails the ^[a-z][a-z0-9_-]*$ whitelist
    result = await _run(cli_env, "filter", "run", "Foo.Bar")
    assert result.exit_code != 0
    assert "invalid filter name" in (result.output or str(result.exception))


async def test_filter_user_dir_with_corrupt_meta_is_silently_ignored_in_list(cli_env):
    user_dir = cli_env.config.data_root / "filters" / "broken-one"
    user_dir.mkdir(parents=True)
    (user_dir / "filter.py").write_text("print('hi')\n")
    (user_dir / "meta.json").write_text("{ this is not json")
    # broken-one doesn't show up in list (silently dropped), but the
    # builtin new-session does.
    result = cli_env.runner.invoke(cli_env.main, [
        "filter", "list", "--json",
        "--data-root", str(cli_env.config.data_root),
    ])
    assert result.exit_code == 0
    out = json.loads(result.stdout)
    names = [f["name"] for f in out["filters"]]
    assert "broken-one" not in names
    assert "new-session" in names


async def test_filter_user_dir_with_corrupt_meta_resolve_errors(cli_env):
    user_dir = cli_env.config.data_root / "filters" / "broken-two"
    user_dir.mkdir(parents=True)
    (user_dir / "filter.py").write_text("print('hi')\n")
    (user_dir / "meta.json").write_text("{ not json either")
    # Direct invocation surfaces the parse error
    result = await _run(cli_env, "filter", "run", "broken-two")
    assert result.exit_code != 0


async def test_filter_meta_with_empty_marks_rejected(cli_env):
    user_dir = cli_env.config.data_root / "filters" / "no-ops"
    user_dir.mkdir(parents=True)
    (user_dir / "filter.py").write_text("print('hi')\n")
    (user_dir / "meta.json").write_text(json.dumps({
        "mark_tag": {"add": [], "remove": []}
    }))
    result = await _run(cli_env, "filter", "run", "no-ops")
    assert result.exit_code != 0
    assert "cannot both be empty" in (result.output or "")
