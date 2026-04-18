"""Claude Code adapter — reads ~/.claude/projects/ JSONL conversation files."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

from memory_talk.adapters.base import Adapter
from memory_talk.models.session import Round, Session, TextBlock


class ClaudeCodeAdapter(Adapter):
    name = "claude-code"

    def __init__(self, projects_dir: Path | None = None):
        self.projects_dir = projects_dir or (Path.home() / ".claude" / "projects")

    def discover(self) -> list[Path]:
        if not self.projects_dir.exists():
            return []
        return sorted(self.projects_dir.rglob("*.jsonl"))

    def convert(self, source_path: Path) -> Session:
        rounds: list[Round] = []
        session_id = source_path.stem
        project_name = self._decode_project_name(source_path)

        with source_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                msg = json.loads(line)
                rnd = self._parse_message(msg)
                if rnd:
                    rounds.append(rnd)

        return Session(
            session_id=session_id,
            source="claude-code",
            created_at=rounds[0].timestamp if rounds else None,
            metadata={"project": project_name, "path": str(source_path)},
            tags=["claude-code"],
            rounds=rounds,
            round_count=len(rounds),
        )

    def _parse_message(self, msg: dict) -> Round | None:
        msg_type = msg.get("type")
        if msg_type not in ("user", "assistant"):
            return None

        role = "human" if msg_type == "user" else "assistant"
        speaker = "user" if msg_type == "user" else "assistant"

        content_blocks = self._parse_content(msg.get("message", {}).get("content", []))
        if not content_blocks:
            # Handle string content
            raw_content = msg.get("message", {}).get("content")
            if isinstance(raw_content, str):
                content_blocks = [TextBlock(text=raw_content)]
            else:
                return None

        timestamp = None
        ts_str = msg.get("timestamp")
        if ts_str:
            try:
                ts_str = ts_str.replace("Z", "+00:00")
                timestamp = datetime.fromisoformat(ts_str)
            except (ValueError, TypeError):
                pass

        return Round(
            round_id=msg.get("uuid", ""),
            parent_id=msg.get("parentUuid"),
            timestamp=timestamp,
            speaker=speaker,
            role=role,
            content=content_blocks,
            is_sidechain=msg.get("isSidechain", False),
            cwd=msg.get("cwd"),
        )

    def _parse_content(self, content_list) -> list[TextBlock]:
        if not isinstance(content_list, list):
            return []
        blocks = []
        for block in content_list:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                text = block.get("text", "")
                if text:
                    blocks.append(TextBlock(text=text))
            elif btype == "thinking":
                thinking = block.get("thinking", "")
                if thinking:
                    blocks.append(TextBlock(text=f"[Thinking] {thinking}"))
            elif btype == "tool_use":
                tool_name = block.get("name", "tool")
                tool_input = block.get("input", "")
                if isinstance(tool_input, dict):
                    tool_input = json.dumps(tool_input, ensure_ascii=False)
                blocks.append(TextBlock(text=f"[{tool_name}] {tool_input}"))
        return blocks

    def _decode_project_name(self, source_path: Path) -> str:
        # Project dir is typically the parent of the JSONL file
        # e.g., ~/.claude/projects/-home-user-myproject/session.jsonl
        project_dir = source_path.parent.name
        return unquote(project_dir)


ADAPTERS = {"claude-code": ClaudeCodeAdapter}


def get_adapter(name: str) -> Adapter:
    cls = ADAPTERS.get(name)
    if not cls:
        raise ValueError(f"Unknown adapter: {name}")
    return cls()
