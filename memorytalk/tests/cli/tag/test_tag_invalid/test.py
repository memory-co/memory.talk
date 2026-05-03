"""`memory-talk tag {add,remove}` — error paths."""
from __future__ import annotations
import json


async def _run_add(cli_env, subject_id: str, *tags: str) -> tuple[int, str]:
    result = cli_env.runner.invoke(cli_env.main, [
        "tag", "add", subject_id, *tags,
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    return result.exit_code, result.stdout


async def _run_remove(cli_env, subject_id: str, *keys: str) -> tuple[int, str]:
    result = cli_env.runner.invoke(cli_env.main, [
        "tag", "remove", subject_id, *keys,
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    return result.exit_code, result.stdout


async def test_tag_add_on_bad_prefix_rejected(cli_env):
    """No sess_ / card_ prefix → CLI itself rejects (BadParameter, exit 2)."""
    result = cli_env.runner.invoke(cli_env.main, [
        "tag", "add", "plain-no-prefix", "decision",
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    assert result.exit_code != 0
    # Click renders BadParameter through .output (stdout+stderr-mixed in test runner)
    msg = result.output or (str(result.exception) if result.exception else "")
    assert "subject_id must start with sess_ or card_" in msg


async def test_tag_add_on_unknown_session_returns_404(cli_env):
    exit_code, stdout = await _run_add(cli_env, "sess_does_not_exist", "decision")
    assert exit_code != 0
    out = json.loads(stdout)
    assert "not found" in str(out["error"])


async def test_tag_add_on_unknown_card_returns_404(cli_env):
    exit_code, stdout = await _run_add(cli_env, "card_does_not_exist", "topic")
    assert exit_code != 0
    out = json.loads(stdout)
    assert "not found" in str(out["error"])


async def test_tag_remove_on_unknown_session_returns_404(cli_env):
    exit_code, stdout = await _run_remove(cli_env, "sess_missing", "decision")
    assert exit_code != 0
    out = json.loads(stdout)
    assert "not found" in str(out["error"])


async def test_tag_remove_with_colon_rejected_by_cli(cli_env):
    """remove takes keys only — anything containing ``:`` is a CLI usage error."""
    result = cli_env.runner.invoke(cli_env.main, [
        "tag", "remove", "sess_x", "project:foo",
        "--data-root", str(cli_env.config.data_root),
        "--json",
    ])
    assert result.exit_code != 0
    msg = result.output or (str(result.exception) if result.exception else "")
    assert "tag remove takes keys only" in msg


async def test_tag_add_empty_key_rejected(cli_env):
    """Tag string with empty key (`":foo"`) → API 400."""
    from memorytalk.schemas import ContentBlock, IngestRound, IngestSessionRequest
    await cli_env.app.state.sessions.ingest(IngestSessionRequest(
        session_id="x", source="claude-code", created_at="",
        metadata={}, sha256="h",
        rounds=[IngestRound(
            round_id="r1", parent_id=None, timestamp="",
            speaker="user", role="human",
            content=[ContentBlock(type="text", text="hi")],
            is_sidechain=False,
        )],
    ))
    exit_code, stdout = await _run_add(cli_env, "sess_x", ":justvalue")
    assert exit_code != 0
    out = json.loads(stdout)
    assert "key cannot be empty" in str(out["error"])
