"""Explore — a prior/posterior card-extraction workspace.

See docs/works/v3/explore.md. explore is a "gentleman's agreement": it
lays out the global session pool as prior (at/before a frozen divider)
vs posterior (after it), minus the explore's own driving sessions (the
ones run in its workspace directory), and leaves honoring that split to
the extractor. Nothing here enforces card/review reference constraints.
"""
from __future__ import annotations

import datetime as _dt
import json

from memorytalk.util.ids import new_explore_id
from memorytalk.util.instant import parse_instant


class ExploreServiceError(Exception):
    """4xx-equivalent: bad explore create request."""


def _utc_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(
        timespec="seconds",
    ).replace("+00:00", "Z")


def _under(cwd: str | None, dir_path: str) -> bool:
    """True if ``cwd`` is the explore's workspace dir or below it."""
    if not cwd:
        return False
    return cwd == dir_path or cwd.startswith(dir_path.rstrip("/") + "/")


def partition(
    sessions: list[dict], *, divider_at: str, dir_path: str,
) -> dict[str, list[dict]]:
    """Split global ``sessions`` into prior/posterior by ``divider_at``,
    excluding the explore's driving set (cwd under ``dir_path``).

    Both ``last_round_update_time`` and ``divider_at`` are canonical
    UTC-Z, so a lexical compare is a temporal compare. The divider is
    inclusive on the prior side (``<=``). Sessions with no
    ``last_round_update_time`` are skipped (no place on the timeline)."""
    prior: list[dict] = []
    posterior: list[dict] = []
    for s in sessions:
        if _under(s.get("cwd"), dir_path):
            continue  # driving session — excluded from the analysed pool
        lrut = s.get("last_round_update_time")
        if not lrut:
            continue
        (prior if lrut <= divider_at else posterior).append(s)
    return {"prior": prior, "posterior": posterior}


class ExploreService:
    """Create + read explores. The directory is the AI's free workspace;
    memory.talk writes one explore.json at creation and never again."""

    def __init__(self, db, config):
        self.db = db
        self.config = config

    async def create(
        self,
        *,
        entrypoint_session_id: str | None = None,
        divider_at: str | None = None,
        note: str | None = None,
    ) -> str:
        """Resolve + freeze the divider, mint the workspace dir, write the
        row + the one-time explore.json. Pass either an entrypoint session
        (its last_round_update_time becomes the divider, frozen now) or a
        divider time directly."""
        if entrypoint_session_id is not None:
            sess = await self.db.sessions.get(entrypoint_session_id)
            if sess is None:
                raise ExploreServiceError(
                    f"entrypoint session {entrypoint_session_id} not found"
                )
            divider_at = sess.get("last_round_update_time")
        if not divider_at:
            raise ExploreServiceError(
                "explore needs an entrypoint_session_id or a divider_at"
            )

        explore_id = new_explore_id()
        created_at = _utc_iso()
        now = parse_instant(created_at)
        dir_path = (
            self.config.data_root / "explores"
            / now.strftime("%Y") / now.strftime("%m") / explore_id
        )
        dir_path.mkdir(parents=True, exist_ok=True)
        (dir_path / "explore.json").write_text(
            json.dumps({
                "explore_id": explore_id,
                "dir_path": str(dir_path),
                "divider_at": divider_at,
                "entrypoint_session_id": entrypoint_session_id,
                "created_at": created_at,
                "note": note,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        await self.db.explores.insert(
            explore_id, dir_path=str(dir_path), divider_at=divider_at,
            entrypoint_session_id=entrypoint_session_id,
            created_at=created_at, note=note,
        )
        return explore_id

    async def get_partition(self, explore_id: str) -> dict[str, list[dict]]:
        """Live prior/posterior split for an explore: the global session
        pool against the frozen divider, minus the driving set. Computed
        fresh each call (line frozen, membership live)."""
        exp = await self.db.explores.get(explore_id)
        if exp is None:
            raise ExploreServiceError(f"explore {explore_id} not found")
        sessions = await self.db.sessions.list_for_partition()
        return partition(
            sessions, divider_at=exp["divider_at"], dir_path=exp["dir_path"],
        )
