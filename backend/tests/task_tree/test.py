"""树:建根、拆子、状态收拢、画布乐观锁、事件、召回。不碰 server。"""


def test_tree_status_canvas_events(client):
    root = client.post("/api/tasks", json={"goal": "把 v5 做出来", "project": "/w/memory.talk"}).json()
    a = client.post("/api/tasks", json={"goal": "实现 issue", "parent": root["id"]}).json()
    b = client.post("/api/tasks", json={"goal": "实现 task", "parent": root["id"]}).json()
    assert client.post("/api/tasks", json={"goal": "x", "parent": "task_nope"}).status_code == 404

    forest = client.get("/api/tasks").json()
    assert [n["id"] for n in forest] == [root["id"]]
    assert sorted(c["id"] for c in forest[0]["children"]) == sorted([a["id"], b["id"]])
    assert client.get("/api/tasks", params={"root": a["id"]}).json()[0]["children"] == []

    # 父 task 不能先于子 task 做完
    r = client.patch(f"/api/tasks/{root['id']}", json={"status": "done"})
    assert r.status_code == 409 and a["id"] in r.json()["message"]
    assert client.patch(f"/api/tasks/{a['id']}", json={"status": "done"}).json()["done_at"]
    assert client.patch(f"/api/tasks/{b['id']}", json={"status": "abandoned"}).status_code == 200
    assert client.patch(f"/api/tasks/{root['id']}", json={"status": "done"}).json()["status"] == "done"

    # 结束后不再是干活的地方
    assert client.post(f"/api/tasks/{a['id']}/members", json={"uri": "bash://"}).status_code == 409

    # 画布:视图 + 乐观锁 + 越界
    cv = client.get(f"/api/tasks/{root['id']}/canvas").json()
    assert cv["version"] == 0 and cv["panels"] == []
    panels = [{"id": "p1", "uri": "file:///w", "x": 0, "y": 0, "w": 12, "h": 16},
              {"id": "p2", "uri": "https://example.com", "x": 12, "y": 0, "w": 12, "h": 16}]
    cv = client.put(f"/api/tasks/{root['id']}/canvas", json={"version": 0, "panels": panels}).json()
    assert cv["version"] == 1
    assert client.put(f"/api/tasks/{root['id']}/canvas", json={"version": 0, "panels": []}).status_code == 409
    bad = [{"id": "p1", "uri": "file:///w", "x": 20, "y": 0, "w": 12, "h": 16}]
    assert client.put(f"/api/tasks/{root['id']}/canvas", json={"version": 1, "panels": bad}).status_code == 409

    # 事件
    types = [e["type"] for e in client.get(f"/api/tasks/{root['id']}/events").json()]
    assert types == ["created", "status", "frozen"]

    # 召回 = card 目录
    client.post("/api/cards", json={"title": "配置只来自环境变量", "dir": "memory.talk"})
    assert "配置只来自环境变量" in client.get(f"/api/tasks/{root['id']}/recall").text
