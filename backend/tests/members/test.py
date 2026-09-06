"""成员(人):带身份的操作被记下来;current = 最近活动过;history = 操作过的所有人;不带身份不记、也不拦。"""


def test_members_visibility(client):
    t = client.post("/api/tasks", json={"goal": "团队一起做"}, headers={"X-Memory-Talk-User": "alice"}).json()
    client.patch(f"/api/tasks/{t['id']}", json={"status": "doing"}, headers={"X-Memory-Talk-User": "bob"})
    client.get(f"/api/tasks/{t['id']}", headers={"X-Memory-Talk-User": "alice"})
    client.patch(f"/api/tasks/{t['id']}", json={"goal": "匿名也能改"})           # 不带身份:不记、不拦

    m = client.get(f"/api/tasks/{t['id']}/members").json()
    assert [x["user"] for x in m["history"]] == ["alice", "bob"]              # 按最近活动倒序
    assert {x["user"]: x["ops"] for x in m["history"]} == {"alice": 2, "bob": 1}
    assert all(x["active"] for x in m["current"]) and len(m["current"]) == 2

    # 心跳
    m = client.post(f"/api/tasks/{t['id']}/members/touch", headers={"X-Memory-Talk-User": "carol"}).json()
    assert m["history"][0]["user"] == "carol" and m["history"][0]["ops"] == 1

    # 过了活跃窗口就不在 current 里(把 last_seen 拨回去)
    import json, os
    p = os.path.join(os.environ["MEMORY_TALK_HOME"], "tasks", t["id"], "members.json")
    rows = json.load(open(p))
    for r in rows:
        if r["user"] == "bob":
            r["last_seen"] = "2020-01-01T00:00:00Z"
    json.dump(rows, open(p, "w"))
    m = client.get(f"/api/tasks/{t['id']}/members").json()
    assert sorted(x["user"] for x in m["current"]) == ["alice", "carol"]
    assert len(m["history"]) == 3

    assert client.get("/api/tasks/task_nope/members").status_code == 404
