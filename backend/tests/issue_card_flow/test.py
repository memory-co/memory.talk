"""一条龙:提问题 → 加立场 → 表态 → 绑 manager → 派 task → 写卡(同一 commit)→ 改卡 → 开讨论页 → 历史 / 目录 / 检索。"""
import subprocess


def test_issue_to_card_and_back(client, tmp_path):
    # 提问题
    r = client.post("/api/issues", json={
        "question": "memory.talk 的向量库该不该换?",
        "origin": {"task_id": "task_a", "rounds": [3, 4]},
        "reason": "做同步时撞见的",
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
    client.post(f"/api/issues/{iid}/positions", json={"claim": "换 pgvector"})
    client.post(f"/api/issues/{iid}/positions", json={"claim": "不换,继续 LanceDB"})

    # 派 task 去验 p2,然后它回流 +1;p1 被踩
    client.post(f"/api/issues/{iid}/positions/p2/tasks", json={"task_id": "task_bench"})
    client.post(f"/api/issues/{iid}/positions/p2/arguments",
                json={"stance": 1, "task_id": "task_bench",
                      "evidence": {"task_id": "task_bench", "rounds": [9]}, "comment": "基准没差别"})
    client.post(f"/api/issues/{iid}/positions/p1/arguments", json={"stance": -1, "comment": "迁移成本高"})

    v = client.get(f"/api/issues/{iid}").json()
    assert [p["id"] for p in v["positions"]] == ["p2", "p1"]      # 按 credence 排
    assert v["positions"][0]["credence"] == 1 and v["positions"][1]["credence"] == -1
    assert v["positions"][0]["spawned_tasks"] == ["task_bench"]

    # 争出结果 → 写卡,同一个 commit
    r = client.post(f"/api/issues/{iid}/card", json={
        "position_id": "p2", "title": "向量库用 LanceDB", "dir": "memory.talk",
        "context": "memory.talk 仓库", "reason": "基准无差别,迁移成本高",
    })
    assert r.status_code == 201, r.text
    cid = r.json()["card"]
    assert cid == "memory.talk/向量库用-LanceDB"
    card = client.get(f"/api/cards/{cid}").json()
    assert card["issue"] == iid and card["body"] == "不换,继续 LanceDB"

    repo = tmp_path / "home" / "memory"
    head_files = subprocess.run(["git", "-c", "core.quotepath=false", "show", "--name-only", "--format=", "HEAD"],
                                cwd=repo, capture_output=True, text=True).stdout.split()
    assert sorted(head_files) == sorted([f"cards/{cid}.md", f"issues/{iid}.json"])

    # 目录 + 召回文本
    cat = client.get("/api/cards").json()
    assert cat["subdirs"][0]["dir"] == "memory.talk"
    assert cat["subdirs"][0]["cards"][0]["title"] == "向量库用 LanceDB"
    assert "向量库用 LanceDB" in client.get("/api/cards/recall").text

    # 改卡 → 历史两条;读旧版本
    client.put(f"/api/cards/{cid}", json={"body": "不换。基准无差别,迁移成本高。", "reason": "补理由"})
    hist = client.get(f"/api/cards/{cid}/history").json()
    assert len(hist) == 2 and hist[0]["subject"].startswith("card: edit")
    old = client.get(f"/api/cards/{cid}", params={"rev": hist[1]["sha"]}).json()
    assert old["body"] == "不换,继续 LanceDB"

    # 检索
    assert client.get("/api/cards/search", params={"q": "迁移成本"}).json()[0]["id"] == cid
    assert client.get("/api/issues/search", params={"q": "pgvector"}).json()[0]["id"] == iid

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
