"""users/activity -- work users current/history + aggregated stats. See README.md."""


def _work(client, H):
    return client.post("/api/works", json={"goal": "团队一起做"}, headers=H("alice")).json()


def test_operations_with_identity_are_recorded(client, H):
    t = _work(client, H)
    client.patch(f"/api/works/{t['id']}", json={"status": "doing"}, headers=H("bob"))
    client.get(f"/api/works/{t['id']}", headers=H("alice"))          # 打开也算
    u = client.get(f"/api/works/{t['id']}/users").json()
    assert {x["user"]: x["ops"] for x in u["history"]} == {"alice": 2, "bob": 1}


def test_history_is_ordered_by_last_activity(client, H):
    t = _work(client, H)
    client.patch(f"/api/works/{t['id']}", json={"status": "doing"}, headers=H("bob"))
    assert [x["user"] for x in client.get(f"/api/works/{t['id']}/users").json()["history"]] == ["bob", "alice"]


def test_every_operation_is_recorded_to_whoever_is_logged_in(client, H):
    t = _work(client, H)
    client.patch(f"/api/works/{t['id']}", json={"goal": "默认的 client 是 admin"})
    assert [x["user"] for x in client.get(f"/api/works/{t['id']}/users").json()["history"]] == ["admin", "alice"]


def test_heartbeat_touch(client, H):
    t = _work(client, H)
    u = client.post(f"/api/works/{t['id']}/users/touch", headers=H("carol")).json()
    assert u["history"][0]["user"] == "carol" and u["history"][0]["ops"] == 1


def test_current_drops_users_outside_the_window(client, H, svc):
    t = _work(client, H)
    client.patch(f"/api/works/{t['id']}", json={"status": "doing"}, headers=H("bob"))
    rows = svc.works.repo.get_doc(t["id"], "users")
    for r in rows:
        if r["user"] == "bob":
            r["last_seen"] = "2020-01-01T00:00:00Z"
    svc.works.repo.put_doc(t["id"], "users", rows)
    u = client.get(f"/api/works/{t['id']}/users").json()
    assert [x["user"] for x in u["current"]] == ["alice"] and len(u["history"]) == 2


def test_user_list_aggregates_activity(client, H):
    t = _work(client, H)
    client.patch(f"/api/works/{t['id']}", json={"status": "doing"}, headers=H("bob"))
    users = {u["name"]: u for u in client.get("/api/users").json()}
    assert users["alice"]["works_created"] == 1 and users["alice"]["works_touched"] == 1
    assert users["bob"]["works_created"] == 0 and users["bob"]["works_touched"] == 1
    assert users["alice"]["active_works"] == [t["id"]]
    p = client.get("/api/users/bob").json()
    assert p["works_touched_ids"] == [t["id"]]
