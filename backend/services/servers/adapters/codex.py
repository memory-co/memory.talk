"""Codex:~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl,session_meta 带 cwd。"""
from __future__ import annotations

import json
from pathlib import Path

from models.task import Round


def _session_cwd(path: Path) -> str | None:
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "session_meta":
                return (msg.get("payload") or {}).get("cwd")
    return None


class CodexAdapter:
    name = "codex"

    def __init__(self, root: Path) -> None:
        self.root = root

    def find(self, cwd: Path, since_mtime: float) -> Path | None:
        if not self.root.is_dir():
            return None
        cands = [p for p in self.root.rglob("rollout-*.jsonl")
                 if p.stat().st_mtime >= since_mtime and _session_cwd(p) == str(cwd)]
        return max(cands, key=lambda p: p.stat().st_mtime) if cands else None

    def rounds(self, path: Path) -> list[Round]:
        out = []
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines()):
            try:
                env = json.loads(line)
            except json.JSONDecodeError:
                continue
            t, payload = env.get("type"), env.get("payload") or {}
            pt, ts = payload.get("type"), env.get("timestamp")
            rid = f"{path.stem}:{n}"
            if t == "event_msg" and pt == "user_message":
                out.append(Round(id=rid, timestamp=ts, role="human", text=payload.get("message") or ""))
            elif t == "event_msg" and pt == "agent_message":
                out.append(Round(id=rid, timestamp=ts, role="assistant", text=payload.get("message") or ""))
            elif t == "response_item" and pt == "function_call":
                out.append(Round(id=rid, timestamp=ts, role="assistant",
                                 text=f"[{payload.get('name') or 'function'}] {payload.get('arguments') or ''}"))
            elif t == "response_item" and pt == "function_call_output":
                o = payload.get("output") or ""
                out.append(Round(id=rid, timestamp=ts, role="tool",
                                 text=f"[result] {o if isinstance(o, str) else json.dumps(o, ensure_ascii=False)}"))
        return [r for r in out if r.text]
