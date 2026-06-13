"""crud — POST/GET /v3/explores. See README.md."""
from __future__ import annotations

import pytest

from memorytalk.tests._ingest import ingest_session

pytestmark = pytest.mark.asyncio


async def _seed_prior_and_posterior(client):
    await ingest_session(client, "ex-prior", rounds=[
        {"round_id": "r1", "role": "human", "timestamp": "2026-05-01T00:00:00Z",
         "content": [{"type": "text", "text": "a"}]}])
    await ingest_session(client, "ex-post", rounds=[
        {"round_id": "r1", "role": "human", "timestamp": "2026-06-01T00:00:00Z",
         "content": [{"type": "text", "text": "b"}]}])


async def test_post_explores_freezes_divider_and_reports_counts(app, client):
    await _seed_prior_and_posterior(client)

    r = await client.post("/v3/explores", json={"divider_at": "2026-05-15T00:00:00Z"})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["explore_id"].startswith("explore_")
    assert body["divider_at"] == "2026-05-15T00:00:00Z"
    assert body["prior_count"] >= 1
    assert body["posterior_count"] >= 1


async def test_get_explore_returns_partition(app, client):
    await _seed_prior_and_posterior(client)
    eid = (await client.post(
        "/v3/explores", json={"divider_at": "2026-05-15T00:00:00Z"})).json()["explore_id"]

    r = await client.get(f"/v3/explores/{eid}")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["explore_id"] == eid
    assert "prior" in body and "posterior" in body
    assert len(body["prior"]) >= 1
