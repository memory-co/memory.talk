"""一条龙:提问题 → 加立场 → 表态 → 绑 manager → 派 task → 写卡(同一 commit)→ 改卡 → 开讨论页 → 历史 / 目录 / 检索。"""
import subprocess


def test_issue_to_card_and_back(client, tmp_path):
    # 提问题
    r = client.post("/api/issues", json={
        "question": "memory.talk v5 的配置该走文件还是环境变量?",
        "origin": {"task_id": "task_a", "rounds": [3, 4]},
        "reason": "写 config.py 时撞见的",
    })
    assert r.status_code == 201, r.text
    iss = r.json()
    iid = iss["id"]
    assert iss["manager_task"] is None

    # 没人管 → unmanaged 能查到
    assert [i["id"] for i in client.get("/api/issues", params={"unmanaged": True}).json()] == [iid]

    # 绑 manager
    r = client.put(f"/api/issues/{iid}/manager", json={"task_id": "task_root"})
    assert r.json()["manager_task"] == "task_root"

    # 两个立场
    client.post(f"/api/issues/{iid}/positions", json={"claim": "加一个 settings.json"})
    client.post(f"/api/issues/{iid}/positions", json={"claim": "只用环境变量,不要配置文件"})

    # 派 task 去验 p2,然后它回流 +1;p1 被踩
    client.post(f"/api/issues/{iid}/positions/p2/tasks", json={"task_id": "task_try"})
    client.post(f"/api/issues/{iid}/positions/p2/arguments",
                json={"stance": 1, "task_id": "task_try",
                      "evidence": {"task_id": "task_try", "rounds": [9]}, "comment": "试了一遍,环境变量够用"})
    client.post(f"/api/issues/{iid}/positions/p1/arguments", json={"stance": -1, "comment": "多一份状态要同步"})

    v = client.get(f"/api/issues/{iid}").json()
    assert [p["id"] for p in v["positions"]] == ["p2", "p1"]      # 按 credence 排
    assert v["positions"][0]["credence"] == 1 and v["positions"][1]["credence"] == -1
    assert v["positions"][0]["spawned_tasks"] == ["task_try"]

    # 争出结果 → 写卡,同一个 commit
    r = client.post(f"/api/issues/{iid}/card", json={
        "position_id": "p2", "title": "配置只来自环境变量", "dir": "memory.talk",
        "context": "memory.talk v5", "reason": "环境变量够用,配置文件多一份状态",
    })
    assert r.status_code == 201, r.text
    cid = r.json()["card"]
    assert cid == "memory.talk/配置只来自环境变量"
    card = client.get(f"/api/cards/{cid}").json()
    assert card["issue"] == iid and card["body"] == "只用环境变量,不要配置文件"

    repo = tmp_path / "home" / "memory"
    head_files = subprocess.run(["git", "-c", "core.quotepath=false", "show", "--name-only", "--format=", "HEAD"],
                                cwd=repo, capture_output=True, text=True).stdout.split()
    assert sorted(head_files) == sorted([f"cards/{cid}.md", f"issues/{iid}.json"])

    # 目录 + 召回文本
    cat = client.get("/api/cards").json()
    assert cat["subdirs"][0]["dir"] == "memory.talk"
    assert cat["subdirs"][0]["cards"][0]["title"] == "配置只来自环境变量"
    assert "配置只来自环境变量" in client.get("/api/cards/recall").text

    # 改卡 → 历史两条;读旧版本
    client.put(f"/api/cards/{cid}", json={"body": "只用环境变量。配置文件是多出来的一份状态,要同步。", "reason": "补理由"})
    hist = client.get(f"/api/cards/{cid}/history").json()
    assert len(hist) == 2 and hist[0]["subject"].startswith("card: edit")
    old = client.get(f"/api/cards/{cid}", params={"rev": hist[1]["sha"]}).json()
    assert old["body"] == "只用环境变量,不要配置文件"

    # 检索
    assert client.get("/api/cards/search", params={"q": "一份状态"}).json()[0]["id"] == cid
    assert client.get("/api/issues/search", params={"q": "settings.json"}).json()[0]["id"] == iid

    # 直接写一张卡,再对它不同意 → 开讨论页,同一 commit
    r = client.post("/api/cards", json={"title": "Python 3.12", "body": "仓库用 3.12", "dir": "memory.talk"})
    assert r.status_code == 201
    r = client.post("/api/cards/memory.talk/Python-3.12/issue", json={"question": "要不要升 3.13?"})
    assert r.status_code == 201
    assert r.json()["card"] == "memory.talk/Python-3.12"
    assert client.get("/api/cards/memory.talk/Python-3.12").json()["issue"] == r.json()["id"]

    # 废弃
    r = client.delete(f"/api/cards/{cid}", params={"reason": "过时"})
    assert r.json()["status"] == "deprecated"
    assert client.get("/api/cards").json()["subdirs"][0]["cards"][0]["id"] == "memory.talk/Python-3.12"

    # 404 / 409
    assert client.get("/api/cards/nope").status_code == 404
    assert client.post("/api/cards", json={"title": "Python 3.12", "dir": "memory.talk"}).status_code == 409
