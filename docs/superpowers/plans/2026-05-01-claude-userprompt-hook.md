# Claude Code UserPromptSubmit Hook — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `pip install + memory-talk setup` 装的用户也能享受 Claude Code 集成 —— setup 末尾自动检测 Claude Code 并把 UserPromptSubmit hook 写入 `~/.claude/settings.json`，每次用户输入 Claude 都会通过 `memory-talk recall --hook` 拿到相关记忆作为 `additionalContext`。

**Architecture:** 不新增 `hook` 子命令；现有 `recall` 加 `--hook` 模式（stdin 读 Claude payload + stdout 写 hookSpecificOutput JSON）。新增一个 wizard 末步 `_step_claude_hook` 负责检测 + 合并写 `~/.claude/settings.json`，用 `_source: "memory-talk"` tag 做幂等。所有失败路径必须静默 exit 0，绝不阻塞 Claude 用户输入。

**Tech Stack:** Python 3.11+ · click · httpx · pydantic · `string.Template`（已有）· `shutil.which` · `util/settings_io.write_settings_atomic`（已有）。所有 HTTP 走现有 `cli/_http.api()`。

**Spec:** `docs/superpowers/specs/2026-05-01-claude-userprompt-hook-design.md`

---

## 涉及文件总览

- **修改**：`memorytalk/cli/recall.py`
  - 加 `--hook` flag，使两个位置参数变成可选
  - 新增 `_run_hook_mode()` 函数处理 stdin/stdout 流程
- **新建**：`memorytalk/cli/setup/steps/claude_hook.py`
  - `_step_claude_hook()` 函数：检测 + 合并写 `~/.claude/settings.json`
  - 模块级常量：`CLAUDE_DIR`, `SETTINGS`, `COMMAND`, `SOURCE_TAG`, `ENTRY_TEMPLATE`
- **修改**：`memorytalk/cli/setup/wizard.py`
  - 在 `_step_server` 调用之后追加 `_step_claude_hook()` 调用
  - `_wizard` 返回值新增 `claude_hook` 字段
- **修改**：`memorytalk/cli/setup/summary.py`
  - 新增 `_hook_label()` 辅助函数
  - 在 `PATH takeover` 行和 `changed` 行之间插入 `claude hook` 行
- **新建**：`memorytalk/tests/cli/recall/test_hook_mode/`
  - 6 个测试覆盖 `--hook` 模式的成功 / 空命中 / server-down / 坏 stdin / 缺字段 / 5xx
- **新建**：`memorytalk/tests/cli/setup/test_claude_hook_install/`
  - 7 个测试覆盖 detect 失败 / fresh / merge / unchanged / updated / corrupt JSON

不涉及：`validate_embedder`、provider/embedding、Cursor 的 `hooks-cursor.json`、Claude session ↔ memory-talk session 映射、hook 卸载 CLI。

---

## Task 0：Pre-implementation 手动验证 stdin payload 字段名

**这一步不出 commit。** spec 假定 Claude Code 在 UserPromptSubmit 事件 stdin 里给 `session_id` 和 `prompt` 字段。如果字段名不对，所有测试 mock 都得重做。**所以一定要先验证。**

- [ ] **Step 1：临时落一个 dump-stdin hook**

把 `~/.claude/settings.json` 备份一份（`cp ~/.claude/settings.json ~/.claude/settings.json.before-verify`），然后用如下条目临时替换/合并：

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "cat > /tmp/claude-hook-debug.log",
            "async": false
          }
        ]
      }
    ]
  }
}
```

如果你已经有别的 hook，保留它们，只 append 这一条到 `UserPromptSubmit` 数组里。

- [ ] **Step 2：开 Claude Code 会话，发任意一句话**

例：直接问 Claude "say hi"。Claude 会触发 hook，stdin 会被 `cat` 完整重定向到 `/tmp/claude-hook-debug.log`。

- [ ] **Step 3：检查实际 JSON shape**

```bash
cat /tmp/claude-hook-debug.log | python3 -m json.tool
```

确认下面三件事：

1. **`session_id` 字段名是否就叫这个**？（不是 `sessionId` / `session` / 之类的变体）
2. **用户输入的 prompt 字段叫什么**？我们 spec 里假定的是 `prompt`。如果实际是 `user_prompt` / `message` / `text` 等，记下真实名字。
3. 还有没有其它字段（`transcript_path` / `cwd` / `hook_event_name`）符合预期。

- [ ] **Step 4：恢复原 settings.json**

```bash
mv ~/.claude/settings.json.before-verify ~/.claude/settings.json
rm -f /tmp/claude-hook-debug.log
```

- [ ] **Step 5：根据验证结果决策**

- 如果 `session_id` 和 `prompt` 字段名**和 spec 假定的一致** → 直接进 Task 1，无需修改任何代码。
- 如果**字段名不一致**：在 Task 1 的代码里把 `payload["session_id"]` 和 `payload["prompt"]` 替换成实际字段名；在 Task 1 的测试 mock stdin payload 也用真实字段名。spec 文档可不必回改（实施细节，留 commit message 说明即可）。

---

## Task 1：`recall` 加 `--hook` 模式

**Files:**
- Modify: `memorytalk/cli/recall.py`
- Create: `memorytalk/tests/cli/recall/test_hook_mode/__init__.py`（空文件）
- Create: `memorytalk/tests/cli/recall/test_hook_mode/test.py`

**做什么**：给现有 `recall` 命令加一个 `--hook` flag。开关打开时：
- 忽略命令行位置参数
- 从 stdin 读 Claude UserPromptSubmit payload JSON
- 拿出 `session_id` / `prompt` 调 `POST /v2/recall`
- 输出 Claude 期待的 `{hookSpecificOutput: {hookEventName, additionalContext}}` JSON 到 stdout
- **任何**异常 → 空 `additionalContext` + exit 0（不阻塞 Claude）

- [ ] **Step 1：建测试目录 + 空 `__init__.py`**

```bash
mkdir -p memorytalk/tests/cli/recall/test_hook_mode
touch memorytalk/tests/cli/recall/test_hook_mode/__init__.py
```

- [ ] **Step 2：写失败测试**

新建 `memorytalk/tests/cli/recall/test_hook_mode/test.py`：

```python
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
```

- [ ] **Step 3：运行测试，确认全部失败**

```bash
cd /home/twwyzh/mem-go/memory.talk
pytest memorytalk/tests/cli/recall/test_hook_mode/ -v
```

预期：全部 6 个 FAIL —— 因为 `--hook` flag 还不存在，click 会报 `no such option: --hook`。

- [ ] **Step 4：实现 `--hook` 模式**

修改 `memorytalk/cli/recall.py` 整个文件为：

```python
"""CLI: recall <session_id> <prompt> [--top-k N] [--json] → POST /v2/recall.

--hook mode: read Claude Code UserPromptSubmit JSON payload from stdin,
emit Claude hookSpecificOutput JSON to stdout, exit 0 on every error
(must never block the user prompt).
"""
from __future__ import annotations
import json
import sys

import click

from memorytalk.cli._format import fmt_error, fmt_recall
from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.cli._render import emit_json, emit_json_err, emit_md, emit_md_err
from memorytalk.config import Config


@click.command("recall")
@click.argument("session_id", required=False, default=None)
@click.argument("prompt", required=False, default=None)
@click.option("--top-k", type=int, default=None, help="Top-k (default from settings.recall)")
@click.option("--data-root", type=click.Path(), default=None)
@click.option("--json", "json_out", is_flag=True, default=False, help="Emit JSON instead of Markdown")
@click.option("--hook", "hook_mode", is_flag=True, default=False,
              help="Read Claude Code UserPromptSubmit payload from stdin; "
                   "emit Claude hookSpecificOutput JSON. Always exits 0.")
def recall(session_id: str | None, prompt: str | None, top_k: int | None,
           data_root: str | None, json_out: bool, hook_mode: bool) -> None:
    """Hook-stage memory recall: top-K cards inlined for the AI context."""
    if hook_mode:
        _run_hook_mode(top_k, data_root)
        return

    # CLI mode — args required
    if session_id is None or prompt is None:
        emit_md_err(fmt_error("recall requires SESSION_ID and PROMPT (or pass --hook)"))
        sys.exit(2)

    cfg = Config(data_root) if data_root else Config()
    body = {"session_id": session_id, "query": prompt}
    if top_k is not None:
        body["top_k"] = top_k
    try:
        result = api("POST", "/v2/recall", cfg, json_body=body, timeout=30.0)
    except ApiError as e:
        if json_out:
            emit_json_err(e.payload)
        else:
            emit_md_err(fmt_error(extract_error_message(e.payload)))
        sys.exit(1)

    if json_out:
        emit_json(result)
    else:
        emit_md(fmt_recall(result))


def _run_hook_mode(top_k: int | None, data_root: str | None) -> None:
    """UserPromptSubmit hook entry. Always exits 0; emits hook JSON on stdout.

    Errors funnel through _emit("") so Claude never sees a non-zero exit
    or a malformed stdout.
    """
    def _emit(ctx: str) -> None:
        sys.stdout.write(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": ctx,
            }
        }) + "\n")
        sys.stdout.flush()

    # Parse stdin
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
        session_id = payload["session_id"]
        prompt = payload["prompt"]
        if not isinstance(session_id, str) or not isinstance(prompt, str):
            raise TypeError("session_id and prompt must be strings")
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        sys.stderr.write(f"memory-talk hook: malformed stdin ({e})\n")
        _emit("")
        return

    # Call recall API with short timeout (server may be down — fail fast)
    cfg = Config(data_root) if data_root else Config()
    body: dict = {"session_id": session_id, "query": prompt}
    if top_k is not None:
        body["top_k"] = top_k
    try:
        result = api("POST", "/v2/recall", cfg, json_body=body, timeout=2.0)
    except Exception as e:  # noqa: BLE001 — never propagate to Claude
        sys.stderr.write(f"memory-talk hook: recall failed ({e})\n")
        _emit("")
        return

    # Format response
    recalled = result.get("recalled") or []
    if not recalled:
        _emit("")
        return

    lines = ["Recalled from prior sessions:", ""]
    for hit in recalled:
        cid = hit.get("card_id", "?")
        summary = hit.get("summary", "")
        lines.append(f"- [{cid}] {summary}")
    _emit("\n".join(lines))
```

要点：
- `session_id` / `prompt` 改为 `required=False`，CLI 模式下手动检查；`--hook` 模式忽略它们。
- `_run_hook_mode` 用一个内嵌的 `_emit(ctx)` 闭包统一所有 stdout 出口，错误处理不重复。
- `except Exception`（带 `noqa: BLE001`）—— 此处确实需要 catch-all，hook 进程绝不能用未捕获异常砸 Claude。
- `timeout=2.0` 换掉默认的 `30.0`，server 没起来时秒级返回。

- [ ] **Step 5：运行测试，确认全部通过**

```bash
pytest memorytalk/tests/cli/recall/test_hook_mode/ -v
```

预期：6 passed。

- [ ] **Step 6：跑现有 recall 测试，确认无回归**

```bash
pytest memorytalk/tests/cli/recall/ -v
```

预期：全绿（既有 4 个 + 新增 6 个 = 10 passed）。

- [ ] **Step 7：commit**

```bash
git add memorytalk/cli/recall.py memorytalk/tests/cli/recall/test_hook_mode/
git commit -m "$(cat <<'EOF'
feat(cli/recall): add --hook mode for Claude Code UserPromptSubmit

Reads UserPromptSubmit JSON payload from stdin, calls POST /v2/recall,
emits Claude hookSpecificOutput JSON to stdout. Always exits 0; any
error (malformed stdin, server down, server 5xx) returns an empty
additionalContext so the hook can never block a user prompt.

HTTP timeout dropped to 2s for hook mode — server-not-up case must
fail fast.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 2：新增 wizard step `_step_claude_hook`（独立测试，不接入 wizard）

**Files:**
- Create: `memorytalk/cli/setup/steps/claude_hook.py`
- Create: `memorytalk/tests/cli/setup/test_claude_hook_install/__init__.py`（空文件）
- Create: `memorytalk/tests/cli/setup/test_claude_hook_install/test.py`

**做什么**：实现独立的 step 函数，检测 + 合并写 `~/.claude/settings.json`。Task 2 只完成 step 本体；Task 3 才把它接进 wizard 流程。这样 step 单独可测、commit 范围干净。

- [ ] **Step 1：建测试目录**

```bash
mkdir -p memorytalk/tests/cli/setup/test_claude_hook_install
touch memorytalk/tests/cli/setup/test_claude_hook_install/__init__.py
```

- [ ] **Step 2：写失败测试**

新建 `memorytalk/tests/cli/setup/test_claude_hook_install/test.py`：

```python
"""_step_claude_hook：检测 Claude Code 存在并合并写 ~/.claude/settings.json。

测试覆盖矩阵：
- 检测失败 (~/.claude 不存在 / claude 不在 PATH) → 静默 skip
- fresh install (settings.json 不存在 / 存在但无 UserPromptSubmit)
- 已有 _source=memory-talk 条目 → unchanged / updated
- 已有其它无关 hook → 必须保留不动
- settings.json 损坏 → skip + warning
"""
from __future__ import annotations
import json
from pathlib import Path

import pytest

from memorytalk.cli.setup.steps.claude_hook import _step_claude_hook


@pytest.fixture
def home_env(tmp_path, monkeypatch):
    """Provides an isolated fake $HOME with no ~/.claude dir by default,
    plus a ``which_claude`` toggle to mock the binary check."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    # Default: claude binary IS on PATH (most tests want gate to pass)
    state = {"which": "/usr/local/bin/claude"}
    import shutil
    monkeypatch.setattr(shutil, "which", lambda name: state["which"] if name == "claude" else None)

    class Env:
        pass

    env = Env()
    env.home = fake_home
    env.claude_dir = fake_home / ".claude"
    env.settings_path = env.claude_dir / "settings.json"
    env.set_claude_on_path = lambda present: state.update(which="/usr/local/bin/claude" if present else None)
    return env


def _make_claude_dir(env):
    env.claude_dir.mkdir()


def _read_settings(env):
    return json.loads(env.settings_path.read_text())


# -------- 检测失败：必须静默跳过 --------

def test_skip_when_claude_dir_missing(home_env):
    # ~/.claude 不存在
    result = _step_claude_hook()
    assert result["status"] == "skipped"
    assert "Claude Code not detected" in result["reason"]
    assert not home_env.settings_path.exists()


def test_skip_when_claude_not_on_path(home_env):
    _make_claude_dir(home_env)  # ~/.claude 存在
    home_env.set_claude_on_path(False)  # 但 binary 不在 PATH
    result = _step_claude_hook()
    assert result["status"] == "skipped"
    assert "Claude Code not detected" in result["reason"]
    assert not home_env.settings_path.exists()


# -------- fresh install --------

def test_fresh_install_creates_settings_file(home_env):
    _make_claude_dir(home_env)
    result = _step_claude_hook()
    assert result["status"] == "installed"
    data = _read_settings(home_env)
    blocks = data["hooks"]["UserPromptSubmit"]
    assert len(blocks) == 1
    entries = blocks[0]["hooks"]
    assert len(entries) == 1
    e = entries[0]
    assert e["type"] == "command"
    assert e["command"] == "memory-talk recall --hook"
    assert e["async"] is False
    assert e["_source"] == "memory-talk"


def test_install_into_existing_settings_preserves_other_hooks(home_env):
    _make_claude_dir(home_env)
    # 用户原本已有别的 hook（PostToolUse + 其它 UserPromptSubmit 条目）
    home_env.settings_path.write_text(json.dumps({
        "hooks": {
            "PostToolUse": [{"hooks": [{"type": "command", "command": "echo done"}]}],
            "UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": "/path/to/other-hook.sh"}]}
            ],
        },
        "theme": "dark",
    }))

    result = _step_claude_hook()
    assert result["status"] == "installed"
    data = _read_settings(home_env)
    # 其它 event 没动
    assert data["hooks"]["PostToolUse"][0]["hooks"][0]["command"] == "echo done"
    # UserPromptSubmit 的老条目还在
    ups = data["hooks"]["UserPromptSubmit"]
    other_block = ups[0]
    assert other_block["hooks"][0]["command"] == "/path/to/other-hook.sh"
    # 我们的新条目追加了
    new_blocks = [b for b in ups if any(
        e.get("_source") == "memory-talk" for e in b.get("hooks", [])
    )]
    assert len(new_blocks) == 1
    # 顶层无关字段保留
    assert data["theme"] == "dark"


# -------- 幂等：已存在的处理 --------

def test_unchanged_when_entry_already_correct(home_env):
    _make_claude_dir(home_env)
    home_env.settings_path.write_text(json.dumps({
        "hooks": {
            "UserPromptSubmit": [{
                "hooks": [{
                    "type": "command",
                    "command": "memory-talk recall --hook",
                    "async": False,
                    "_source": "memory-talk",
                }]
            }]
        }
    }))
    mtime_before = home_env.settings_path.stat().st_mtime_ns

    result = _step_claude_hook()
    assert result["status"] == "unchanged"
    # 文件不应被改写
    assert home_env.settings_path.stat().st_mtime_ns == mtime_before


def test_updated_when_entry_command_differs(home_env):
    _make_claude_dir(home_env)
    home_env.settings_path.write_text(json.dumps({
        "hooks": {
            "UserPromptSubmit": [{
                "hooks": [{
                    "type": "command",
                    "command": "/old/path/to/memory-talk recall --hook",
                    "async": False,
                    "_source": "memory-talk",
                    "user_added_field": "preserved",
                }]
            }]
        }
    }))

    result = _step_claude_hook()
    assert result["status"] == "updated"
    data = _read_settings(home_env)
    e = data["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    assert e["command"] == "memory-talk recall --hook"
    # canonical 字段都对
    assert e["_source"] == "memory-talk"
    assert e["async"] is False
    # 用户加的未知字段保留
    assert e["user_added_field"] == "preserved"


# -------- corrupt JSON --------

def test_skip_on_corrupt_settings_json(home_env):
    _make_claude_dir(home_env)
    home_env.settings_path.write_text("{ this is broken json")
    result = _step_claude_hook()
    assert result["status"] == "skipped"
    assert "corrupt" in result["reason"].lower()
    # 损坏文件不应被改写
    assert home_env.settings_path.read_text() == "{ this is broken json"
```

- [ ] **Step 3：运行测试，确认全部失败**

```bash
pytest memorytalk/tests/cli/setup/test_claude_hook_install/ -v
```

预期：全部 7 个 FAIL —— 因为 `_step_claude_hook` 还不存在。

- [ ] **Step 4：实现 `claude_hook.py`**

新建 `memorytalk/cli/setup/steps/claude_hook.py`：

```python
"""Wizard step: install/refresh the UserPromptSubmit hook in
``~/.claude/settings.json`` so Claude Code calls ``memory-talk recall
--hook`` on every user prompt.

Gate (both required, AND):
  - ``~/.claude/`` directory exists
  - ``claude`` binary resolves on $PATH

Idempotency: our entry is tagged ``"_source": "memory-talk"``. Any other
hooks (different events, different tools) are left untouched. A user who
deletes the tag has opted out of automatic management; we'll append a
new tagged entry next to theirs rather than rewriting it.

Failure-soft: corrupt JSON, permission errors, missing ~/.claude all
return a ``skipped`` status with a reason. The wizard never aborts on
hook install — it's a convenience step, not a correctness gate.
"""
from __future__ import annotations
import json
import shutil
from pathlib import Path
from typing import Any

from memorytalk.util.console import err_console, section
from memorytalk.util.settings_io import write_settings_atomic


CLAUDE_DIR = Path.home() / ".claude"  # NOTE: re-evaluated at call time below

COMMAND = "memory-talk recall --hook"
SOURCE_TAG = "memory-talk"

ENTRY_TEMPLATE: dict[str, Any] = {
    "type": "command",
    "command": COMMAND,
    "async": False,
    "_source": SOURCE_TAG,
}


def _claude_dir() -> Path:
    """Re-resolve at call time so tests' Path.home() monkeypatch is honored."""
    return Path.home() / ".claude"


def _settings_path() -> Path:
    return _claude_dir() / "settings.json"


def _step_claude_hook() -> dict:
    """Install / refresh the UserPromptSubmit hook.

    Returns a dict consumed by the wizard summary:
      {"status": "installed" | "updated" | "unchanged" | "skipped",
       "reason": "<text>"  # only present when skipped}
    """
    section("Claude Code hook")

    claude_dir = _claude_dir()
    settings_path = _settings_path()

    # Gate: both ~/.claude/ AND `claude` on $PATH
    if not claude_dir.is_dir():
        err_console.print(
            "[dim]~/.claude not found — skipping Claude hook install[/dim]"
        )
        return {"status": "skipped", "reason": "Claude Code not detected (~/.claude missing)"}
    if shutil.which("claude") is None:
        err_console.print(
            "[dim]`claude` not on $PATH — skipping Claude hook install[/dim]"
        )
        return {"status": "skipped", "reason": "Claude Code not detected (claude not on $PATH)"}

    # Read existing settings (or {} if missing)
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            err_console.print(
                f"[yellow]warning:[/yellow] {settings_path} is corrupt JSON — skipping ({e})"
            )
            return {"status": "skipped", "reason": "settings.json corrupt"}
        if not isinstance(data, dict):
            err_console.print(
                f"[yellow]warning:[/yellow] {settings_path} is not a JSON object — skipping"
            )
            return {"status": "skipped", "reason": "settings.json corrupt"}
    else:
        data = {}

    # Locate or create the UserPromptSubmit array
    hooks_root = data.setdefault("hooks", {})
    if not isinstance(hooks_root, dict):
        err_console.print(
            f"[yellow]warning:[/yellow] hooks field in {settings_path} is not an object — skipping"
        )
        return {"status": "skipped", "reason": "settings.json corrupt"}
    ups_blocks = hooks_root.setdefault("UserPromptSubmit", [])
    if not isinstance(ups_blocks, list):
        err_console.print(
            f"[yellow]warning:[/yellow] UserPromptSubmit in {settings_path} is not a list — skipping"
        )
        return {"status": "skipped", "reason": "settings.json corrupt"}

    # Search for our existing tagged entry
    existing_entry: dict | None = None
    for block in ups_blocks:
        if not isinstance(block, dict):
            continue
        for entry in block.get("hooks", []) or []:
            if isinstance(entry, dict) and entry.get("_source") == SOURCE_TAG:
                existing_entry = entry
                break
        if existing_entry is not None:
            break

    if existing_entry is None:
        ups_blocks.append({"hooks": [dict(ENTRY_TEMPLATE)]})
        action = "installed"
    else:
        # Diff canonical fields only; preserve user-added unknown fields
        diffed = any(existing_entry.get(k) != v for k, v in ENTRY_TEMPLATE.items())
        if not diffed:
            err_console.print("[green]✓[/green] Claude hook already correct")
            return {"status": "unchanged"}
        for k, v in ENTRY_TEMPLATE.items():
            existing_entry[k] = v
        action = "updated"

    # Atomic write
    try:
        write_settings_atomic(settings_path, data)
    except OSError as e:
        err_console.print(
            f"[yellow]warning:[/yellow] write to {settings_path} failed ({e})"
        )
        return {"status": "skipped", "reason": f"write failed: {e}"}

    err_console.print(f"[green]✓[/green] Claude hook {action} → {settings_path}")
    return {"status": action}
```

要点：
- `_claude_dir()` / `_settings_path()` 是函数而不是模块级常量 —— 测试会 monkeypatch `Path.home()`，必须每次调用重新解析，否则 import 时计算的常量会指向错地方。模块顶部那个 `CLAUDE_DIR` 常量本质是文档展示，函数实际不用它。
- 失败处理分层：缺目录 / 无 binary → soft skip（dim 提示）；JSON 损坏 / 写盘失败 → soft skip + yellow warning。两种都 return `{"status": "skipped", "reason": ...}`，wizard 不会终止。
- 已存在条目的判定**只比 canonical 字段**（`type` / `command` / `async` / `_source`），用户加的额外字段（如 `user_added_field`）原样保留。
- 用 `write_settings_atomic`（util 已有）—— 不重复造原子写。

- [ ] **Step 5：运行测试，确认全部通过**

```bash
pytest memorytalk/tests/cli/setup/test_claude_hook_install/ -v
```

预期：7 passed。

- [ ] **Step 6：跑全部 setup 测试，确认没破坏既有场景**

```bash
pytest memorytalk/tests/cli/setup/ -v
```

预期：既有 16 个 + 新增 7 个 = 23 passed。注意：此时 step 还没接进 wizard，所以既有 wizard 测试看不到 `claude hook` 行 —— 这是对的。

- [ ] **Step 7：commit**

```bash
git add memorytalk/cli/setup/steps/claude_hook.py memorytalk/tests/cli/setup/test_claude_hook_install/
git commit -m "$(cat <<'EOF'
feat(cli/setup): _step_claude_hook installs UserPromptSubmit hook

New wizard step (not yet wired in) that detects Claude Code on the
host and merges a UserPromptSubmit entry into ~/.claude/settings.json.

Gate: both ~/.claude/ exists AND `claude` is on $PATH. Either failing
yields a soft-skip; corrupt JSON / write errors also soft-skip with a
warning. Wizard never aborts on hook install.

Idempotent via _source=memory-talk tag — re-running setup either
no-ops, refreshes a stale command, or appends a fresh entry. Other
hooks (different events, different tools, untagged user entries) are
left untouched.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 3：把 step 接入 wizard + summary

**Files:**
- Modify: `memorytalk/cli/setup/wizard.py`
- Modify: `memorytalk/cli/setup/summary.py`
- Modify: `memorytalk/tests/cli/setup/conftest.py`（让既有 wizard 测试在受控状态下绕开 hook step）
- Modify: 至少一个既有 wizard 测试（断言 summary 表里出现 `claude hook` 行）

**做什么**：把 `_step_claude_hook()` 接进 `_wizard()` 末步，结果通过 wizard return dict 传给 `_summary_md()`，summary 表加一行。同时确保既有 wizard 测试不受副作用影响（默认不让 step 真去写 `~/.claude/`）。

- [ ] **Step 1：先在 conftest 里加 hook step 的 stub，让既有 wizard 测试默认绕开**

修改 `memorytalk/tests/cli/setup/conftest.py`，在文件最末尾追加（在 `mock_openai_probe` 函数之前、`monkeypatch.setattr(_prompt, "select", ...)` 这块之后是合适位置）：

```python
    # Default: stub out the Claude hook step so wizard tests don't touch
    # the real ~/.claude/. Tests that want to exercise the hook step
    # explicitly should re-monkeypatch this at the test level.
    from memorytalk.cli.setup.steps import claude_hook as claude_hook_mod
    monkeypatch.setattr(
        claude_hook_mod, "_step_claude_hook",
        lambda: {"status": "skipped", "reason": "stubbed in tests"},
    )
```

注意：这里 monkeypatch 的是 **module-level 的 `_step_claude_hook` 名字**。Task 3 Step 2 把 wizard 改成 `from .steps.claude_hook import _step_claude_hook`，那种 import 方式拿到的是函数对象本身，monkeypatch 这一行**不**会替换 wizard 模块里已经 import 的引用。所以 wizard 那边必须改成 `from .steps import claude_hook as claude_hook_mod` + `claude_hook_mod._step_claude_hook(...)`，跟现有 `from .steps.embedding import _step_embedding` 风格不一致。

为了**保持现有 wizard import 风格统一**，更好的做法是在 conftest 里直接 monkeypatch wizard 模块的引用：

```python
    from memorytalk.cli.setup import wizard as wizard_mod
    monkeypatch.setattr(
        wizard_mod, "_step_claude_hook",
        lambda: {"status": "skipped", "reason": "stubbed in tests"},
    )
```

— 在 wizard.py 里依然用 `from .steps.claude_hook import _step_claude_hook`，但 conftest patch 的是 wizard 模块上**已 bound 的名字**，这样 wizard 内部 `_step_claude_hook()` 调用会拿到 stub。

**用第二种**。conftest 追加这两行（位置同上文）：

```python
    # Stub out the Claude hook step so wizard tests don't touch real ~/.claude/.
    # Tests that want to exercise the hook step explicitly re-monkeypatch this.
    from memorytalk.cli.setup import wizard as wizard_mod
    monkeypatch.setattr(
        wizard_mod, "_step_claude_hook",
        lambda: {"status": "skipped", "reason": "stubbed in tests"},
    )
```

- [ ] **Step 2：改 `wizard.py`，调用 step 并返回结果**

打开 `memorytalk/cli/setup/wizard.py`，做两处修改。

**修改 A**：imports 区追加：

```python
from .steps.claude_hook import _step_claude_hook
```

放在已有的 `from .steps.server import _step_server` 那行下面。

**修改 B**：在 `_wizard()` 函数末尾，把现有的：

```python
    # 7. server start/restart prompt
    server_payload = _step_server(cfg, old_raw is not None and bool(changed))

    return {
        "settings_changed": changed,
        "wrote_settings": True,
        "ensured_dirs": True,
        "server": server_payload,
        "first_install": is_first_install,
    }
```

替换为：

```python
    # 7. server start/restart prompt
    server_payload = _step_server(cfg, old_raw is not None and bool(changed))

    # 8. Claude Code hook install (last — wires Claude Code into the now-running server)
    hook_payload = _step_claude_hook()

    return {
        "settings_changed": changed,
        "wrote_settings": True,
        "ensured_dirs": True,
        "server": server_payload,
        "claude_hook": hook_payload,
        "first_install": is_first_install,
    }
```

注意：这里**只在写盘成功路径上**调 hook step，跟 `_step_server` 完全对称。早返回路径（`if old_raw is not None and not changed`）不调 hook —— 完全没改 settings 也没改 server，再去 fiddle Claude 配置没意义。

- [ ] **Step 3：改 `summary.py`，加 `claude hook` 行 + label 函数**

打开 `memorytalk/cli/setup/summary.py`。

**修改 A**：在 `_summary_md` 函数体内，找到这两行：

```python
    takeover = result.get("path_takeover") or {}
    rows.append(("PATH takeover", _takeover_label(takeover)))

    rows.append(("changed", _changed_label(result)))
```

中间插入一行：

```python
    takeover = result.get("path_takeover") or {}
    rows.append(("PATH takeover", _takeover_label(takeover)))

    hook = result.get("claude_hook") or {"status": "unchanged"}
    rows.append(("claude hook", _hook_label(hook)))

    rows.append(("changed", _changed_label(result)))
```

**修改 B**：在文件最末尾追加 `_hook_label` 辅助函数：

```python
def _hook_label(payload: dict) -> str:
    status = payload.get("status", "unchanged")
    if status in ("installed", "updated", "unchanged"):
        return status
    if status == "skipped":
        reason = payload.get("reason", "")
        return f"skipped ({reason})" if reason else "skipped"
    return status
```

- [ ] **Step 4：跑既有 wizard 测试，确认 stub 生效不破坏**

```bash
pytest memorytalk/tests/cli/setup/ -v
```

预期：23 个测试全过。conftest 的 stub 让既有测试看到 `claude hook | skipped (stubbed in tests)`，原有断言不会因为新增这一行而炸（因为它们检查的是 specific 字段如 `"changed"` / `"port"`，不是 row 数）。

- [ ] **Step 5：在 `test_first_install_openai` 里加一条断言，确认 `claude hook` 行实际出现在 summary**

修改 `memorytalk/tests/cli/setup/test_first_install_openai/test.py`，在文件末尾、`assert "ms" in err` 这条断言**之后**追加：

```python
    # Wizard summary now includes a `claude hook` row (stubbed to skipped in conftest).
    assert "claude hook" in result.stdout
    assert "skipped" in result.stdout  # stub 出来的状态
```

- [ ] **Step 6：跑该测试，确认通过**

```bash
pytest memorytalk/tests/cli/setup/test_first_install_openai/ -v
```

预期：1 passed。

- [ ] **Step 7：跑全部测试，验收无回归**

```bash
pytest memorytalk/tests/ 2>&1 | tail -3
```

预期：之前 231 + Task 1 加 6 + Task 2 加 7 + Task 3 不加新测试只改既有 = 244 passed。如果数字不对，看 fail 列表诊断。

- [ ] **Step 8：commit**

```bash
git add memorytalk/cli/setup/wizard.py memorytalk/cli/setup/summary.py memorytalk/tests/cli/setup/conftest.py memorytalk/tests/cli/setup/test_first_install_openai/test.py
git commit -m "$(cat <<'EOF'
feat(cli/setup): wire _step_claude_hook into wizard + summary table

Setup now finishes with a Claude Code hook install step: detect
Claude Code, merge a UserPromptSubmit entry into ~/.claude/settings.json,
report status in the final markdown summary.

The step runs only on success paths (matches _step_server) — a no-op
reconfigure does not touch ~/.claude. Tests stub the step in the
shared conftest so existing wizard tests don't write to the real home.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## 验收

三个 commit 全部落盘后：

```bash
pytest memorytalk/tests/ 2>&1 | tail -3
```

预期所有测试通过。然后做一次端到端手动验证（你自己的机器）：

1. 备份 `~/.claude/settings.json`（之前 Task 0 的备份还在的话用那份）
2. 跑 `~/.memory-talk/.venv/bin/python3 -m memorytalk setup`，全部 Enter 接受默认
3. 看 wizard 末尾输出：应有 `✓ Claude hook installed → /Users/.../.claude/settings.json` 一行 + summary 表里 `claude hook | installed`
4. 检查 `~/.claude/settings.json`，确认 UserPromptSubmit 数组里有一条 `_source: "memory-talk"` 的条目
5. 开个 Claude Code 会话，发一条跟你 memory.talk 里某张 card 相关的消息，应该能看到 Claude 在回复里引用了被 recall 的内容（如果 card 库非空）

## 不在范围内

- Cursor 的 `hooks-cursor.json` —— 后续 spec
- 其它 Claude Code hook 事件（PreToolUse / PostToolUse / Stop）—— 后续
- Claude session ↔ memory-talk session 映射 —— 直接透传
- hook 卸载 CLI —— 用户手动编辑 `~/.claude/settings.json`，需要再说
- hook 延迟优化（Python 启动 + memorytalk import ≈ 300-500ms / prompt）—— 用户报告卡顿再做
