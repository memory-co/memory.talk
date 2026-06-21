"""SessionMarkService — the v4 session-mark write path ("以写代读").

A submission = one optimistic-locked batch of marks for one session. Each
mark's free text carries ``#…？`` issues; on write every issue is embedded
and collided against the ``cards`` (issue) vector library:

  miss (relevance < θ)  → create a NEW card        (is_new=True)
  hit  (relevance >= θ) → link the EXISTING card   (is_new=False)

…and either way a ``card_sessions`` row records the provenance edge
``(card_id, session_id, mark, indexes)`` — granular to *that mark*. The
mark body (incl. resolved ``issues[]``) is written canonical to
``marks/<mark>.yaml``; ``session_marks`` holds its metadata.

Ordering & invariants (docs/works/v4/session-mark.md):
  1. Optimistic lock: ``last_index`` must equal the session's current max
     round index (== ``round_count``, rounds are 1-indexed). Mismatch →
     ``MarkConflict`` (409). Nothing is written.
  2. Validate every ``id``: explicit ``m<n>``, session-monotonic, no
     skip/reuse. The next id must equal ``next_seq`` (count+1) at the time
     that mark is inserted. Bad → ``MarkServiceError`` (400). Validated up
     front before any write, so a bad batch writes nothing. ``indexes`` is
     required on EVERY mark; ``mark`` text is optional (an id-only entry
     records coverage but carries no #…？ → no issues / cards).
  2b. Round coverage (以写代读): the union of every mark's ``indexes`` over
     ``[1, last_index]`` must cover ≥ ``MARK_COVERAGE_THRESHOLD`` (90%) of the
     session's rounds. Under → ``MarkServiceError`` (400) before any write.
  3. Atomic write, in two phases. (a) RESOLUTION: embed/collide every
     ``#…？`` issue of every mark and create/link its card UP FRONT — before
     any submission-level write. (b) WRITE: only then, per mark in order,
     insert the ``session_marks`` row (mints the same ``m<n>``), the
     ``card_sessions`` edges, and ``marks/<mark>.yaml``. Because all embedding
     happens in phase (a), a provider failure mid-batch raises before phase
     (b) starts → NONE of the batch's session_marks/card_sessions/yaml is
     written (整份拒绝 / 不写任何东西).

Embedding degradation (503): if searchbase is unavailable, or the embedding
provider fails mid-resolution, the issue can't be collided. Rather than
silently mis-classify (or leave a half-written batch), the submission is
rejected with ``MarkUnavailable`` during phase (a), before any
session_marks/card_sessions/yaml write — so state never corrupts. A
submission whose marks carry no ``#…？`` needs no searchbase and always
proceeds.
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
from memorytalk.util.ids import (
    MARK_SEQ_PREFIX, SESSION_PREFIX, SESSION_PREFIX_LEGACY, mark_seq,
)
from memorytalk.util.indexes import IndexesParseError, parse_indexes
from memorytalk.util.marks import parse_issues


def _utc_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _seq_int(seq: str) -> int:
    """``'m3'`` → ``3`` (the int after the ``m`` seq prefix)."""
    return int(seq[len(MARK_SEQ_PREFIX):])


def _is_session_id(sid: str) -> bool:
    return sid.startswith(SESSION_PREFIX) or sid.startswith(SESSION_PREFIX_LEGACY)


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
# cover ≥90% of the session's rounds (the union of every mark's ``indexes``
# over ``[1, last_index]``). Tune here.
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
        marks: list[dict],
    ) -> dict:
        """Optimistically-locked write of a batch of marks. Returns the
        per-mark resolved ``issues[]`` (see module docstring)."""
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

        # 2. validate the batch up front — non-empty, explicit monotonic ids,
        #    and (per mark) parseable issues + indexes. Reject *before* any
        #    write so a bad batch leaves no partial state.
        if not marks:
            raise MarkServiceError("marks required")
        # The first id this batch must use is the store's next seq (a cheap
        # COUNT(*) the store mints from); subsequent marks step monotonically
        # from there. Reusing ``next_seq`` keeps validation and minting in
        # lockstep.
        next_n = _seq_int(await self.db.session_marks.next_seq(session_id))
        parsed: list[dict] = []
        covered: set[int] = set()
        for m in marks:
            mid = m.get("id")
            expected = mark_seq(next_n)
            if not mid or mid != expected:
                raise MarkServiceError(
                    "mark id required and must be monotonic (m<n>); "
                    f"expected {expected!r}, got {mid!r}",
                )
            text = m.get("mark") or ""
            # #…？ → cards runs ONLY on entries that carry mark text. An id-only
            # entry (no/empty ``mark``) records coverage but creates no issues.
            issues = parse_issues(text) if text else []
            raw_indexes = m.get("indexes")
            # ``indexes`` is now required on EVERY mark — it's what coverage
            # counts (id-only entries record "read but nothing to note").
            if not raw_indexes:
                raise MarkServiceError(f"mark {mid}: indexes required")
            try:
                rounds = parse_indexes(raw_indexes)
            except IndexesParseError as e:
                raise MarkServiceError(f"mark {mid}: {e}") from e
            covered.update(rounds)
            parsed.append({
                "id": mid, "mark": text, "indexes": raw_indexes, "issues": issues,
            })
            next_n += 1

        # 2b. ROUND-COVERAGE — the union of every mark's ``indexes`` must cover
        #     ≥90% of the session's rounds (以写代读: read the whole session).
        #     Count only rounds in ``[1, last_index]``. Reject the WHOLE
        #     submission BEFORE any write if under threshold.
        if last_index > 0:
            in_range = {r for r in covered if 1 <= r <= last_index}
            need = math.ceil(MARK_COVERAGE_THRESHOLD * last_index)
            if len(in_range) < need:
                pct = round(100 * len(in_range) / last_index)
                raise MarkServiceError(
                    f"coverage {pct}% ({len(in_range)}/{last_index} rounds) "
                    f"< {round(MARK_COVERAGE_THRESHOLD * 100)}%",
                )

        # Degrade cleanly: if any mark carries issues but we can't collide
        # them, reject the whole batch before writing anything (no corruption).
        if self.search is None and any(p["issues"] for p in parsed):
            raise MarkUnavailable("searchbase unavailable; cannot resolve #…？ issues")

        # 3a. RESOLUTION PHASE — embed + nearest-collide + create/link every
        #     issue of every mark UP FRONT, before any submission-level write.
        #     Atomicity: if embedding raises mid-batch (e.g. provider falls
        #     over on the 2nd mark) we surface MarkUnavailable here, having
        #     written NONE of the batch's session_marks / card_sessions / yaml.
        #     (create_card may mint a card row mid-resolution — that's the only
        #     pre-commit write, and an orphaned issue-card is harmless/idempotent
        #     on retry.) The only post-resolution writes below are local + ordered.
        for p in parsed:
            resolved = []
            for issue in p["issues"]:
                try:
                    card_id, is_new = await self._resolve_issue(issue)
                except MarkUnavailable:
                    raise
                except Exception as e:   # embedding / collision blew up
                    raise MarkUnavailable(
                        f"embedding/collision failed while resolving #…？: {e}",
                    ) from e
                resolved.append({
                    "issue": issue, "card_id": card_id, "is_new": is_new,
                    "indexes": p["indexes"],
                })
            p["resolved"] = resolved

        # 3b. WRITE PHASE — every issue is resolved; nothing below embeds, so
        #     these writes are local + ordered and can't fail on the provider.
        out_marks: list[dict] = []
        for p in parsed:
            now = _utc_iso()
            # The store mints the same ``m<n>`` we validated up front against
            # ``next_seq`` (the lock above rules out a concurrent writer), so
            # this equals ``p['id']``.
            mark = await self.db.session_marks.insert(session_id, last_index, now)

            for r in p["resolved"]:
                await self.db.card_sessions.insert(
                    r["card_id"], session_id, mark, p["indexes"], now,
                )

            body = {
                "last_index": last_index,
                "description": description,
                "mark": p["mark"],
            }
            if p["indexes"]:
                body["indexes"] = p["indexes"]
            body["issues"] = p["resolved"]
            body["created_at"] = now
            await self.db.session_mark_files.write_doc(
                source, session_id, mark, body,
            )
            out_marks.append({"mark": mark, "issues": p["resolved"]})

        return {
            "session_id": session_id, "last_index": last_index, "marks": out_marks,
        }

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
        body dict (description / last_index / mark / indexes? / issues /
        created_at) or None when the session or mark is missing."""
        session = await self.db.sessions.get(session_id)
        if session is None:
            return None
        return await self.db.session_mark_files.read_doc(
            session["source"], session_id, mark,
        )
