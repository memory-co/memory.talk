"""ExploreService.get_partition — prior/posterior over the live global pool."""
from __future__ import annotations

import pytest

from memorytalk.service.explores import ExploreService
from memorytalk.tests._ingest import ingest_session

pytestmark = pytest.mark.asyncio


async def test_get_partition_splits_global_sessions_by_divider(app, client):
    rp = await ingest_session(client, "gp-prior", rounds=[
        {"round_id": "r1", "role": "human", "timestamp": "2026-05-01T00:00:00Z",
         "content": [{"type": "text", "text": "a"}]}])
    rq = await ingest_session(client, "gp-post", rounds=[
        {"round_id": "r1", "role": "human", "timestamp": "2026-06-01T00:00:00Z",
         "content": [{"type": "text", "text": "b"}]}])
    sid_prior = rp.json()["session_id"]
    sid_post = rq.json()["session_id"]

    svc = ExploreService(db=app.state.db, config=app.state.config)
    explore_id = await svc.create(divider_at="2026-05-15T00:00:00Z")

    part = await svc.get_partition(explore_id)

    assert sid_prior in {s["session_id"] for s in part["prior"]}
    assert sid_post in {s["session_id"] for s in part["posterior"]}
