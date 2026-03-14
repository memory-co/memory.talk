#!/usr/bin/env python3
"""
Export all Claude Code sessions to memory-talk server.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
API_URL = "http://localhost:7788"
PLATFORM = "claude-code"


def decode_project_name(name: str, username: str) -> str:
    """Decode project directory name back to original path."""
    prefix = f"-home-{username}-"
    if name.startswith(prefix):
        decoded = name.replace(prefix, f"/home/{username}/")
        decoded = decoded.replace("-", "/")
        return decoded
    elif name == "-tmp":
        return "/tmp"
    return name


def parse_messages(jsonl_path: Path) -> list[dict]:
    """Parse messages from a session JSONL file."""
    messages = []
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    msg_type = data.get("type")
                    if msg_type not in ("user", "assistant"):
                        continue

                    # Extract content - convert to string if needed
                    content = ""
                    if msg_type == "user":
                        msg_content = data.get("message", {})
                        raw_content = msg_content.get("content", "")
                        # Convert to string if it's not already
                        if not isinstance(raw_content, str):
                            content = json.dumps(raw_content)
                        else:
                            content = raw_content
                    elif msg_type == "assistant":
                        msg_content = data.get("message", {})
                        content_parts = msg_content.get("content", [])
                        if isinstance(content_parts, list):
                            # Extract text from content parts
                            for part in content_parts:
                                if isinstance(part, dict):
                                    part_type = part.get("type")
                                    if part_type == "text":
                                        content += part.get("text", "")
                                    elif part_type == "thinking":
                                        content += part.get("thinking", "")
                                    elif part_type == "tool_use":
                                        content += f"[tool_use: {part.get('name', 'unknown')}]"
                                    elif part_type == "tool_result":
                                        content += f"[tool_result: {part.get('content', '')}]"
                        elif isinstance(content_parts, str):
                            content = content_parts

                    # Ensure content is a string
                    if not isinstance(content, str):
                        content = str(content)

                    # Parse timestamp
                    timestamp_str = data.get("timestamp", "")
                    if timestamp_str:
                        try:
                            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                        except ValueError:
                            timestamp = datetime.now()
                    else:
                        timestamp = datetime.now()

                    messages.append({
                        "uuid": data.get("uuid", ""),
                        "parent_uuid": data.get("parentUuid"),
                        "role": msg_type,
                        "content": content,
                        "timestamp": timestamp.isoformat(),
                    })
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"Error reading {jsonl_path}: {e}", file=sys.stderr)

    return messages


def export_session(jsonl_path: Path, session_id: str, project_path: str) -> bool:
    """Export a single session to the API."""
    messages = parse_messages(jsonl_path)
    if not messages:
        return False

    payload = {
        "platform": PLATFORM,
        "conversation_id": session_id,
        "messages": messages,
        "metadata": {
            "title": f"Claude Code - {project_path}",
            "project_path": project_path,
        }
    }

    try:
        response = requests.post(f"{API_URL}/api/v1/ingest", json=payload, timeout=30)
        if response.status_code == 200:
            return True
        else:
            print(f"Error exporting {session_id}: {response.status_code} - {response.text}", file=sys.stderr)
            return False
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to API: {e}", file=sys.stderr)
        return False


def export_all_sessions():
    """Export all Claude Code sessions to memory-talk server."""
    if not CLAUDE_PROJECTS_DIR.exists():
        print(f"Claude projects directory not found: {CLAUDE_PROJECTS_DIR}")
        sys.exit(1)

    # Check API availability
    try:
        response = requests.get(f"{API_URL}/api/v1/status", timeout=5)
        if response.status_code != 200:
            print(f"API error: {response.status_code}")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"Cannot connect to API at {API_URL}: {e}")
        sys.exit(1)

    username = os.getenv("USER") or os.getenv("USERNAME") or os.getlogin()
    projects = sorted(CLAUDE_PROJECTS_DIR.iterdir(), key=lambda x: x.name)

    total_exported = 0
    total_sessions = 0

    print(f"Exporting sessions to {API_URL}...")
    print("-" * 60)

    for project in projects:
        if not project.is_dir():
            continue

        original_path = decode_project_name(project.name, username)
        sessions = list(project.glob("*.jsonl"))

        for session_file in sessions:
            session_id = session_file.stem
            total_sessions += 1

            if export_session(session_file, session_id, original_path):
                total_exported += 1
                print(f"Exported: {original_path} / {session_id}")

    print("-" * 60)
    print(f"Exported {total_exported}/{total_sessions} sessions")


if __name__ == "__main__":
    export_all_sessions()
