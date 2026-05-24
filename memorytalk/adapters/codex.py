"""Codex CLI adapter — reads ``~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl``.

Codex stores one JSONL file per session, organized by date:

    ~/.codex/sessions/
    └── 2026/05/24/
        └── rollout-2026-05-24T01-20-24-019e5791-ab3d-76b1-8bcc-e0f410415f83.jsonl

Each line is an *envelope* with a ``type`` and a ``payload``:

    {"timestamp": "...", "type": "...", "payload": {...}}

Top-level envelope types (observed in v0.133.0 transcripts):

    session_meta         once per file; carries session id + cwd + system prompt
    turn_context         per turn; sandbox / approval / cwd snapshot
    event_msg            CLI-level events (task lifecycle, user/agent message,
                         token counts, turn aborted, …)
    response_item        raw API response items (message / function_call /
                         function_call_output / reasoning)

Round mapping — we deliberately pick ONE surface per kind of content to
avoid double-counting (events_msg/agent_message and response_item/message
role=assistant are two views of the same generation; we pick the cleaner
event_msg form for human-readable text):

    event_msg/user_message       → role=human,     speaker=user
    event_msg/agent_message      → role=assistant, speaker=assistant
    response_item/function_call  → role=assistant, speaker=assistant (tool_use block)
    response_item/function_call_output → role=tool, speaker=tool (tool_result block)
    response_item/reasoning      → role=assistant, speaker=assistant (thinking block)

Skipped envelopes (not a conversation round):

    session_meta                        — metadata, fed into the SourceProbe instead
    turn_context                        — per-turn config
    event_msg/task_started              — telemetry
    event_msg/task_complete             — telemetry
    event_msg/turn_aborted              — telemetry
    event_msg/token_count               — telemetry
    response_item/message role=*        — wire form of the message, already
                                          surfaced via event_msg/*_message;
                                          including it would double-count

round_id
========
Codex doesn't put a stable per-envelope id on event_msg items. We use
a 16-char SHA-256 prefix of the raw line bytes — deterministic per
line content, unique within a file, and round-trip-safe under our
"strictly append-only" sync model (the same line at the same offset
always hashes the same).

session_id_raw
==============
Extracted from the ``session_meta`` envelope (``payload.id``). The
filename also encodes it (``rollout-<ISO>-<uuid>.jsonl``) but the
in-file value is the source of truth.
"""
from __future__ import annotations
import datetime as _dt
import hashlib
import json
import re
from pathlib import Path
from typing import Iterator

from memorytalk.adapters.base import BaseAdapter, register
from memorytalk.schemas import ContentBlock, ReadAfterResult, RoundInput, SourceProbe


# Pulled out of the filename when the session_meta envelope is missing
# (truncated file, etc.). ``rollout-<ISO>-<uuid>.jsonl``.
_FILENAME_UUID_RE = re.compile(
    r"rollout-[\d-]+T[\d-]+-([0-9a-f-]{36})\.jsonl$"
)


@register
class CodexAdapter(BaseAdapter):
    source_name = "codex"
    DEFAULT_LOCATION = str(Path.home() / ".codex" / "sessions")

    @property
    def root(self) -> Path:
        return Path(self.location).expanduser()

    # ─── sync surface ────────────────────────────────────────────────

    def watch_roots(self) -> list[Path]:
        return [self.root]

    def list_sources(self) -> Iterator[SourceProbe]:
        if not self.root.exists():
            return
        # rollout-*.jsonl files are scattered under YYYY/MM/DD/ subdirs.
        for path in sorted(self.root.rglob("rollout-*.jsonl")):
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

        session_meta = self._find_first_session_meta(raw_bytes)
        if session_meta is not None:
            session_id = session_meta.get("id") or self._uuid_from_filename(path)
            cwd = session_meta.get("cwd")
            created_at = (
                session_meta.get("timestamp")
                or _envelope_top_timestamp(raw_bytes)
                or ""
            )
        else:
            # Truncated / corrupt file — fall back to filename parse so
            # we don't lose track of the session entirely.
            session_id = self._uuid_from_filename(path)
            cwd = None
            created_at = _envelope_top_timestamp(raw_bytes) or ""

        if session_id is None:
            return None

        metadata: dict = {"path": str(path)}
        if cwd:
            metadata["cwd"] = cwd
        if session_meta:
            for k in ("cli_version", "originator", "model_provider"):
                v = session_meta.get(k)
                if v:
                    metadata[k] = v

        return SourceProbe(
            source_id=str(path),
            session_id=session_id,
            sha256=sha256,
            created_at=created_at,
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

        lines = raw.splitlines(keepends=True)
        rounds: list[RoundInput] = []
        next_offset = 0
        started = after_round_id is None

        # Walk every envelope. Each one we decide to keep becomes a
        # RoundInput with a deterministic line-hash round_id. ``started``
        # flips true once we see ``after_round_id`` in the stream (we
        # skip up to + including it).
        cursor = 0
        for line in lines:
            line_start = cursor
            cursor += len(line)
            text = line.strip()
            if not text:
                continue
            try:
                envelope = json.loads(text)
            except json.JSONDecodeError:
                continue
            round_id = _line_round_id(text)
            if not started:
                if round_id == after_round_id:
                    started = True
                continue
            parsed = self._parse_envelope(envelope, round_id, line_start)
            if parsed is not None:
                rounds.append(parsed)
        next_offset = cursor
        return ReadAfterResult(rounds=rounds, next_line_offset=next_offset)

    # ─── parsing helpers ─────────────────────────────────────────────

    def _parse_envelope(
        self, envelope: dict, round_id: str, line_offset: int,
    ) -> RoundInput | None:
        """Map a codex envelope to a RoundInput, or None to skip."""
        t = envelope.get("type")
        payload = envelope.get("payload") or {}
        pt = payload.get("type")
        ts = envelope.get("timestamp")

        # ── skip envelopes ────────────────────────────────────────────
        if t in ("session_meta", "turn_context"):
            return None
        if t == "event_msg" and pt in (
            "task_started", "task_complete", "turn_aborted", "token_count",
        ):
            return None
        if t == "response_item" and pt == "message":
            # Wire form — duplicates the event_msg user/agent surface.
            # The exceptions (developer / system prompts injected by
            # the harness) are still skipped: they're not user-visible
            # conversation, just config that the LLM saw.
            return None

        # ── real human / agent text ───────────────────────────────────
        if t == "event_msg" and pt == "user_message":
            text = payload.get("message") or ""
            return _make_round(
                round_id, ts, "human", "user",
                [{"type": "text", "text": text}],
            )
        if t == "event_msg" and pt == "agent_message":
            text = payload.get("message") or ""
            return _make_round(
                round_id, ts, "assistant", "assistant",
                [{"type": "text", "text": text}],
            )

        # ── assistant tool call ───────────────────────────────────────
        if t == "response_item" and pt == "function_call":
            name = payload.get("name") or "function"
            args = payload.get("arguments") or ""
            return _make_round(
                round_id, ts, "assistant", "assistant",
                [{"type": "tool_use", "name": name, "input": args,
                  "text": f"[{name}] {args}"}],
            )

        # ── tool result ───────────────────────────────────────────────
        if t == "response_item" and pt == "function_call_output":
            output = payload.get("output") or ""
            if not isinstance(output, str):
                output = json.dumps(output, ensure_ascii=False)
            return _make_round(
                round_id, ts, "tool", "tool",
                [{"type": "tool_result", "text": output}],
            )

        # ── assistant reasoning ───────────────────────────────────────
        if t == "response_item" and pt == "reasoning":
            # ``content`` may be a list of summary blocks; usually empty
            # with the actual reasoning in ``encrypted_content`` (opaque).
            summary = payload.get("summary") or []
            text_parts: list[str] = []
            for s in summary:
                if isinstance(s, dict) and s.get("text"):
                    text_parts.append(s["text"])
            if not text_parts and payload.get("encrypted_content"):
                # Mark as opaque so downstream knows reasoning was here
                # but isn't readable. (We don't store the encrypted
                # blob — it bloats jsonl with non-searchable bytes.)
                thinking = "[encrypted reasoning]"
            else:
                thinking = "\n\n".join(text_parts) or "[empty reasoning]"
            return _make_round(
                round_id, ts, "assistant", "assistant",
                [{"type": "thinking", "thinking": thinking}],
            )

        # Unknown envelope type — skip safely; new codex versions may add
        # types we don't yet recognize. Don't fail the whole file.
        return None

    @staticmethod
    def _find_first_session_meta(raw_bytes: bytes) -> dict | None:
        for line in raw_bytes.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "session_meta":
                return msg.get("payload") or {}
        return None

    @staticmethod
    def _uuid_from_filename(path: Path) -> str | None:
        m = _FILENAME_UUID_RE.search(path.name)
        return m.group(1) if m else None


# ─── shared helpers ─────────────────────────────────────────────────


def _line_round_id(line_text: str) -> str:
    """16-char SHA-256 prefix of a JSONL line. Deterministic + unique
    within a session file (lines differ at least in their timestamp)."""
    return hashlib.sha256(line_text.encode("utf-8")).hexdigest()[:16]


def _envelope_top_timestamp(raw_bytes: bytes) -> str | None:
    """First ``envelope.timestamp`` we can parse — fallback for
    ``created_at`` when ``session_meta`` is missing."""
    for line in raw_bytes.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("timestamp"):
            return msg["timestamp"]
    return None


def _make_round(
    round_id: str,
    timestamp: str | None,
    role: str,
    speaker: str,
    content: list[dict],
) -> RoundInput:
    return RoundInput(
        round_id=round_id,
        parent_id=None,  # codex doesn't carry a parent chain on event_msg
        timestamp=timestamp,
        speaker=speaker,
        role=role,
        content=[ContentBlock(**b) for b in content],
        is_sidechain=False,
        cwd=None,
    )
