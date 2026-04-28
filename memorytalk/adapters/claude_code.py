"""Claude Code adapter — reads ~/.claude/projects/*.jsonl conversation files
and produces POST /v2/sessions payloads.

Porting note: v1 produced Session model objects; v2 wants the HTTP request
body shape (raw platform session_id, dict rounds, sha256 over source bytes).
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Iterator
from urllib.parse import unquote

from memorytalk.adapters.base import BaseAdapter, register


@register
class ClaudeCodeAdapter(BaseAdapter):
    source_name = "claude-code"

    DEFAULT_ROOT = Path.home() / ".claude" / "projects"

    def iter_sessions(self, root: Path | None = None) -> Iterator[dict]:
        d = Path(root) if root else self.DEFAULT_ROOT
        if not d.exists():
            return
        for path in sorted(d.rglob("*.jsonl")):
            payload = self._convert_file(path)
            if payload:
                yield payload

    def _convert_file(self, path: Path) -> dict | None:
        raw_bytes = path.read_bytes()
        sha256 = hashlib.sha256(raw_bytes).hexdigest()
        session_id = path.stem  # raw platform id, no sess_ prefix
        project_dir = path.parent.name
        project_name = unquote(project_dir)

        rounds: list[dict] = []
        created_at: str | None = None
        for line in raw_bytes.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            r = self._parse_message(msg)
            if r is None:
                continue
            rounds.append(r)
            if created_at is None and r.get("timestamp"):
                created_at = r["timestamp"]

        if not rounds:
            return None

        return {
            "session_id": session_id,
            "source": self.source_name,
            "created_at": created_at or "",
            "metadata": {"project": project_name, "path": str(path)},
            "sha256": sha256,
            "rounds": rounds,
        }

    def _parse_message(self, msg: dict) -> dict | None:
        msg_type = msg.get("type")
        if msg_type not in ("user", "assistant"):
            return None
        role = "human" if msg_type == "user" else "assistant"
        speaker = "user" if msg_type == "user" else "assistant"
        raw_content = msg.get("message", {}).get("content", [])
        blocks = self._parse_content(raw_content)
        if not blocks:
            if isinstance(raw_content, str):
                blocks = [{"type": "text", "text": raw_content}]
            else:
                return None
        return {
            "round_id": msg.get("uuid", ""),
            "parent_id": msg.get("parentUuid"),
            "timestamp": msg.get("timestamp"),
            "speaker": speaker,
            "role": role,
            "content": blocks,
            "is_sidechain": bool(msg.get("isSidechain")),
            "cwd": msg.get("cwd"),
        }

    def _parse_content(self, content_list) -> list[dict]:
        if not isinstance(content_list, list):
            return []
        out: list[dict] = []
        for block in content_list:
            if not isinstance(block, dict):
                continue
            t = block.get("type")
            if t == "text":
                text = block.get("text") or ""
                if text:
                    out.append({"type": "text", "text": text})
            elif t == "thinking":
                thinking = block.get("thinking") or ""
                if thinking:
                    out.append({"type": "thinking", "thinking": thinking})
            elif t == "tool_use":
                name = block.get("name", "tool")
                inp = block.get("input", "")
                if isinstance(inp, dict):
                    inp = json.dumps(inp, ensure_ascii=False)
                out.append({"type": "text", "text": f"[{name}] {inp}"})
            elif t == "tool_result":
                c = block.get("content", "")
                if isinstance(c, list):
                    c = json.dumps(c, ensure_ascii=False)
                out.append({"type": "text", "text": str(c)})
        return out
