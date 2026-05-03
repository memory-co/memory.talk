"""new-session: viewfinder over sessions not yet processed by this filter.

Returns session_ids that haven't been tagged with `_filter-new-session`.
The filter itself is a pure selector — actually doing something with
each session (extracting cards, summarizing, etc.) is the user's job
between `filter run` and `filter mark`.
"""
from __future__ import annotations
from typing import Callable


def select(client: Callable) -> list[str]:
    """Return subject_ids currently in this filter's frame.

    ``client`` is a callable wrapping memory-talk's HTTP API:
        client(method: str, path: str, *,
               json_body: dict | None = None,
               params: list | dict | None = None) -> dict
    """
    resp = client("POST", "/v2/search", json_body={
        "query": "",
        "where": 'tag != "_filter-new-session"',
    })
    return [s["session_id"] for s in resp["sessions"]["results"]]
