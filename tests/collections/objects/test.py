"""collections/objects -- CRUD across the three built-in layers. See README.md."""
IP = "memory.talk/配置/该走文件还是环境变量"
CP = "memory.talk/配置/配置只来自环境变量"


def test_issue_is_a_suffixed_dir_titled_by_its_name(client, svc):
    r = client.post(f"/api/collections/issue/{IP}", json={"files": {"readme.md": "背景……"}})
    assert r.status_code == 201 and r.json()["title"] == "该走文件还是环境变量" and r.json()["files"] == {"readme.md": "背景……"}
    assert svc.collections.repo.read(f"{IP}.issue/readme.md") == "背景……".encode()


def test_card_is_readme_plus_meta(client, svc):
    r = client.post(f"/api/collections/card/{CP}", json={"files": {"readme.md": "只用环境变量。", "meta.yaml": "context: v5\nissue: " + IP}})
    assert r.status_code == 201 and r.json()["title"] == "配置只来自环境变量"
    assert svc.collections.repo.read(f"{CP}.card/meta.yaml").decode() == "context: v5\nissue: " + IP
    assert client.get(f"/api/collections/card/{CP}").json()["files"] == {"meta.yaml": "context: v5\nissue: " + IP, "readme.md": "只用环境变量。"}


def test_origin_is_a_plain_file_with_raw_content(client):
    client.post("/api/collections/origin/memory.talk/配置/旧方案.md", json={"content": "这是原文"})
    o = client.get("/api/collections/origin/memory.talk/配置/旧方案.md").json()
    assert o["content"] == "这是原文" and o["files"] == {} and o["title"] == "旧方案.md"


def test_three_layers_live_side_by_side(client):
    client.post("/api/collections/origin/memory.talk/配置/旧方案.md", json={"content": "x"})
    client.post(f"/api/collections/issue/{IP}", json={"files": {"readme.md": ""}})
    client.post(f"/api/collections/card/{CP}", json={"files": {"readme.md": "t"}})
    names = {i["name"]: i for i in client.get("/api/collections/tree", params={"path": "memory.talk/配置"}).json()}
    assert names["旧方案.md"]["layer"] == "origin"
    assert names["该走文件还是环境变量.issue"]["kind"] == "object" and names["该走文件还是环境变量.issue"]["path"] == IP
    assert names["配置只来自环境变量.card"]["layer"] == "card"


def test_rejections_carry_the_reason(client):
    r = client.post(f"/api/collections/card/{CP}", json={"files": {"meta.yaml": "context: v5"}})
    assert r.status_code == 422 and "缺 readme.md" in r.json()["message"]
    r = client.post(f"/api/collections/card/{CP}", json={"files": {"readme.md": "", "meta.yaml": "score: 1"}})
    assert r.status_code == 422 and "meta.yaml" in r.json()["message"] and "score" in r.json()["message"]
    r = client.post(f"/api/collections/card/{CP}", json={"files": {"readme.md": "", "notes.txt": "x"}})
    assert r.status_code == 422 and "notes.txt" in r.json()["message"]
    assert client.post(f"/api/collections/card/{CP}", json={}).status_code == 400            # 什么都没给


def test_duplicate_is_409_and_missing_is_404(client):
    client.post(f"/api/collections/issue/{IP}", json={"files": {"readme.md": ""}})
    assert client.post(f"/api/collections/issue/{IP}", json={"files": {"readme.md": ""}}).status_code == 409
    assert client.put(f"/api/collections/issue/x/没有", json={"files": {"readme.md": ""}}).status_code == 404
    assert client.get("/api/collections/nope").status_code == 404


def test_edit_touches_only_the_named_files_and_null_deletes(client):
    client.post(f"/api/collections/card/{CP}", json={"files": {"readme.md": "旧", "meta.yaml": "context: v5"}})
    o = client.put(f"/api/collections/card/{CP}", json={"files": {"readme.md": "新"}}).json()
    assert o["files"] == {"meta.yaml": "context: v5", "readme.md": "新"}
    o = client.put(f"/api/collections/card/{CP}", json={"files": {"meta.yaml": None}}).json()
    assert o["files"] == {"readme.md": "新"}
    r = client.put(f"/api/collections/card/{CP}", json={"files": {"readme.md": None}})
    assert r.status_code == 422 and "不能删" in r.json()["message"]
    assert client.put(f"/api/collections/card/{CP}", json={"files": {"readme.md": "新"}}).status_code == 400   # 没变


def test_subject_names_the_commit(client):
    client.post(f"/api/collections/issue/{IP}", json={"files": {"readme.md": ""}, "subject": f"raise {IP}"})
    client.put(f"/api/collections/issue/{IP}", json={"files": {"positions/只用环境变量.md": "够用"}, "subject": f"position {IP}: 只用环境变量"})
    subjects = [h["subject"] for h in client.get(f"/api/collections/history/issue/{IP}").json()]
    assert subjects == [f"[issue] position {IP}: 只用环境变量", f"[issue] raise {IP}"]


def test_delete_then_404(client):
    client.post("/api/collections/origin/memory.talk/配置/旧方案.md", json={"content": "x"})
    assert client.delete("/api/collections/origin/memory.talk/配置/旧方案.md").status_code == 200
    assert client.get("/api/collections/origin/memory.talk/配置/旧方案.md").status_code == 404
    client.post(f"/api/collections/issue/{IP}", json={"files": {"readme.md": "", "positions/甲.md": "a"}})
    assert client.delete(f"/api/collections/issue/{IP}").status_code == 200
    assert client.get(f"/api/collections/issue/{IP}").status_code == 404
