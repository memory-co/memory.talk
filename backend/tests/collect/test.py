"""Collect:层、对象 CRUD、行为(两个相邻提交)、守卫、历史、检索、树、manager 与收件箱、用户层。"""
import subprocess

H = {"X-Memory-Talk-User": "alice"}


def _log(client, ref="stack"):
    root = client.app.state.collect.repo.root
    args = ["git", "-c", "core.quotepath=false", "log", "--format=%s%n%b", "--first-parent", ref] if ref == "stack" \
        else ["git", "-c", "core.quotepath=false", "log", "--format=%s%n%b", ref]
    return subprocess.run(args, cwd=root, capture_output=True, text=True).stdout


def test_layers_and_objects(client):
    layers = client.get("/api/collect/layers").json()
    assert [l["name"] for l in layers] == ["origin", "issue", "card"]
    assert layers[0]["suffix"] is None and layers[1]["suffix"] == ".issue" and layers[2]["body"] == "card.md"
    assert "decide" in layers[1]["behaviors"] and layers[2]["behaviors"] == ["discuss"]

    # origin:原文文件;issue / card:带后缀的目录,并排在同一个文件夹
    assert client.post("/api/collect/origin/memory.talk/配置/旧方案.md", json={"content": "这是原文"}).status_code == 201
    iss = client.post("/api/collect/issue/memory.talk/配置/该走文件还是环境变量",
                      json={"data": {"question": "配置该走文件还是环境变量?", "origin": {"work_id": "work_a", "rounds": [3]}},
                            "reason": "撞见的"}, headers=H)
    assert iss.status_code == 201, iss.text
    ip = iss.json()["path"]
    assert iss.json()["title"] == "配置该走文件还是环境变量?"
    assert client.post("/api/collect/issue/" + ip, json={"data": {"question": "x"}}).status_code == 409

    tree = {i["name"]: i for i in client.get("/api/collect/tree", params={"path": "memory.talk/配置"}).json()}
    assert tree["旧方案.md"]["kind"] == "file" and tree["旧方案.md"]["layer"] == "origin"
    assert tree["该走文件还是环境变量.issue"]["kind"] == "object" and tree["该走文件还是环境变量.issue"]["path"] == ip

    # 行为:立场、表态、派活、连边
    client.post(f"/api/collect/act/issue/position/{ip}", json={"claim": "加一个 settings.json"})
    client.post(f"/api/collect/act/issue/position/{ip}", json={"claim": "只用环境变量"})
    client.post(f"/api/collect/act/issue/spawn/{ip}", json={"position": "p2", "work_id": "work_try"})
    r = client.post(f"/api/collect/act/issue/argue/{ip}", json={"position": "p2", "stance": 1, "work_id": "work_try",
                                                                  "evidence": {"work_id": "work_try", "rounds": [9]}}).json()
    client.post(f"/api/collect/act/issue/argue/{ip}", json={"position": "p1", "stance": -1, "comment": "多一份状态"})
    v = client.get(f"/api/collect/issue/{ip}").json()["body"]
    assert [p["id"] for p in v["positions"]] == ["p2", "p1"] and v["positions"][0]["credence"] == 1
    assert v["positions"][0]["spawned_works"] == ["work_try"]
    assert client.post(f"/api/collect/act/issue/argue/{ip}", json={"position": "p9", "stance": 1}).status_code == 404
    assert client.post(f"/api/collect/act/issue/nope/{ip}", json={}).status_code == 404

    # decide:两个相邻提交,各在自己的层,同一个 Decision trailer
    cp = "memory.talk/配置/配置只来自环境变量"
    r = client.post(f"/api/collect/act/issue/decide/{ip}", json={"position": "p2", "card": cp, "context": "memory.talk v5",
                                                                  "reason": "环境变量够用"}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["card"] == cp
    card = client.get(f"/api/collect/card/{cp}").json()
    assert card["title"] == "只用环境变量" and card["body"]["issue"] == ip and card["body"]["context"] == "memory.talk v5"
    log = _log(client)
    first, second = log.split("\n\n")[0:2]
    assert first.startswith(f"[card] write {cp}") and f"[issue] decide {ip}#p2" in log
    dec = [l for l in log.splitlines() if l.startswith("Decision:")]
    assert len(dec) == 2 and dec[0] == dec[1]
    assert "By: alice" in log and "Reason: 环境变量够用" in log
    assert "[card]" not in _log(client, "layer/issue") and "[issue]" not in _log(client, "layer/card")
    assert client.post(f"/api/collect/act/issue/decide/{ip}", json={"position": "p2", "card": cp}).status_code == 409

    # 守卫:改卡的提交碰不到 .issue/ 里的文件(服务层直接试)
    from services.collect import CollectError, Ctx
    svc = client.app.state.collect
    try:
        svc.commit("card", "touch", {f"{ip}.issue/issue.json": b"{}"}, [], "", Ctx())
        assert False, "应当被拒"
    except CollectError as e:
        assert e.code == "guard" and "[issue]" in str(e)

    # 改卡、历史、读旧版本、删
    client.put(f"/api/collect/card/{cp}", json={"data": {"body": "只用环境变量。配置文件是多出来的一份状态。"}, "reason": "补理由"})
    hist = client.get(f"/api/collect/history/card/{cp}").json()
    assert [h["subject"][:12] for h in hist] == ["[card] edit ", "[card] write"]
    old = client.get(f"/api/collect/card/{cp}", params={"rev": hist[1]["sha"]}).json()
    assert old["body"]["body"] == "只用环境变量"
    assert client.get("/api/collect/card").json()["subdirs"][0]["dir"] == "memory.talk"
    assert "只用环境变量" in client.get("/api/collect/card/recall").text
    hits = client.get("/api/collect/search", params={"q": "一份状态", "layer": "card"}).json()
    assert hits and hits[0]["path"] == cp
    assert {h["layer"] for h in client.get("/api/collect/search", params={"q": "环境变量"}).json()} == {"issue", "card"}

    # 对卡开讨论页:两个提交
    r = client.post(f"/api/collect/act/card/discuss/{cp}", json={"issue": "memory.talk/配置/要不要加配置文件", "question": "要不要加?"})
    assert r.status_code == 200 and r.json()["card"] == cp
    assert client.get(f"/api/collect/card/{cp}").json()["body"]["issue"] == "memory.talk/配置/要不要加配置文件"
    assert "Discussion:" in _log(client)

    assert client.delete(f"/api/collect/origin/memory.talk/配置/旧方案.md").status_code == 204
    assert client.get("/api/collect/origin/memory.talk/配置/旧方案.md").status_code == 404
    assert client.get("/api/collect/nope").status_code == 404


def test_manager_and_inbox(client):
    t = client.post("/api/works", json={"goal": "管配置这一片"}).json()
    ip = "memory.talk/配置/该走文件还是环境变量"
    client.post(f"/api/collect/issue/{ip}", json={"data": {"question": "q"}})
    assert client.get("/api/collect/manager", params={"path": ip}).json() is None
    assert [o["path"] for o in client.get("/api/collect/managed").json()] == [ip]          # 没人管

    # 主题文件夹绑 work;之后这一片(不分层)的变动都进它的收件箱
    m = client.put("/api/collect/manager", params={"path": "memory.talk"}, json={"work": t["id"]}).json()
    assert m == {"dir": "memory.talk", "work": t["id"]}
    assert client.get("/api/collect/manager", params={"path": ip}).json()["work"] == t["id"]
    assert [o["path"] for o in client.get("/api/collect/managed", params={"work": t["id"]}).json()] == [ip]
    assert client.get("/api/collect/managed").json() == []

    client.post(f"/api/collect/act/issue/position/{ip}", json={"claim": "a"}, headers=H)
    client.post("/api/collect/origin/memory.talk/资料.md", json={"content": "x"})
    client.post("/api/collect/card/memory.talk/一张卡", json={"data": {"title": "一张卡"}}, headers={"X-Memory-Talk-Work": t["id"]})
    inbox = client.get(f"/api/works/{t['id']}/inbox").json()
    assert [(i["layer"], i["path"], i["routed_by"]) for i in inbox] == [
        ("issue", ip, "memory.talk"), ("origin", "memory.talk/资料.md", "memory.talk")]   # 自己(带 X-Memory-Talk-Work)造成的不投给自己
    assert inbox[0]["by"] == "alice" and inbox[0]["subject"].startswith("position")

    # 对象自己目录下的 manager.json 更近,优先;解绑回到上层
    t2 = client.post("/api/works", json={"goal": "专管这个 issue"}).json()
    client.put("/api/collect/manager", params={"path": ip}, json={"work": t2["id"]})
    assert client.get("/api/collect/manager", params={"path": ip}).json() == {"dir": f"{ip}.issue", "work": t2["id"]}
    client.post(f"/api/collect/act/issue/position/{ip}", json={"claim": "b"})
    assert client.get(f"/api/works/{t2['id']}/inbox").json()[-1]["path"] == ip
    assert client.delete("/api/collect/manager", params={"path": ip}).status_code == 204
    assert client.get("/api/collect/manager", params={"path": ip}).json()["work"] == t["id"]
    # manager.json 在 .issue/ 里随 [issue] 提交,在普通目录里归最底层
    log = _log(client)
    assert f"[issue] manage {ip}.issue" in log and "[origin] manage memory.talk by" in log


def test_user_layer(client):
    schema = """
layer: decision
format: markdown+frontmatter
title: title
description: 一个决定
fields:
  title:    {type: string, required: true}
  chosen:   {type: string, required: true}
  rejected: {type: "list[string]"}
  issue:    {type: ref, layer: issue}
"""
    r = client.post("/api/collect/layers", json={"name": "decision", "schema_yaml": schema})
    assert r.status_code == 201, r.text
    assert [l["name"] for l in client.get("/api/collect/layers").json()] == ["origin", "issue", "card", "decision"]
    assert r.json()["fields"]["issue"] == {"type": "ref", "required": False, "ref": "issue", "description": ""}
    assert r.json()["behaviors"] == []

    r = client.post("/api/collect/decision/memory.talk/配置/定了用环境变量",
                    json={"data": {"title": "定了用环境变量", "chosen": "环境变量", "rejected": ["配置文件", "两者都要"],
                                   "issue": "memory.talk/配置/该走文件还是环境变量", "body": "因为……"}})
    assert r.status_code == 201, r.text
    d = client.get("/api/collect/decision/memory.talk/配置/定了用环境变量").json()
    assert d["body"]["rejected"] == ["配置文件", "两者都要"] and d["body"]["body"] == "因为……"
    assert client.post("/api/collect/decision/x", json={"data": {"title": "缺 chosen"}}).status_code == 422
    assert "[decision] write" in _log(client, "layer/decision")
    tree = client.get("/api/collect/tree", params={"path": "memory.talk/配置"}).json()
    assert tree[0]["name"] == "定了用环境变量.decision" and tree[0]["layer"] == "decision"
    # 重启后层还在(layers 文件 + schemas/ 都在仓库里)
    from config import load_config, load_runtime_config
    from main import create_app
    app2 = create_app(load_config(), load_runtime_config())
    assert app2.state.collect.order[-1] == "decision"
