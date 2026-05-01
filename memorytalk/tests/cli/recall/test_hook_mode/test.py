"""--hook 模式：stdin Claude UserPromptSubmit payload → stdout hookSpecificOutput JSON.

所有失败路径都必须 exit 0 + 空 additionalContext，不能阻塞 Claude 用户输入。
"""
from __future__ import annotations
import json
from unittest.mock import patch

import httpx
from memorytalk.schemas import CardRoundsItem, ContentBlock, CreateCardRequest, IngestRound, IngestSessionRequest


async def _seed(cli_env):
    """Seed a session + a card so recall has something to retrieve."""
    await cli_env.app.state.sessions.ingest(IngestSessionRequest(
        session_id="src", source="claude-code", created_at="",
        metadata={}, sha256="h",
        rounds=[IngestRound(
            round_id="r1", parent_id=None, timestamp="",
            speaker="user", role="human",
            content=[ContentBlock(type="text", text="LanceDB intro")],
            is_sidechain=False,
        )],
    ))
    await cli_env.app.state.cards.create(CreateCardRequest(
        summary="LanceDB selection",
        rounds=[CardRoundsItem(session_id="sess_src", indexes="1")],
    ))


def _invoke_hook(cli_env, stdin_payload: str):
    """Run the CLI with stdin set to payload string, return CliRunner Result."""
    return cli_env.runner.invoke(
        cli_env.main,
        ["recall", "--hook", "--data-root", str(cli_env.config.data_root)],
        input=stdin_payload,
    )


def _parse_stdout_json(result):
    """Stdout must be a single hookSpecificOutput JSON object."""
    return json.loads(result.stdout.strip())


# -------- 成功路径 --------

async def test_hook_success_emits_recalled_cards_as_bullets(cli_env):
    await _seed(cli_env)
    payload = json.dumps({
        "session_id": "in-flight-session",
        "prompt": "LanceDB",
        "hook_event_name": "UserPromptSubmit",
    })

    result = _invoke_hook(cli_env, payload)

    assert result.exit_code == 0, result.stdout
    out = _parse_stdout_json(result)
    assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "Recalled from prior sessions:" in ctx
    assert "card_" in ctx  # 至少有一条 card_id


# -------- 空命中 --------

async def test_hook_empty_recall_emits_empty_context(cli_env):
    """Recall 没命中任何 card 时，additionalContext 整个为空字符串。"""
    # 不 seed，session 也不存在 → 空 recall
    payload = json.dumps({
        "session_id": "nonexistent",
        "prompt": "anything",
    })

    result = _invoke_hook(cli_env, payload)

    assert result.exit_code == 0
    out = _parse_stdout_json(result)
    assert out["hookSpecificOutput"]["additionalContext"] == ""


# -------- 失败必须静默 --------

def test_hook_malformed_stdin_returns_empty(cli_env):
    """非 JSON stdin → 空 ctx + exit 0。"""
    result = _invoke_hook(cli_env, "this is not json {{{")
    assert result.exit_code == 0
    out = _parse_stdout_json(result)
    assert out["hookSpecificOutput"]["additionalContext"] == ""


def test_hook_stdin_missing_session_id_returns_empty(cli_env):
    payload = json.dumps({"prompt": "no session"})
    result = _invoke_hook(cli_env, payload)
    assert result.exit_code == 0
    out = _parse_stdout_json(result)
    assert out["hookSpecificOutput"]["additionalContext"] == ""


def test_hook_stdin_missing_prompt_returns_empty(cli_env):
    payload = json.dumps({"session_id": "x"})
    result = _invoke_hook(cli_env, payload)
    assert result.exit_code == 0
    out = _parse_stdout_json(result)
    assert out["hookSpecificOutput"]["additionalContext"] == ""


def test_hook_server_down_returns_empty(cli_env, monkeypatch):
    """模拟 server 没起来 (httpx 抛 ConnectError)。"""
    from memorytalk.cli import _http

    def boom(*a, **kw):
        raise httpx.ConnectError("connection refused")

    class FakeClient:
        def request(self, *a, **kw):
            boom()

    monkeypatch.setattr(_http, "_make_client", lambda cfg: FakeClient())

    payload = json.dumps({"session_id": "x", "prompt": "q"})
    result = _invoke_hook(cli_env, payload)
    assert result.exit_code == 0
    out = _parse_stdout_json(result)
    assert out["hookSpecificOutput"]["additionalContext"] == ""


def test_hook_outer_exception_net_emits_empty(cli_env, monkeypatch):
    """If something unforeseen raises before the inner try/except blocks
    (e.g. Config() construction itself fails), the outer BaseException
    net still emits valid hook JSON + exit 0."""
    from memorytalk.cli import recall as recall_mod

    class BoomConfig:
        def __init__(self, *a, **kw):
            raise RuntimeError("simulated config failure")

    monkeypatch.setattr(recall_mod, "Config", BoomConfig)

    payload = json.dumps({"session_id": "x", "prompt": "q"})
    result = _invoke_hook(cli_env, payload)

    assert result.exit_code == 0
    out = _parse_stdout_json(result)
    assert out["hookSpecificOutput"]["additionalContext"] == ""
