"""Claude Code adapter — reads ~/.claude/projects/ JSONL files."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from memory_talk.adapters.base import Adapter
from memory_talk.models import (
    CodeBlock,
    Round,
    Session,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)


CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"


class ClaudeCodeAdapter(Adapter):
    name = "claude-code"

    def __init__(self, projects_dir: Path | None = None):
        self.projects_dir = projects_dir or CLAUDE_PROJECTS_DIR

    def discover(self) -> list[Path]:
        if not self.projects_dir.exists():
            return []
        paths = []
        for project in sorted(self.projects_dir.iterdir()):
            if not project.is_dir():
                continue
            for session_file in sorted(project.glob("*.jsonl")):
                paths.append(session_file)
        return paths

    def convert(self, source_path: Path) -> Session:
        project_name = source_path.parent.name
        session_id = source_path.stem
        rounds = []
        first_ts = None

        with open(source_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg_type = data.get("type")
                if msg_type not in ("user", "assistant"):
                    continue

                timestamp = self._parse_timestamp(data.get("timestamp", ""))
                if first_ts is None and timestamp:
                    first_ts = timestamp

                content_blocks = self._parse_content(data, msg_type)
                if not content_blocks:
                    continue

                rounds.append(Round(
                    round_id=data.get("uuid", f"r{i:04d}"),
                    timestamp=timestamp,
                    speaker=msg_type,
                    role="human" if msg_type == "user" else "assistant",
                    content=content_blocks,
                ))

        return Session(
            session_id=session_id,
            source=self.name,
            created_at=first_ts,
            metadata={
                "project": self._decode_project_name(project_name),
                "source_path": str(source_path),
            },
            rounds=rounds,
        )

    def _parse_content(self, data: dict, msg_type: str) -> list:
        blocks = []
        msg = data.get("message", {})

        if msg_type == "user":
            raw = msg.get("content", "")
            if isinstance(raw, str):
                if raw:
                    blocks.append(TextBlock(text=raw))
            else:
                blocks.append(TextBlock(text=json.dumps(raw)))

        elif msg_type == "assistant":
            parts = msg.get("content", [])
            if isinstance(parts, str):
                if parts:
                    blocks.append(TextBlock(text=parts))
            elif isinstance(parts, list):
                for part in parts:
                    if not isinstance(part, dict):
                        continue
                    pt = part.get("type")
                    if pt == "text":
                        text = part.get("text", "")
                        if text:
                            blocks.append(TextBlock(text=text))
                    elif pt == "tool_use":
                        blocks.append(ToolUseBlock(
                            name=part.get("name", "unknown"),
                            input=json.dumps(part.get("input", "")),
                        ))
                    elif pt == "tool_result":
                        blocks.append(ToolResultBlock(
                            output=str(part.get("content", "")),
                        ))

        return blocks

    def _parse_timestamp(self, ts_str: str) -> datetime | None:
        if not ts_str:
            return None
        try:
            return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _decode_project_name(self, name: str) -> str:
        username = os.getenv("USER") or os.getenv("USERNAME", "")
        prefix = f"-home-{username}-"
        if name.startswith(prefix):
            decoded = name.replace(prefix, f"/home/{username}/", 1)
            return decoded.replace("-", "/")
        return name
