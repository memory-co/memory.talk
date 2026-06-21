"""SessionMarkService — the v4 session-mark write path ("以写代读").

A submission = ONE mark for one session. The server auto-assigns its id
``m<n>`` (``next_seq`` = COUNT+1: first pass ``m1``, next ``m2``…); the
client never provides it. The submission walks the session's rounds from
index 1; each round carries an optional ``comment`` (``#…？`` parsed into
issues, grounded at the round's own ``index``) and/or explicit
``issues: [{issue, indexes?}]``. On write every resolved issue is embedded
and collided against the ``cards`` (issue) vector library:

  miss (relevance < θ)  → create a NEW card        (is_new=True)
  hit  (relevance >= θ) → link the EXISTING card   (is_new=False)

…and a ``card_sessions`` row records the provenance edge
``(card_id, session_id, mark, indexes)`` — granular to *that mark*. If
multiple rounds in the SAME mark reference the SAME card, their grounding
rounds MERGE into one ``indexes`` string (PK is ``(card_id, session_id,
mark)`` — one row per (card, session, mark)). The mark body (incl. each
round's resolved ``issues[]``) is written canonical to ``marks/<mark>.yaml``;
``session_marks`` holds its metadata.

Ordering & invariants (docs/works/v4/session-mark.md):
  1. Optimistic lock: ``last_index`` must equal the session's current max
     round index (== ``round_count``, rounds are 1-indexed). Mismatch →
     ``MarkConflict`` (409). Nothing is written.
  2. ``rounds`` validation (reject the WHOLE submission → 400, before any
     write): the first entry's ``index`` must be ``1`` (starting mid-session
     = skipping = reject); ``index`` strictly ascending, no duplicates, each
     in ``[1, last_index]``.
  2b. Round coverage (以写代读): ``len(distinct index) >= ceil(
     MARK_COVERAGE_THRESHOLD * last_index)`` (90%). Under → ``MarkServiceError``
     (400) before any write.
  3. Atomic write, in two phases. (a) RESOLUTION: embed/collide every issue
     (from ``#…？`` comments + explicit ``issues``) of every round UP FRONT —
     before any submission-level write. (b) WRITE: only then insert the
     ``session_marks`` row (mints ``m<n>``), the merged ``card_sessions``
     edges, and ``marks/<mark>.yaml``. A provider failure mid-resolution
     raises before phase (b) → NONE of the submission's
     session_marks/card_sessions/yaml is written (整份拒绝).

Embedding degradation (503): if searchbase is unavailable, or the embedding
provider fails mid-resolution, the issue can't be collided → the submission
is rejected with ``MarkUnavailable`` during phase (a), before any write, so
state never corrupts. A submission whose rounds carry no issues needs no
searchbase and always proceeds.
"""
from __future__ import annotations

import datetime as _dt
import math

from memorytalk.repository import SQLiteStore
from memorytalk.schemas.card_requests import CreateCardRequest
from memorytalk.searchbase import SearchBackend
from memorytalk.service.cards import CardService
from memorytalk.service.searchbase_schema import (
    CARD_ISSUE_HIT_THRESHOLD, V4_CARDS,
)
from memorytalk.util.indexes import IndexesParseError, parse_indexes
from memorytalk.util.marks import parse_issues


def _utc_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class MarkServiceError(Exception):
    """400-equivalent: validation failed, submission rejected."""


class MarkNotFound(MarkServiceError):
    """404-equivalent: the session doesn't exist."""


class MarkConflict(MarkServiceError):
    """409-equivalent: optimistic lock failed (session advanced)."""


class MarkUnavailable(MarkServiceError):
    """503-equivalent: searchbase/embedding unavailable; can't collide issues."""


# 以写代读 means you must read the WHOLE session — submitting marks for only the
# first few rounds of a long session defeats it. A submission must therefore
# cover ≥90% of the session's rounds (distinct round ``index`` over
# ``[1, last_index]``). Tune here.
MARK_COVERAGE_THRESHOLD = 0.9


class SessionMarkService:
    def __init__(
        self, db: SQLiteStore, search: SearchBackend | None, cards: CardService,
    ):
        self.db = db
        self.search = search
        self.cards = cards

    # ────────── submit ──────────

    async def submit_marks(
        self, session_id: str, last_index: int, description: str,
        rounds: list[dict],
    ) -> dict:
        """Optimistically-locked write of ONE mark (a per-round annotation of
        the whole session). The server auto-assigns the mark id ``m<n>``.
        Returns ``{session_id, mark, rounds:[{index, comment?, issues:[…]}]}``
        (each issue carries the server-filled ``card_id`` / ``is_new``)."""
        session = await self.db.sessions.get(session_id)
        if session is None:
            raise MarkNotFound(f"session {session_id} not found")
        source = session["source"]

        # 1. optimistic lock — last_index must match the current max round
        #    index (rounds are 1-indexed → max == round_count).
        current = session.get("round_count") or 0
        if last_index != current:
            raise MarkConflict(
                f"session advanced (last_index {last_index} ≠ current {current}); "
                "re-read & re-mark",
            )

        # 2. validate ``rounds`` up front — first index must be 1, strictly
        #    ascending, no dups, each in [1, last_index]. Reject the WHOLE
        #    submission *before* any write so a bad batch leaves no partial
        #    state. Resolve each round's issues (comment #…？ + explicit
        #    issues) into (text, grounding-indexes) pairs.
        if not rounds:
            raise MarkServiceError("rounds required")

        parsed: list[dict] = []   # [{index, comment, issue_decls:[(text, idx)]}]
        prev = 0
        for entry in rounds:
            idx = entry.get("index")
            if not isinstance(idx, int):
                raise MarkServiceError(f"round index required (int), got {idx!r}")
            if not parsed and idx != 1:
                # First round must be 1 — starting mid-session is skipping.
                raise MarkServiceError(
                    f"first round index must be 1 (got {idx}); "
                    "read from the session's first round",
                )
            if idx <= prev:
                raise MarkServiceError(
                    f"round index must be strictly ascending, no dups "
                    f"(got {idx} after {prev})",
                )
            if last_index > 0 and not (1 <= idx <= last_index):
                raise MarkServiceError(
                    f"round index {idx} out of range [1, {last_index}]",
                )
            prev = idx

            comment = entry.get("comment") or ""
            # Two sources of issues, both processed:
            #  ① #…？ parsed from the comment → grounds at THIS round's index.
            #  ② explicit issues: [{issue, indexes?}] → grounds at the given
            #     indexes, else this round's index.
            decls: list[tuple[str, str]] = []
            for issue in (parse_issues(comment) if comment else []):
                decls.append((issue, str(idx)))
            for d in entry.get("issues") or []:
                text = d.get("issue")
                if not text:
                    raise MarkServiceError(
                        f"round {idx}: explicit issue needs non-empty 'issue'",
                    )
                raw = d.get("indexes")
                gidx = str(raw) if raw else str(idx)
                # Validate the grounding indexes parse (same syntax as reviews).
                try:
                    parse_indexes(gidx)
                except IndexesParseError as e:
                    raise MarkServiceError(f"round {idx}: {e}") from e
                decls.append((text, gidx))
            parsed.append({"index": idx, "comment": comment, "decls": decls})

        # 2b. ROUND-COVERAGE — distinct round ``index`` must cover ≥90% of the
        #     session's rounds (以写代读: read the whole session). Reject the
        #     WHOLE submission BEFORE any write if under threshold.
        if last_index > 0:
            covered = len(parsed)   # already deduped (strictly ascending)
            need = math.ceil(MARK_COVERAGE_THRESHOLD * last_index)
            if covered < need:
                pct = round(100 * covered / last_index)
                raise MarkServiceError(
                    f"coverage {pct}% ({covered}/{last_index} rounds) "
                    f"< {round(MARK_COVERAGE_THRESHOLD * 100)}%",
                )

        has_issues = any(p["decls"] for p in parsed)
        # Degrade cleanly: if any round carries issues but we can't collide
        # them, reject the whole submission before writing anything.
        if self.search is None and has_issues:
            raise MarkUnavailable("searchbase unavailable; cannot resolve #…？ issues")

        # 3a. RESOLUTION PHASE — embed + nearest-collide + create/link every
        #     issue UP FRONT, before any submission-level write. If embedding
        #     raises mid-batch we surface MarkUnavailable here, having written
        #     NONE of the submission's session_marks / card_sessions / yaml.
        #     (create_card may mint a card row mid-resolution — that's the only
        #     pre-commit write, and an orphaned issue-card is harmless on retry.)
        for p in parsed:
            resolved = []
            for (text, gidx) in p["decls"]:
                try:
                    card_id, is_new = await self._resolve_issue(text)
                except MarkUnavailable:
                    raise
                except Exception as e:   # embedding / collision blew up
                    raise MarkUnavailable(
                        f"embedding/collision failed while resolving #…？: {e}",
                    ) from e
                resolved.append({
                    "issue": text, "card_id": card_id, "is_new": is_new,
                    "indexes": gidx,
                })
            p["resolved"] = resolved

        # 3b. WRITE PHASE — every issue is resolved; nothing below embeds, so
        #     these writes are local + ordered. One session_marks row (mints
        #     m<n>); one MERGED card_sessions row per (card, this mark).
        now = _utc_iso()
        mark = await self.db.session_marks.insert(session_id, last_index, now)

        # Merge per-card across all rounds of THIS mark: if rounds 37 & 50 both
        # hit the same card, the card_sessions row gets indexes "37,50" (PK is
        # (card_id, session_id, mark) — one row per card per mark).
        merged: dict[str, list[str]] = {}
        for p in parsed:
            for r in p["resolved"]:
                merged.setdefault(r["card_id"], []).append(r["indexes"])
        for card_id, idx_list in merged.items():
            await self.db.card_sessions.insert(
                card_id, session_id, mark, ",".join(idx_list), now,
            )

        out_rounds: list[dict] = []
        body_rounds: list[dict] = []
        for p in parsed:
            entry: dict = {"index": p["index"]}
            if p["comment"]:
                entry["comment"] = p["comment"]
            if p["resolved"]:
                entry["issues"] = p["resolved"]
            body_rounds.append(entry)
            out_rounds.append({
                "index": p["index"],
                **({"comment": p["comment"]} if p["comment"] else {}),
                "issues": p["resolved"],
            })

        body = {
            "last_index": last_index,
            "description": description,
            "created_at": now,
            "rounds": body_rounds,
        }
        await self.db.session_mark_files.write_doc(source, session_id, mark, body)

        return {"session_id": session_id, "mark": mark, "rounds": out_rounds}

    async def _resolve_issue(self, issue: str) -> tuple[str, bool]:
        """Embed + nearest-neighbor an issue against the ``cards`` library.
        Returns ``(card_id, is_new)``: hit (cosine similarity ≥ θ) → the
        closest existing card; miss → mint a new card. Uses pure-vector
        ``nearest`` (not hybrid ``search``) so the score is a thresholdable
        cosine similarity. Assumes ``self.search`` is set (callers gate)."""
        hits = await self.search.nearest(V4_CARDS, issue, top_k=1)
        if hits and hits[0].id and hits[0].score >= CARD_ISSUE_HIT_THRESHOLD:
            return hits[0].id, False
        card_id = await self.cards.create_card(CreateCardRequest(issue=issue))
        return card_id, True

    # ────────── clear ──────────

    async def clear_marks(self, session_id: str) -> dict:
        """Remove ALL marks for a session: every ``marks/*.yaml`` file, every
        ``session_marks`` row, and every ``card_sessions`` row WHERE
        session_id. Leaves cards / positions / reviews / links untouched.
        404 if the session doesn't exist; clearing a session with no marks is
        a no-op success (``deleted_marks: 0``)."""
        session = await self.db.sessions.get(session_id)
        if session is None:
            raise MarkNotFound(f"session {session_id} not found")
        source = session["source"]

        rows = await self.db.session_marks.list_for_session(session_id)
        n = len(rows)

        await self.db.session_mark_files.delete_all(source, session_id)
        await self.db.session_marks.delete_for_session(session_id)
        await self.db.card_sessions.delete_for_session(session_id)

        return {"session_id": session_id, "deleted_marks": n}

    # ────────── list / read ──────────

    async def list_marks(self, session_id: str) -> dict:
        """Mark metadata for ``GET …/marks`` (from ``session_marks``)."""
        if await self.db.sessions.get(session_id) is None:
            raise MarkNotFound(f"session {session_id} not found")
        rows = await self.db.session_marks.list_for_session(session_id)
        return {
            "session_id": session_id,
            "marks": [
                {"mark": r["mark"], "last_index": r["last_index"],
                 "created_at": r["created_at"]}
                for r in rows
            ],
        }

    async def read_mark(self, session_id: str, mark: str) -> dict | None:
        """Read one mark's canonical YAML (``read sess_…#m<n>``). Returns the
        body dict (last_index / description / created_at / rounds[]) or None
        when the session or mark is missing."""
        session = await self.db.sessions.get(session_id)
        if session is None:
            return None
        return await self.db.session_mark_files.read_doc(
            session["source"], session_id, mark,
        )
