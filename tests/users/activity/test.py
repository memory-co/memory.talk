"""users/activity -- derived stats: created from works.db, touched / last_seen from the trace, active from works.viewers. See README.md."""
import re

from memorytalk.backend.services.work.viewers import ACTIVE_WINDOW


def _work(client, H, who="alice"):
    return client.post("/api/works", json={"goal": "团队一起做"}, headers=H(who)).json()


def _users(client):
    return {u["name"]: u for u in client.get("/api/users").json()}


def test_creating_a_work_counts_as_created_and_touched(client, H):
    t = _work(client, H)
    a = client.get("/api/users/alice").json()
    assert (a["works_created"], a["works_touched"]) == (1, 1)
    assert a["works_created_ids"] == a["works_touched_ids"] == [t["id"]]


def test_ending_a_span_counts_as_touching(client, H):
    t = _work(client, H)
    client.patch(f"/api/works/{t['id']}", json={"status": "archived"}, headers=H("bob"))     # bob 只结束了 work 段
    b = client.get("/api/users/bob").json()
    assert (b["works_created"], b["works_touched"], b["works_touched_ids"]) == (0, 1, [t["id"]])


def test_a_point_counts_as_touching(client, H):
    t = _work(client, H)
    client.post(f"/api/works/{t['id']}/columns", json={"alias": "carol 的列"}, headers=H("carol"))
    assert client.get("/api/users/carol").json()["works_touched_ids"] == [t["id"]]


def test_reads_and_heartbeats_do_not_count_as_touching(client, H):
    t = _work(client, H)
    client.get(f"/api/works/{t['id']}", headers=H("carol"))
    client.post(f"/api/works/{t['id']}/users/touch", headers=H("carol"))
    c = client.get("/api/users/carol").json()
    assert (c["works_touched"], c["works_touched_ids"], c["last_seen"]) == (0, [], "")
    assert c["active_works"] == [t["id"]]                                                    # 只是在看


def test_active_works_are_the_works_the_user_is_looking_at(client, H):
    t1, t2 = _work(client, H), _work(client, H)
    assert _users(client)["alice"]["active_works"] == sorted([t1["id"], t2["id"]])           # 按 work id 排
    client.post(f"/api/works/{t1['id']}/users/leave", headers=H("alice"))
    assert _users(client)["alice"]["active_works"] == [t2["id"]]
    assert _users(client)["bob"]["active_works"] == []


def test_active_works_drop_out_after_the_window(client, svc, H):
    t = _work(client, H)
    svc.works.viewers._beats[t["id"]]["alice"] -= ACTIVE_WINDOW + 1
    svc.works.viewers.sweep()                                                                # 后台每 30 秒清一遍
    a = client.get("/api/users/alice").json()
    assert a["active_works"] == [] and a["works_touched_ids"] == [t["id"]]                  # 不在看了,动过还是动过


def test_touched_ids_are_ordered_by_work_id(client, H):
    ids = [_work(client, H, "bob")["id"] for _ in range(3)]
    client.patch(f"/api/works/{ids[0]}", json={"goal": "最后才改的"}, headers=H("bob"))
    assert client.get("/api/users/bob").json()["works_touched_ids"] == sorted(ids)


def test_last_seen_is_utc_to_the_second(client, H):
    t = _work(client, H)
    client.patch(f"/api/works/{t['id']}", json={"goal": "改个名"}, headers=H("bob"))
    users = _users(client)
    for name in ("alice", "bob"):
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", users[name]["last_seen"])
    assert users["bob"]["last_seen"] >= users["alice"]["last_seen"] >= t["created_at"]
    assert users["carol"]["last_seen"] == ""


def test_profile_and_list_agree(client, H):
    t = _work(client, H)
    client.patch(f"/api/works/{t['id']}", json={"status": "archived"}, headers=H("bob"))
    users = _users(client)
    for name in ("alice", "bob"):
        p = client.get(f"/api/users/{name}").json()
        assert {k: p[k] for k in ("works_created", "works_touched", "active_works", "last_seen")} == \
            {k: users[name][k] for k in ("works_created", "works_touched", "active_works", "last_seen")}
