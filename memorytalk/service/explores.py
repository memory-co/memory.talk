"""Explore — a prior/posterior card-extraction workspace.

See docs/works/v3/explore.md. explore is a "gentleman's agreement": it
lays out the global session pool as prior (at/before a frozen divider)
vs posterior (after it), minus the explore's own driving sessions (the
ones run in its workspace directory), and leaves honoring that split to
the extractor. Nothing here enforces card/review reference constraints.
"""
from __future__ import annotations


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
