"""Claude Code adapter.

Reads ``~/.claude/projects/*/*.jsonl`` conversation files and produces
ingest payloads. Each ``.jsonl`` file is one session; each line is one
platform message; ``round_id = uuid`` from the message.

Round-level layout:

- ``content`` block preservation matches the v3 ContentBlock schema —
  tool_use / tool_result remain typed so future search / display can
  render them with their original semantics (text projection is built
  separately for FTS).
- ``metadata.cwd`` is extracted from the first message that carries
  a ``cwd`` field so the explore namespace check works without the
  server having to dig into each round.
- ``role`` / ``speaker`` for ``type:"user"`` rows is **not** simply
  "human" — Claude Code transcripts pack four distinct things into the
  user-role bucket (real human input, tool_result echo-back, harness-
  injected slash command artifacts, status messages). See
  ``_classify_user_message`` for the disambiguation logic.

Cursor semantics:

- ``source_id`` = absolute file path string.
- ``sha256``    = sha256 of the file's raw bytes (used by sync to
  short-circuit "did anything change").
- ``after_round_id`` is the platform uuid of the last round the server
  already stored. ``hint_line_offset`` is the line number sync cached
  the last time it read this file — we use it as a fast-seek hint
  but always validate before trusting it.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Iterator
from urllib.parse import unquote

from memorytalk.adapters.base import BaseAdapter, register
from memorytalk.schemas import (
    ContentBlock, ReadAfterResult, RoundInput, SourceProbe,
)


def _classify_user_message(msg: dict) -> tuple[str, str]:
    """Classify a ``type:"user"`` Claude Code message into (role, speaker).

    The Anthropic Messages API only has user / assistant roles. Claude
    Code persists raw API payloads verbatim, so on disk ``type:"user"``
    is a 4-way bucket:

      1. tool_result echo-back (model's tool call output reflected back
         into the user-side payload by the API protocol)
      2. CLI-injected caveat (``isMeta`` flag set on harness messages)
      3. Slash command artifacts the harness wraps in ``<command-name>``
         / ``<local-command-stdout>`` / ``<local-command-caveat>`` /
         ``[Request interrupted by user]`` text
      4. Actual human keyboard input

    Priority order below favors the most stable signal: ``toolUseResult``
    is a CLI-level field that survives Anthropic API content-shape
    changes; the content-block ``type`` is the API-level fallback; text
    prefixes are last because they're brittle to harness rebranding
    (tests in ``tests/adapters/test_claude_code.py`` catch regressions).
    """
    # 1. tool_result (CLI-level signal, most stable)
    if "toolUseResult" in msg:
        return ("tool", "tool")
    content = msg.get("message", {}).get("content", [])
    if (
        isinstance(content, list) and content
        and isinstance(content[0], dict)
        and content[0].get("type") == "tool_result"
    ):
        return ("tool", "tool")

    # 2. CLI-flagged meta (caveat etc.)
    if msg.get("isMeta"):
        return ("system", "harness")

    # 3. Harness-injected slash-command artifacts — text prefix only.
    text: str | None = None
    if isinstance(content, str):
        text = content
    elif (
        isinstance(content, list) and content
        and isinstance(content[0], dict)
        and content[0].get("type") == "text"
    ):
        text = content[0].get("text", "")
    if text:
        stripped = text.lstrip()
        for prefix in (
            "<command-name>",
            "<local-command-stdout>",
            "<local-command-caveat>",
            "[Request interrupted by user]",
        ):
            if stripped.startswith(prefix):
                return ("system", "harness")

    # 4. Default — actual human input.
    return ("human", "user")


@register
class ClaudeCodeAdapter(BaseAdapter):
    source_name = "claude-code"

    DEFAULT_ROOT = Path.home() / ".claude" / "projects"

    # ────────── sync-facing surface ──────────

    def watch_roots(self) -> list[Path]:
        return [self.DEFAULT_ROOT]

    def list_sources(self) -> Iterator[SourceProbe]:
        if not self.DEFAULT_ROOT.exists():
            return
        for path in sorted(self.DEFAULT_ROOT.rglob("*.jsonl")):
            probe = self.probe(str(path))
            if probe is not None:
                yield probe

    def probe(self, source_id: str) -> SourceProbe | None:
        path = Path(source_id)
        if path.suffix != ".jsonl":
            return None
        try:
            raw_bytes = path.read_bytes()
        except FileNotFoundError:
            return None
        if not raw_bytes:
            return None
        sha256 = hashlib.sha256(raw_bytes).hexdigest()
        session_id = path.stem  # platform uuid, no prefix
        project_name = unquote(path.parent.name)

        # Pull created_at + cwd from the first parseable message.
        created_at: str | None = None
        cwd: str | None = None
        for line in raw_bytes.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if created_at is None and msg.get("timestamp"):
                created_at = msg["timestamp"]
            if cwd is None and msg.get("cwd"):
                cwd = msg["cwd"]
            if created_at is not None and cwd is not None:
                break

        metadata: dict = {"project": project_name, "path": str(path)}
        if cwd:
            metadata["cwd"] = cwd

        return SourceProbe(
            source_id=str(path),
            session_id=session_id,
            sha256=sha256,
            created_at=created_at or "",
            metadata=metadata,
        )

    def read_after(
        self,
        source_id: str,
        after_round_id: str | None,
        hint_line_offset: int = 0,
    ) -> ReadAfterResult:
        path = Path(source_id)
        if path.suffix != ".jsonl":
            return ReadAfterResult(rounds=[], next_line_offset=0)
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return ReadAfterResult(rounds=[], next_line_offset=0)
        lines = raw.splitlines()

        start_line = self._locate_start(lines, after_round_id, hint_line_offset)

        rounds: list[RoundInput] = []
        cursor = start_line
        for cursor in range(start_line, len(lines)):
            line = lines[cursor].strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            parsed = self._parse_message(msg)
            if parsed is None:
                continue
            rounds.append(parsed)

        return ReadAfterResult(rounds=rounds, next_line_offset=len(lines))

    # ────────── seek / parse helpers ──────────

    def _locate_start(
        self,
        lines: list[str],
        after_round_id: str | None,
        hint_line_offset: int,
    ) -> int:
        """Return the index of the first line whose round should be
        yielded (i.e., the line strictly after the one carrying
        ``after_round_id``).

        Strategy:
          - If ``after_round_id`` is None → start at 0 (full read).
          - Otherwise: trust ``hint_line_offset`` only if line[hint-1]
            actually carries ``after_round_id``. If it doesn't (file got
            rewritten, hint stale, ...), scan from the top to find the
            marker. If marker not found anywhere → start at 0.
        """
        if after_round_id is None:
            return 0

        if 0 < hint_line_offset <= len(lines):
            if self._line_round_id(lines[hint_line_offset - 1]) == after_round_id:
                return hint_line_offset

        for i, line in enumerate(lines):
            if self._line_round_id(line) == after_round_id:
                return i + 1
        # Marker not in the file at all — caller has a stale cursor.
        # Treat as fresh ingest so the conflict-retry path kicks in.
        return 0

    @staticmethod
    def _line_round_id(line: str) -> str | None:
        line = line.strip()
        if not line:
            return None
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            return None
        return msg.get("uuid") or None

    # ────────── per-message parsing ──────────

    def _parse_message(self, msg: dict) -> RoundInput | None:
        msg_type = msg.get("type")
        if msg_type not in ("user", "assistant"):
            return None
        if msg_type == "assistant":
            role, speaker = "assistant", "assistant"
        else:
            role, speaker = _classify_user_message(msg)
        raw_content = msg.get("message", {}).get("content", [])
        blocks = self._parse_content(raw_content)
        if not blocks:
            if isinstance(raw_content, str):
                blocks = [{"type": "text", "text": raw_content}]
            else:
                return None
        return RoundInput(
            round_id=msg.get("uuid", ""),
            parent_id=msg.get("parentUuid"),
            timestamp=msg.get("timestamp"),
            speaker=speaker,
            role=role,
            content=[ContentBlock(**b) for b in blocks],
            is_sidechain=bool(msg.get("isSidechain")),
            cwd=msg.get("cwd"),
        )

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
                # Keep typed; carry text for FTS.
                out.append({"type": "tool_use", "name": name, "input": inp,
                            "text": f"[{name}] {inp}"})
            elif t == "tool_result":
                c = block.get("content", "")
                if isinstance(c, list):
                    c = json.dumps(c, ensure_ascii=False)
                out.append({"type": "tool_result", "text": str(c)})
        return out
