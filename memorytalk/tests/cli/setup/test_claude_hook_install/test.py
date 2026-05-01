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
