#!/usr/bin/env python3
"""
List all Claude Code sessions with their associated directories and message counts.
"""

import os
import json
from pathlib import Path

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"


def decode_project_name(name: str, username: str) -> str:
    """Decode project directory name back to original path."""
    import os

    # Try to decode Claude Code's project naming pattern
    # Format: -home-{username}-{rest} or -home-twwyzh-{rest}
    prefix = f"-home-{username}-"
    if name.startswith(prefix):
        decoded = name.replace(prefix, f"/home/{username}/")
        decoded = decoded.replace("-", "/")
        return decoded
    elif name == "-tmp":
        return "/tmp"
    return name


def count_messages(jsonl_path: Path) -> int:
    """Count messages in a jsonl session file."""
    try:
        count = 0
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count
    except Exception:
        return 0


def list_sessions():
    """List all Claude Code sessions."""
    import os

    if not CLAUDE_PROJECTS_DIR.exists():
        print(f"Claude projects directory not found: {CLAUDE_PROJECTS_DIR}")
        return

    # Get current username
    username = os.getenv("USER") or os.getenv("USERNAME") or os.getlogin()

    projects = sorted(CLAUDE_PROJECTS_DIR.iterdir(), key=lambda x: x.name)

    print(f"{'Directory':<50} {'Sessions':<10} {'Messages':<10}")
    print("-" * 72)

    total_sessions = 0
    total_messages = 0

    for project in projects:
        if not project.is_dir():
            continue

        # Decode directory name to original path
        original_path = decode_project_name(project.name, username)

        # Count session files (.jsonl)
        sessions = list(project.glob("*.jsonl"))
        session_count = len(sessions)

        # Count total messages
        message_count = sum(count_messages(s) for s in sessions)

        total_sessions += session_count
        total_messages += message_count

        print(f"{original_path:<50} {session_count:<10} {message_count:<10}")

    print("-" * 72)
    print(f"{'Total':<50} {total_sessions:<10} {total_messages:<10}")


if __name__ == "__main__":
    list_sessions()
