"""Claude Code:~/.claude/projects/<cwd 编码>/<session>.jsonl。"""
from __future__ import annotations

import json
from pathlib import Path

from models.task import Round


def _project_dir(root: Path, cwd: Path) -> Path:
    return root / str(cwd).replace("/", "-")


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for b in content or []:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        if t == "text" and b.get("text"):
            parts.append(b["text"])
        elif t == "thinking" and b.get("thinking"):
            parts.append(f"[thinking] {b['thinking']}")
        elif t == "tool_use":
            inp = b.get("input", "")
            parts.append(f"[{b.get('name', 'tool')}] {json.dumps(inp, ensure_ascii=False) if isinstance(inp, dict) else inp}")
        elif t == "tool_result":
            c = b.get("content", "")
            parts.append(f"[result] {json.dumps(c, ensure_ascii=False) if isinstance(c, list) else c}")
    return "\n".join(parts)


def _role(msg: dict) -> str:
    if msg.get("type") == "assistant":
        return "assistant"
    content = msg.get("message", {}).get("content", [])
    if "toolUseResult" in msg or (isinstance(content, list) and content and isinstance(content[0], dict)
                                  and content[0].get("type") == "tool_result"):
        return "tool"
    if msg.get("isMeta"):
        return "system"
    text = content if isinstance(content, str) else _text_of(content)
    if text.lstrip().startswith(("<command-name>", "<local-command-stdout>", "<local-command-caveat>",
                                 "[Request interrupted by user]")):
        return "system"
    return "human"


class ClaudeCodeAdapter:
    name = "claude"

    def __init__(self, root: Path) -> None:
        self.root = root

    def find(self, cwd: Path, since_mtime: float) -> Path | None:
        d = _project_dir(self.root, cwd)
        if not d.is_dir():
            return None
        cands = [p for p in d.glob("*.jsonl") if p.stat().st_mtime >= since_mtime]
        return max(cands, key=lambda p: p.stat().st_mtime) if cands else None

    def rounds(self, path: Path) -> list[Round]:
        out = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("type") not in ("user", "assistant") or msg.get("isSidechain"):
                continue
            text = _text_of(msg.get("message", {}).get("content", []))
            if not text:
                continue
            out.append(Round(id=msg.get("uuid", ""), timestamp=msg.get("timestamp"), role=_role(msg), text=text))
        return out
