"""filter list / run / mark / unmark — happy paths.

filter.py is run as a subprocess that shells out to ``memory-talk
search`` in production. In the test fixture there's no real HTTP
server on localhost (we're routed through ASGI/TestClient), so we
substitute the built-in's filter.py with a user-side filter that
prints fixed subject_ids directly. That tests the framework's
discovery + run + mark + unmark flow without depending on a network
round-trip from inside the spawned subprocess.

The built-in's *registration* is still asserted in
``test_list_includes_builtin_new_session`` — that path doesn't touch
subprocess.
"""
from __future__ import annotations
import json
import os

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


def _drop_user_filter(cli_env, name: str, prints: list[str], mark_add: list[str]) -> None:
    """Create a user filter under <data_root>/filters/<name>/ that just
    prints the given lines from filter.py. ``mark_add`` populates
    meta.json's mark_tag.add list."""
    d = cli_env.config.data_root / "filters" / name
    d.mkdir(parents=True, exist_ok=True)
    body = "#!/usr/bin/env python3\n"
    for line in prints:
        body += f"print({line!r})\n"
    (d / "filter.py").write_text(body)
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
    _drop_user_filter(cli_env, "new-session", ["overridden"], ["_user-override"])

    code, out = await _run_cli_json(cli_env, "filter", "list")
    assert code == 0
    new_session = next(f for f in out["filters"] if f["name"] == "new-session")
    assert new_session["source"] == "user"
    assert new_session["mark_tag"]["add"] == ["_user-override"]


# -------- filter run --------

async def test_run_returns_filter_py_output(cli_env):
    sids = await _seed_sessions(cli_env, 3)
    _drop_user_filter(
        cli_env, "fixed-ids",
        # Test comment-skip and blank-line-skip too
        prints=[sids[0], "# comment", "", sids[1], sids[2]],
        mark_add=["_filter-fixed-ids"],
    )

    code, out = await _run_cli_json(cli_env, "filter", "run", "fixed-ids")
    assert code == 0, out
    assert out["filter"] == "fixed-ids"
    assert out["subject_ids"] == sids


# -------- filter mark / unmark --------

async def test_mark_applies_tag_to_specified_subjects(cli_env):
    sids = await _seed_sessions(cli_env, 2)
    _drop_user_filter(
        cli_env, "test-mark",
        prints=sids,
        mark_add=["_filter-test-mark"],
    )

    code, out = await _run_cli_json(cli_env, "filter", "mark", "test-mark", *sids)
    assert code == 0, out
    applied = out["applied"]
    assert len(applied) == 2
    for r in applied:
        assert r["added"] == ["_filter-test-mark"]
        assert r["errors"] == []

    for sid in sids:
        s_tags = await cli_env.app.state.db.tags.list_for_subject(sid)
        assert "_filter-test-mark" in [t["key"] for t in s_tags]


async def test_run_after_mark_excludes_marked_subjects(cli_env):
    """Use a user filter whose filter.py reads its own state from a
    sentinel file so we can simulate "selector excludes marked items"
    without going through memory-talk search."""
    sids = await _seed_sessions(cli_env, 3)

    # filter.py prints all sids EXCEPT those in a sentinel file
    d = cli_env.config.data_root / "filters" / "exclude-marked"
    d.mkdir(parents=True, exist_ok=True)
    (d / "filter.py").write_text(
        "#!/usr/bin/env python3\n"
        f"all_ids = {sids!r}\n"
        "import os\n"
        "marked = set()\n"
        "if os.path.exists('marked.txt'):\n"
        "    marked = set(open('marked.txt').read().split())\n"
        "for sid in all_ids:\n"
        "    if sid not in marked:\n"
        "        print(sid)\n"
    )
    (d / "meta.json").write_text(json.dumps({
        "mark_tag": {"add": ["_filter-exclude-marked"]}
    }))

    # Initially all 3 in frame
    _, out = await _run_cli_json(cli_env, "filter", "run", "exclude-marked")
    assert sorted(out["subject_ids"]) == sorted(sids)

    # Simulate "user processed sids[0] and sids[1]" by writing them to the
    # sentinel + calling mark
    (d / "marked.txt").write_text("\n".join(sids[:2]))
    await _run_cli_json(cli_env, "filter", "mark", "exclude-marked", sids[0], sids[1])

    # Now only sids[2] is in frame
    _, out = await _run_cli_json(cli_env, "filter", "run", "exclude-marked")
    assert out["subject_ids"] == [sids[2]]


async def test_unmark_per_subject_removes_tag(cli_env):
    sids = await _seed_sessions(cli_env, 2)
    _drop_user_filter(
        cli_env, "test-unmark",
        prints=sids,
        mark_add=["_filter-test-unmark"],
    )

    await _run_cli_json(cli_env, "filter", "mark", "test-unmark", *sids)
    code, out = await _run_cli_json(cli_env, "filter", "unmark", "test-unmark", sids[0])
    assert code == 0, out
    applied = out["applied"]
    assert len(applied) == 1
    assert applied[0]["subject_id"] == sids[0]
    # In unmark we swap add↔remove, so the framework removes the tag we
    # originally added.
    assert applied[0]["removed"] == ["_filter-test-unmark"]

    s0_tags = await cli_env.app.state.db.tags.list_for_subject(sids[0])
    s1_tags = await cli_env.app.state.db.tags.list_for_subject(sids[1])
    assert [t["key"] for t in s0_tags] == []
    assert [t["key"] for t in s1_tags] == ["_filter-test-unmark"]


async def test_unmark_global_clears_all_marked(cli_env):
    sids = await _seed_sessions(cli_env, 3)
    _drop_user_filter(
        cli_env, "test-global-unmark",
        prints=sids,
        mark_add=["_filter-test-global-unmark"],
    )

    await _run_cli_json(cli_env, "filter", "mark", "test-global-unmark", *sids)
    code, out = await _run_cli_json(cli_env, "filter", "unmark", "test-global-unmark")
    assert code == 0, out
    touched = {r["subject_id"] for r in out["applied"]}
    assert touched == set(sids)

    for sid in sids:
        tags = await cli_env.app.state.db.tags.list_for_subject(sid)
        assert tags == []
