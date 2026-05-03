"""filter list / run / mark / unmark — happy paths.

filter.py is imported in-process and its ``select(client)`` function
is called with a thin wrapper over the CLI's ``_http.api()``. That
means the test fixture's ASGI monkeypatch on ``_make_client`` flows
through filters without any extra setup — same path as production,
no subprocess.
"""
from __future__ import annotations
import json

from memorytalk.schemas import (
    ContentBlock, IngestRound, IngestSessionRequest,
)


async def _seed_sessions(cli_env, n: int = 3) -> list[str]:
    sids: list[str] = []
    for i in range(n):
        await cli_env.app.state.sessions.ingest(IngestSessionRequest(
            session_id=f"src-{i}", source="claude-code", created_at="",
            metadata={}, sha256=f"h{i}",
            rounds=[IngestRound(
                round_id=f"r{i}", parent_id=None, timestamp="",
                speaker="user", role="human",
                content=[ContentBlock(type="text", text=f"text-{i}")],
                is_sidechain=False,
            )],
        ))
        sids.append(f"sess_src-{i}")
    return sids


def _drop_user_filter(cli_env, name: str, select_body: str, mark_add: list[str]) -> None:
    """Create a user filter under <data_root>/filters/<name>/.

    ``select_body`` is the body of the ``def select(client):`` function
    (each line indented with 4 spaces).
    """
    d = cli_env.config.data_root / "filters" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "filter.py").write_text(
        "def select(client):\n" + select_body + "\n"
    )
    (d / "meta.json").write_text(json.dumps({"mark_tag": {"add": mark_add}}))


async def _run_cli(cli_env, *args: str) -> tuple[int, str]:
    result = cli_env.runner.invoke(cli_env.main, [
        *args, "--data-root", str(cli_env.config.data_root),
    ])
    return result.exit_code, result.stdout


async def _run_cli_json(cli_env, *args: str) -> tuple[int, dict]:
    code, out = await _run_cli(cli_env, *args, "--json")
    return code, json.loads(out)


# -------- filter list --------

async def test_list_includes_builtin_new_session(cli_env):
    code, out = await _run_cli_json(cli_env, "filter", "list")
    assert code == 0, out
    names = [f["name"] for f in out["filters"]]
    assert "new-session" in names
    new_session = next(f for f in out["filters"] if f["name"] == "new-session")
    assert new_session["source"] == "builtin"
    assert new_session["mark_tag"]["add"] == ["_filter-new-session"]


async def test_list_user_filter_overrides_builtin(cli_env):
    _drop_user_filter(
        cli_env, "new-session",
        "    return []",
        ["_user-override"],
    )
    code, out = await _run_cli_json(cli_env, "filter", "list")
    assert code == 0
    new_session = next(f for f in out["filters"] if f["name"] == "new-session")
    assert new_session["source"] == "user"
    assert new_session["mark_tag"]["add"] == ["_user-override"]


# -------- filter run --------

async def test_run_builtin_new_session_returns_unmarked_sessions(cli_env):
    """Built-in filter.py calls /v2/search via the same client the CLI
    uses → goes through the test ASGI fixture transparently."""
    sids = await _seed_sessions(cli_env, 3)
    await cli_env.app.state.vectors.ensure_fts_index("sessions", replace=True)
    await cli_env.app.state.vectors.ensure_fts_index("cards", replace=True)

    code, out = await _run_cli_json(cli_env, "filter", "run", "new-session")
    assert code == 0, out
    assert out["filter"] == "new-session"
    assert sorted(out["subject_ids"]) == sorted(sids)


async def test_run_user_filter_with_explicit_ids(cli_env):
    sids = await _seed_sessions(cli_env, 3)
    _drop_user_filter(
        cli_env, "fixed",
        f"    return {sids!r}",
        ["_filter-fixed"],
    )
    code, out = await _run_cli_json(cli_env, "filter", "run", "fixed")
    assert code == 0, out
    assert out["subject_ids"] == sids


# -------- filter mark / unmark --------

async def test_mark_applies_tag_to_specified_subjects(cli_env):
    sids = await _seed_sessions(cli_env, 2)
    code, out = await _run_cli_json(cli_env, "filter", "mark", "new-session", *sids)
    assert code == 0, out
    applied = out["applied"]
    assert len(applied) == 2
    for r in applied:
        assert r["added"] == ["_filter-new-session"]
        assert r["errors"] == []

    for sid in sids:
        s_tags = await cli_env.app.state.db.tags.list_for_subject(sid)
        assert "_filter-new-session" in [t["key"] for t in s_tags]


async def test_run_after_mark_excludes_marked_sessions(cli_env):
    """Built-in new-session filter; after marking some, run sees fewer."""
    sids = await _seed_sessions(cli_env, 3)
    await cli_env.app.state.vectors.ensure_fts_index("sessions", replace=True)
    await cli_env.app.state.vectors.ensure_fts_index("cards", replace=True)

    await _run_cli_json(cli_env, "filter", "mark", "new-session", sids[0], sids[1])

    code, out = await _run_cli_json(cli_env, "filter", "run", "new-session")
    assert code == 0
    assert out["subject_ids"] == [sids[2]]


async def test_unmark_per_subject_removes_tag(cli_env):
    sids = await _seed_sessions(cli_env, 2)
    await _run_cli_json(cli_env, "filter", "mark", "new-session", *sids)

    code, out = await _run_cli_json(cli_env, "filter", "unmark", "new-session", sids[0])
    assert code == 0, out
    applied = out["applied"]
    assert len(applied) == 1
    assert applied[0]["subject_id"] == sids[0]
    # In unmark we swap add↔remove: framework removes the tag we originally added.
    assert applied[0]["removed"] == ["_filter-new-session"]

    s0_tags = await cli_env.app.state.db.tags.list_for_subject(sids[0])
    s1_tags = await cli_env.app.state.db.tags.list_for_subject(sids[1])
    assert [t["key"] for t in s0_tags] == []
    assert [t["key"] for t in s1_tags] == ["_filter-new-session"]


async def test_unmark_global_clears_all_marked(cli_env):
    sids = await _seed_sessions(cli_env, 3)
    await cli_env.app.state.vectors.ensure_fts_index("sessions", replace=True)
    await cli_env.app.state.vectors.ensure_fts_index("cards", replace=True)

    await _run_cli_json(cli_env, "filter", "mark", "new-session", *sids)
    code, out = await _run_cli_json(cli_env, "filter", "unmark", "new-session")
    assert code == 0, out
    touched = {r["subject_id"] for r in out["applied"]}
    assert touched == set(sids)

    for sid in sids:
        tags = await cli_env.app.state.db.tags.list_for_subject(sid)
        assert tags == []


# -------- filter.py validation --------

async def test_filter_py_missing_select_function_errors(cli_env):
    d = cli_env.config.data_root / "filters" / "no-select"
    d.mkdir(parents=True)
    (d / "filter.py").write_text("# no select function defined\n")
    (d / "meta.json").write_text(json.dumps({"mark_tag": {"add": ["_x"]}}))

    result = cli_env.runner.invoke(cli_env.main, [
        "filter", "run", "no-select",
        "--data-root", str(cli_env.config.data_root),
    ])
    assert result.exit_code != 0
    msg = result.output + (str(result.exception) if result.exception else "")
    assert "select" in msg


async def test_filter_py_select_returns_non_list_errors(cli_env):
    _drop_user_filter(cli_env, "bad-return", "    return 'not a list'", ["_x"])
    result = cli_env.runner.invoke(cli_env.main, [
        "filter", "run", "bad-return",
        "--data-root", str(cli_env.config.data_root),
    ])
    assert result.exit_code != 0
    msg = result.output + (str(result.exception) if result.exception else "")
    assert "list[str]" in msg


async def test_filter_py_select_raises_propagates_clearly(cli_env):
    _drop_user_filter(cli_env, "raises", "    raise RuntimeError('boom')", ["_x"])
    result = cli_env.runner.invoke(cli_env.main, [
        "filter", "run", "raises",
        "--data-root", str(cli_env.config.data_root),
    ])
    assert result.exit_code != 0
    msg = result.output + (str(result.exception) if result.exception else "")
    assert "RuntimeError" in msg
    assert "boom" in msg
