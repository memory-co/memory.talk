"""Kimi Code CLI:~/.kimi-code/sessions/wd_*/session_<uuid>/{state.json, agents/main/wire.jsonl}。"""
from __future__ import annotations

import json
from pathlib import Path

from models.task import Round


def _state(session_dir: Path) -> dict | None:
    try:
        return json.loads((session_dir / "state.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


class KimiAdapter:
    name = "kimi"

    def __init__(self, root: Path) -> None:
        self.root = root

    def find(self, cwd: Path, since_mtime: float) -> Path | None:
        if not self.root.is_dir():
            return None
        cands = []
        for wire in self.root.glob("wd_*/session_*/agents/main/wire.jsonl"):
            st = _state(wire.parents[2])
            if st and st.get("workDir") == str(cwd) and wire.stat().st_mtime >= since_mtime:
                cands.append(wire)
        return max(cands, key=lambda p: p.stat().st_mtime) if cands else None

    def rounds(self, path: Path) -> list[Round]:
        out = []
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines()):
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            t, ts = m.get("type"), m.get("time")
            ts = str(ts) if ts is not None else None
            if t == "turn.prompt":
                text = "\n".join(p.get("text", "") for p in m.get("input", []) if isinstance(p, dict))
                out.append(Round(id=f"{path.parent.parent.parent.name}:{n}", timestamp=ts, role="human", text=text))
            elif t == "context.append_loop_event":
                ev = m.get("event") or {}
                et, rid = ev.get("type"), ev.get("uuid") or f"{n}"
                if et == "content.part":
                    part = ev.get("part") or {}
                    if part.get("type") == "text" and part.get("text"):
                        out.append(Round(id=rid, timestamp=ts, role="assistant", text=part["text"]))
                    elif part.get("type") == "think" and part.get("think"):
                        out.append(Round(id=rid, timestamp=ts, role="assistant", text=f"[thinking] {part['think']}"))
                elif et == "tool.call":
                    out.append(Round(id=rid, timestamp=ts, role="assistant",
                                     text=f"[{ev.get('name', 'tool')}] {json.dumps(ev.get('args', {}), ensure_ascii=False)}"))
                elif et == "tool.result":
                    res = ev.get("result") or {}
                    o = res.get("output", res) if isinstance(res, dict) else res
                    out.append(Round(id=ev.get("toolCallId") or rid, timestamp=ts, role="tool",
                                     text=f"[result] {o if isinstance(o, str) else json.dumps(o, ensure_ascii=False)}"))
        return [r for r in out if r.text]
