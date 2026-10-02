"""节点目录里放什么(<home>/node/):

    node.sock                       中心 → 节点的控制口(watch / flush / list)
    node.json                       节点进程的 pid(memory.talk node start / stop 用)
    worklets/<worklet id>/
        watch.json                  盯着它的那份说明(节点重启后接着盯)
        settings.json               claude --settings:注入的 hooks
        hooks.jsonl                 hook 事件,一行一个(只追加;推成功了游标才往前挪)
"""
from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

HOOK_SCRIPT = Path(__file__).with_name("hook.py")
CLAUDE_HOOK_EVENTS = ("SessionStart", "SessionEnd", "UserPromptSubmit", "Stop", "Notification", "PreToolUse", "PostToolUse")


def worklet_dir(node_dir: Path, worklet_id: str) -> Path:
    return Path(node_dir) / "worklets" / worklet_id


def hooks_file(node_dir: Path, worklet_id: str) -> Path:
    return worklet_dir(node_dir, worklet_id) / "hooks.jsonl"


def watch_file(node_dir: Path, worklet_id: str) -> Path:
    return worklet_dir(node_dir, worklet_id) / "watch.json"


def claude_settings(node_dir: Path, worklet_id: str) -> Path:
    """写出 claude --settings 用的文件:几个 hook 都跑同一条命令,把事件追加到这个工作单元的 hooks.jsonl。
    --settings 是在用户自己的设置之上「加」,用户原有的 hooks 照跑。交回文件路径。"""
    d = worklet_dir(node_dir, worklet_id)
    d.mkdir(parents=True, exist_ok=True)
    command = shlex.join([sys.executable, str(HOOK_SCRIPT), str(hooks_file(node_dir, worklet_id))])
    hooks = {event: [{"hooks": [{"type": "command", "command": command}]}] for event in CLAUDE_HOOK_EVENTS}
    path = d / "settings.json"
    path.write_text(json.dumps({"hooks": hooks}, ensure_ascii=False, indent=2))
    return path
