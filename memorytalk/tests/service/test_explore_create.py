"""ExploreService.create — resolve + freeze the divider, persist the row."""
from __future__ import annotations

import pytest

from memorytalk.service.explores import ExploreService
from memorytalk.tests._ingest import ingest_session

pytestmark = pytest.mark.asyncio


async def test_create_freezes_divider_from_entrypoint_session(app, client):
    r = await ingest_session(client, "ep-1", rounds=[
        {"round_id": "r1", "role": "human",
         "timestamp": "2026-05-10T08:00:00Z",
         "content": [{"type": "text", "text": "x"}]},
    ])
    sid = r.json()["session_id"]

    svc = ExploreService(db=app.state.db, config=app.state.config)
    explore_id = await svc.create(entrypoint_session_id=sid)

    assert explore_id.startswith("explore_")
    row = await app.state.db.explores.get(explore_id)
    assert row["divider_at"] == "2026-05-10T08:00:00Z"   # entrypoint's lrut, frozen
    assert row["entrypoint_session_id"] == sid
    assert row["dir_path"]                                 # a workspace dir was assigned
