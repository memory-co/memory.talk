"""works/viewers -- who is looking at a work right now (heartbeats in memory, works.viewers as the projection). See README.md."""
from fastapi.testclient import TestClient


def _work(client, H, who="alice"):
    return client.post("/api/works", json={"goal": "x"}, headers=H(who)).json()


def _current(client, w):
    return client.get(f"/api/works/{w['id']}/users").json()["current"]


def test_the_creator_is_looking_at_it(client, H):
    w = _work(client, H)
    assert w["viewers"] == ["alice"] and _current(client, w) == ["alice"]


def test_users_returns_current_names_only(client, H):
    w = _work(client, H)
    assert client.get(f"/api/works/{w['id']}/users").json() == {"current": ["alice"]}
    assert client.get("/api/works/work_nope/users").status_code == 404


def test_opening_a_work_is_a_heartbeat_and_names_are_sorted(client, H):
    w = _work(client, H, "carol")
    assert client.get(f"/api/works/{w['id']}", headers=H("bob")).json()["viewers"] == ["bob", "carol"]
    assert client.post(f"/api/works/{w['id']}/users/touch", headers=H("alice")).json() == {"current": ["alice", "bob", "carol"]}


def test_leave_drops_out_at_once(client, H):
    w = _work(client, H)
    client.get(f"/api/works/{w['id']}", headers=H("bob"))
    assert client.post(f"/api/works/{w['id']}/users/leave", headers=H("alice")).json() == {"current": ["bob"]}
    assert client.get("/api/works", params={"root": w["id"]}).json()[0]["viewers"] == ["bob"]      # works.viewers 跟着变
    assert client.post(f"/api/works/{w['id']}/users/leave", headers=H("alice")).json() == {"current": ["bob"]}   # 再离开一次没事


def test_silent_viewers_are_swept_after_the_window(client, svc, H):
    from memorytalk.backend.services.work.viewers import ACTIVE_WINDOW
    w = _work(client, H)
    client.get(f"/api/works/{w['id']}", headers=H("bob"))
    svc.works.viewers._beats[w["id"]]["bob"] -= ACTIVE_WINDOW + 1          # bob 两分钟没心跳了
    assert _current(client, w) == ["alice"]
    assert client.get("/api/works", params={"root": w["id"]}).json()[0]["viewers"] == ["alice"]


def test_heartbeats_are_not_history(client, H):
    w = _work(client, H)
    for _ in range(3):
        client.get(f"/api/works/{w['id']}", headers=H("bob"))
    spans = client.get(f"/api/works/{w['id']}/trace").json()["traces"]["resourceSpans"][0]["scopeSpans"][0]["spans"]
    logs = client.get(f"/api/works/{w['id']}/trace").json()["logs"]["resourceLogs"][0]["scopeLogs"][0]["logRecords"]
    assert [s["name"] for s in spans] == ["work"] and logs == []          # 看不进轨迹


def test_a_restart_clears_every_viewer(client, H):
    w = _work(client, H)
    from memorytalk.backend.config import load_config, load_runtime_config
    from memorytalk.backend.main import create_app
    with TestClient(create_app(load_config(), load_runtime_config())) as c2:
        c2.headers["Authorization"] = client.headers["Authorization"]
        assert c2.get("/api/works", params={"root": w["id"]}).json()[0]["viewers"] == []
        assert c2.get(f"/api/works/{w['id']}/users").json() == {"current": []}
