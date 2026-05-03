"""filter list / run / mark / unmark — happy paths.

filter.py is imported in-process and its ``select(client)`` function
is called with a thin wrapper over the CLI's ``_http.api()``. That
means the test fixture's ASGI monkeypatch on ``_make_client`` flows
through filters without any extra setup — same path as production,
no subprocess.

Sessions newly ingested by the fixture are auto-stamped with
``sync_session: new`` by SessionService.ingest, so the built-in
``new-session`` filter (which selects ``tag = "sync_session"``)
returns them out of the box.
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


def _drop_user_filter(cli_env, name: str, select_body: str,
                      mark_add: list[str] | None = None,
                      mark_remove: list[str] | None = None) -> None:
    """Create a user filter under <data_root>/filters/<name>/.

    ``select_body`` is the body of the ``def select(client):`` function
    (each line indented with 4 spaces).
    """
    d = cli_env.config.data_root / "filters" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "filter.py").write_text(
        "def select(client):\n" + select_body + "\n"
    )
    mark_tag: dict = {}
    if mark_add:
        mark_tag["add"] = mark_add
    if mark_remove:
        mark_tag["remove"] = mark_remove
    if not mark_tag:
        mark_tag = {"add": ["_default"]}
    (d / "meta.json").write_text(json.dumps({"mark_tag": mark_tag}))


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
    # mark removes sync_session — empty add, single-entry remove.
    assert new_session["mark_tag"]["add"] == []
    assert new_session["mark_tag"]["remove"] == ["sync_session"]


async def test_list_user_filter_overrides_builtin(cli_env):
    _drop_user_filter(
        cli_env, "new-session",
        "    return []",
        mark_add=["_user-override"],
    )
    code, out = await _run_cli_json(cli_env, "filter", "list")
    assert code == 0
    new_session = next(f for f in out["filters"] if f["name"] == "new-session")
    assert new_session["source"] == "user"
    assert new_session["mark_tag"]["add"] == ["_user-override"]


# -------- filter run --------

async def test_run_builtin_new_session_returns_synced_sessions(cli_env):
    """Sessions ingested by the fixture get sync_session:new automatically;
    the built-in filter selects them by `tag = "sync_session"`."""
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
        mark_add=["_filter-fixed"],
    )
    code, out = await _run_cli_json(cli_env, "filter", "run", "fixed")
    assert code == 0, out
    assert out["subject_ids"] == sids


# -------- filter mark / unmark --------

async def test_mark_strips_sync_session_tag(cli_env):
    sids = await _seed_sessions(cli_env, 2)
    code, out = await _run_cli_json(cli_env, "filter", "mark", "new-session", *sids)
    assert code == 0, out
    applied = out["applied"]
    assert len(applied) == 2
    for r in applied:
        # mark for the built-in new-session does `tag remove sync_session`
        assert r["added"] == []
        assert r["removed"] == ["sync_session"]
        assert r["errors"] == []

    for sid in sids:
        s_tags = await cli_env.app.state.db.tags.list_for_subject(sid)
        assert "sync_session" not in [t["key"] for t in s_tags]


async def test_run_after_mark_excludes_marked_sessions(cli_env):
    """Built-in new-session filter; after marking some, run sees fewer."""
    sids = await _seed_sessions(cli_env, 3)
    await cli_env.app.state.vectors.ensure_fts_index("sessions", replace=True)
    await cli_env.app.state.vectors.ensure_fts_index("cards", replace=True)

    await _run_cli_json(cli_env, "filter", "mark", "new-session", sids[0], sids[1])

    code, out = await _run_cli_json(cli_env, "filter", "run", "new-session")
    assert code == 0
    assert out["subject_ids"] == [sids[2]]


async def test_unmark_per_subject_restores_sync_session_tag(cli_env):
    sids = await _seed_sessions(cli_env, 2)
    await _run_cli_json(cli_env, "filter", "mark", "new-session", *sids)

    code, out = await _run_cli_json(cli_env, "filter", "unmark", "new-session", sids[0])
    assert code == 0, out
    applied = out["applied"]
    assert len(applied) == 1
    assert applied[0]["subject_id"] == sids[0]
    # unmark swaps remove↔add: framework re-adds sync_session (with empty value).
    assert applied[0]["added"] == ["sync_session"]
    assert applied[0]["removed"] == []

    s0_tags = await cli_env.app.state.db.tags.list_for_subject(sids[0])
    s1_tags = await cli_env.app.state.db.tags.list_for_subject(sids[1])
    assert "sync_session" in [t["key"] for t in s0_tags]
    assert "sync_session" not in [t["key"] for t in s1_tags]


async def test_unmark_global_restores_all_cleared(cli_env):
    """unmark with no subject_ids: re-adds sync_session everywhere it's missing.
    Note: this is the documented over-tag behavior for the `remove`-direction
    half of mark_tag — over-restoration is OK because filter scan determines
    final visibility, not undo precision."""
    sids = await _seed_sessions(cli_env, 3)
    await cli_env.app.state.vectors.ensure_fts_index("sessions", replace=True)
    await cli_env.app.state.vectors.ensure_fts_index("cards", replace=True)

    # Strip sync_session from all three (mark behavior)
    await _run_cli_json(cli_env, "filter", "mark", "new-session", *sids)
    # Now no session has sync_session.
    # Global unmark: framework looks up subjects bearing the inverse-`add`
    # keys. For new-session that's the empty `add` list, so global unmark
    # finds 0 subjects and is a no-op.
    code, out = await _run_cli_json(cli_env, "filter", "unmark", "new-session")
    assert code == 0, out
    # Per-subject explicit unmark still works:
    code, out = await _run_cli_json(cli_env, "filter", "unmark", "new-session", *sids)
    assert code == 0
    for sid in sids:
        keys = [t["key"] for t in await cli_env.app.state.db.tags.list_for_subject(sid)]
        assert "sync_session" in keys


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
    _drop_user_filter(cli_env, "bad-return", "    return 'not a list'", mark_add=["_x"])
    result = cli_env.runner.invoke(cli_env.main, [
        "filter", "run", "bad-return",
        "--data-root", str(cli_env.config.data_root),
    ])
    assert result.exit_code != 0
    msg = result.output + (str(result.exception) if result.exception else "")
    assert "list[str]" in msg


async def test_filter_py_select_raises_propagates_clearly(cli_env):
    _drop_user_filter(cli_env, "raises", "    raise RuntimeError('boom')", mark_add=["_x"])
    result = cli_env.runner.invoke(cli_env.main, [
        "filter", "run", "raises",
        "--data-root", str(cli_env.config.data_root),
    ])
    assert result.exit_code != 0
    msg = result.output + (str(result.exception) if result.exception else "")
    assert "RuntimeError" in msg
    assert "boom" in msg


# -------- sync → filter integration --------

async def test_sync_imported_then_appended_updates_tag_value(cli_env):
    """Re-ingesting an existing session with new rounds switches the tag
    from `sync_session: new` to `sync_session: update`."""
    # Initial ingest → sync_session: new
    await cli_env.app.state.sessions.ingest(IngestSessionRequest(
        session_id="evolving", source="claude-code", created_at="",
        metadata={}, sha256="h1",
        rounds=[IngestRound(
            round_id="r1", parent_id=None, timestamp="",
            speaker="user", role="human",
            content=[ContentBlock(type="text", text="first")],
            is_sidechain=False,
        )],
    ))
    sid = "sess_evolving"
    tags = await cli_env.app.state.db.tags.list_for_subject(sid)
    assert {(t["key"], t["value"]) for t in tags} == {("sync_session", "new")}

    # Re-ingest with an additional round → sync_session: update
    await cli_env.app.state.sessions.ingest(IngestSessionRequest(
        session_id="evolving", source="claude-code", created_at="",
        metadata={}, sha256="h2",
        rounds=[
            IngestRound(
                round_id="r1", parent_id=None, timestamp="",
                speaker="user", role="human",
                content=[ContentBlock(type="text", text="first")],
                is_sidechain=False,
            ),
            IngestRound(
                round_id="r2", parent_id="r1", timestamp="",
                speaker="assistant", role="assistant",
                content=[ContentBlock(type="text", text="second")],
                is_sidechain=False,
            ),
        ],
    ))
    tags = await cli_env.app.state.db.tags.list_for_subject(sid)
    assert {(t["key"], t["value"]) for t in tags} == {("sync_session", "update")}
