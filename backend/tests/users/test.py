"""user:work 有 created_by;带身份的操作记进 users;current = 最近活动过;history = 操作过的所有人;不带身份不记、也不拦。"""


def test_users_visibility(client):
    t = client.post("/api/works", json={"goal": "团队一起做"}, headers={"X-Memory-Talk-User": "alice"}).json()
    assert t["created_by"] == "alice"
    assert [w["id"] for w in client.get("/api/works", params={"created_by": "alice"}).json()] == [t["id"]]
    assert client.get("/api/works", params={"created_by": "nobody"}).json() == []
    assert client.post("/api/works", json={"goal": "匿名建的"}).json()["created_by"] is None
    client.patch(f"/api/works/{t['id']}", json={"status": "doing"}, headers={"X-Memory-Talk-User": "bob"})
    client.get(f"/api/works/{t['id']}", headers={"X-Memory-Talk-User": "alice"})
    client.patch(f"/api/works/{t['id']}", json={"goal": "匿名也能改"})           # 不带身份:不记、不拦

    m = client.get(f"/api/works/{t['id']}/users").json()
    assert [x["user"] for x in m["history"]] == ["alice", "bob"]              # 按最近活动倒序
    assert {x["user"]: x["ops"] for x in m["history"]} == {"alice": 2, "bob": 1}
    assert all(x["active"] for x in m["current"]) and len(m["current"]) == 2

    # 心跳
    m = client.post(f"/api/works/{t['id']}/users/touch", headers={"X-Memory-Talk-User": "carol"}).json()
    assert m["history"][0]["user"] == "carol" and m["history"][0]["ops"] == 1

    # 过了活跃窗口就不在 current 里(把 last_seen 拨回去——经仓储,两种 store 都行)
    repo = client.app.state.works.repo
    rows = repo.get_doc(t["id"], "users")
    for r in rows:
        if r["user"] == "bob":
            r["last_seen"] = "2020-01-01T00:00:00Z"
    repo.put_doc(t["id"], "users", rows)
    m = client.get(f"/api/works/{t['id']}/users").json()
    assert sorted(x["user"] for x in m["current"]) == ["alice", "carol"]
    assert len(m["history"]) == 3

    assert client.get("/api/works/work_nope/users").status_code == 404


def test_users_top_level(client):
    a = client.post("/api/works", json={"goal": "A 的事"}, headers={"X-Memory-Talk-User": "alice"}).json()
    client.patch(f"/api/works/{a['id']}", json={"status": "doing"}, headers={"X-Memory-Talk-User": "bob"})
    client.post("/api/collections/card/x/一张卡", json={"data": {"title": "一张卡"}}, headers={"X-Memory-Talk-User": "bob"})
    client.post("/api/collections/card/x/匿名卡", json={"data": {"title": "匿名卡"}})          # 没带身份:不算 user

    users = {u["name"]: u for u in client.get("/api/users").json()}
    assert set(users) == {"alice", "bob"}
    assert users["alice"]["works_created"] == 1 and users["alice"]["works_touched"] == 1
    assert users["bob"]["works_created"] == 0 and users["bob"]["works_touched"] == 1 and users["bob"]["commits"] == 1
    assert users["alice"]["active_works"] == [a["id"]]

    p = client.get("/api/users/bob").json()
    assert p["works_touched_ids"] == [a["id"]] and p["recent_commits"][0]["subject"].startswith("[card] write x/一张卡")
    assert client.get("/api/users/nobody").status_code == 404
    assert client.get("/api/users/me").json() is None
    assert client.get("/api/users/me", headers={"X-Memory-Talk-User": "alice"}).json()["works_created_ids"] == [a["id"]]
    assert client.get("/api/users/me", headers={"X-Memory-Talk-User": "carol"}).json()["name"] == "carol"   # 新名字:存在但空白
