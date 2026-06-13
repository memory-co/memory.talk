"""prior_posterior — global pool split, minus the driving set. See README.md."""
from __future__ import annotations

from memorytalk.service.explores import ExploreService, partition
from memorytalk.tests._ingest import ingest_session

# mixed sync (partition) + async (service) — async runs under asyncio_mode=auto


def test_splits_global_excluding_driving_set():
    sessions = [
        {"session_id": "s_prior", "cwd": "/work/a",
         "last_round_update_time": "2026-05-01T00:00:00Z"},
        {"session_id": "s_post", "cwd": "/work/b",
         "last_round_update_time": "2026-06-01T00:00:00Z"},
        {"session_id": "s_anchor", "cwd": "/work/c",
         "last_round_update_time": "2026-05-10T00:00:00Z"},  # == divider → prior
        {"session_id": "s_drive", "cwd": "/explore/E1/x",
         "last_round_update_time": "2026-05-15T00:00:00Z"},  # driving → excluded
    ]
    out = partition(sessions, divider_at="2026-05-10T00:00:00Z", dir_path="/explore/E1")
    assert [s["session_id"] for s in out["prior"]] == ["s_prior", "s_anchor"]
    assert [s["session_id"] for s in out["posterior"]] == ["s_post"]


def test_session_without_cwd_is_not_driving():
    sessions = [{"session_id": "s", "cwd": None,
                 "last_round_update_time": "2026-05-01T00:00:00Z"}]
    out = partition(sessions, divider_at="2026-05-10T00:00:00Z", dir_path="/explore/E1")
    assert [s["session_id"] for s in out["prior"]] == ["s"]


async def test_get_partition_splits_db_sessions_by_divider(app, client):
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
