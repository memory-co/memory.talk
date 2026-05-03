"""new-session: sessions touched by the latest sync.

Selects session_ids that carry the `sync_session` tag (with any value:
typically `new` for fresh imports, `update` for sessions whose rounds
were appended). The tag is stamped automatically by SessionService.ingest
on each successful sync action.

mark removes the tag — the session leaves the frame until another sync
touches it again. unmark adds the tag back (with empty value, since
the framework's auto-reverse doesn't know the prior value).
"""
from __future__ import annotations
from typing import Callable


def select(client: Callable) -> list[str]:
    """Return session_ids currently bearing a sync_session tag.

    ``client`` is a callable wrapping memory-talk's HTTP API:
        client(method: str, path: str, *,
               json_body: dict | None = None,
               params: list | dict | None = None) -> dict
    """
    resp = client("POST", "/v2/search", json_body={
        "query": "",
        "where": 'tag = "sync_session"',
    })
    return [s["session_id"] for s in resp["sessions"]["results"]]
