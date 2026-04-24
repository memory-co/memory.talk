"""`memory-talk search <query> --where <dsl>` — metadata-filtered search.

Focus: the DSL filter is actually wired into the SQL whitelist and
applied to results. Not testing DSL grammar exhaustively (util/dsl.py
has its own unit tests); we assert that the filter wall is real: tagged
sessions pass, untagged ones don't.
"""
from __future__ import annotations
import json

from memory_talk_v2.schemas import ContentBlock, IngestRound, IngestSessionRequest


async def _seed(cli_env):
    """Two sessions with identical text content but different tags."""
    for sid_raw, text in [
        ("platform-a", "LanceDB picked as the vector store"),
        ("platform-b", "LanceDB was also discussed somewhere else"),
    ]:
        await cli_env.app.state.sessions.ingest(IngestSessionRequest(
            session_id=sid_raw, source="claude-code", created_at="",
            metadata={}, sha256=f"h-{sid_raw}",
            rounds=[IngestRound(
                round_id=f"{sid_raw}_r1", parent_id=None, timestamp="",
                speaker="user", role="human",
                content=[ContentBlock(type="text", text=text)],
                is_sidechain=False,
            )],
        ))
    # Only tag sess_platform-a with "decision"
    await cli_env.app.state.db.sessions.update_tags("sess_platform-a", ["decision"])


async def _run_search(cli_env, query: str, where: str) -> tuple[int, dict]:
    result = cli_env.runner.invoke(cli_env.main, [
        "search", query,
        "--where", where,
        "--data-root", str(cli_env.config.data_root),
    ])
    return result.exit_code, json.loads(result.stdout)


async def test_where_filter_narrows_session_hits(cli_env):
    await _seed(cli_env)

    exit_code, out = await _run_search(cli_env, "", 'tag = "decision"')
    assert exit_code == 0, out

    # Empty query + tag=decision → metadata-only filter path.
    # Only sess_platform-a matches; sess_platform-b is excluded.
    assert out["sessions"]["count"] == 1, out
    assert out["sessions"]["results"][0]["session_id"] == "sess_platform-a"


async def test_where_filter_with_nonmatching_tag_returns_empty(cli_env):
    await _seed(cli_env)

    # Tag that no session carries → empty result on sessions side
    exit_code, out = await _run_search(cli_env, "", 'tag = "nonexistent"')
    assert exit_code == 0, out
    assert out["sessions"]["count"] == 0


async def test_where_filter_applies_under_keyword_query_too(cli_env):
    await _seed(cli_env)

    # Both sessions contain "LanceDB"; without the filter both would match.
    # With tag=decision, only sess_platform-a is allowed through.
    exit_code, out = await _run_search(cli_env, "LanceDB", 'tag = "decision"')
    assert exit_code == 0, out

    # DSL whitelist is applied as a LanceDB pre-filter, so the FTS hits
    # are restricted even though both sessions' text contains "LanceDB".
    session_ids = [s["session_id"] for s in out["sessions"]["results"]]
    assert session_ids == ["sess_platform-a"], session_ids


async def test_malformed_where_returns_400_error(cli_env):
    await _seed(cli_env)

    exit_code, out = await _run_search(cli_env, "x", "unknown_field = 'x'")
    # DSL references a field not in FIELDS → DSLError → 400 → CLI error JSON
    assert exit_code != 0
    assert "error" in out
    assert "DSL parse error" in str(out["error"])
