"""metas/recent -- recently changed objects, paginated. See README.md."""
IP = "memory.talk/配置/该走文件还是环境变量"
CP = "memory.talk/配置/配置只来自环境变量"


def _seed(client):
    client.post("/api/metas/origin/memory.talk/资料.md", json={"content": "x"})
    client.post(f"/api/metas/issue/{IP}", json={"files": {"readme.md": ""}})
    client.post(f"/api/metas/card/{CP}", json={"files": {"readme.md": "t"}})
    client.put(f"/api/metas/issue/{IP}", json={"files": {"positions/甲.md": "a"}, "subject": f"position {IP}: 甲"})


def test_objects_once_each_newest_first_with_touched_files(client):
    _seed(client)
    page = client.get("/api/metas/recent").json()
    assert [(i["layer"], i["path"], i["files"]) for i in page["items"]] == [
        ("issue", IP, ["positions/甲.md"]), ("card", CP, ["readme.md"]), ("origin", "memory.talk/资料.md", [])]
    assert page["items"][0]["subject"] == f"[issue] position {IP}: 甲" and page["items"][0]["title"] == "该走文件还是环境变量"
    assert page["next"] is None


def test_filters_by_layer_and_path(client):
    _seed(client)
    assert [i["path"] for i in client.get("/api/metas/recent", params={"layer": "card"}).json()["items"]] == [CP]
    assert [i["layer"] for i in client.get("/api/metas/recent", params={"path": "memory.talk/配置"}).json()["items"]] == ["issue", "card"]
    assert client.get("/api/metas/recent", params={"layer": "nope"}).status_code == 404


def test_pagination_walks_down_the_log(client):
    _seed(client)
    first = client.get("/api/metas/recent", params={"limit": 1}).json()
    assert [i["layer"] for i in first["items"]] == ["issue"] and first["next"]
    second = client.get("/api/metas/recent", params={"limit": 1, "before": first["next"]}).json()
    assert [i["layer"] for i in second["items"]] == ["card"] and second["next"]
    rest = client.get("/api/metas/recent", params={"before": second["next"]}).json()
    assert [i["layer"] for i in rest["items"]] == ["origin"] and rest["next"] is None            # issue 的更早一次提交不再出现:去重是全局的


def test_mechanism_files_do_not_count(client):
    assert client.get("/api/metas/recent").json() == {"items": [], "next": None}       # 只有 metas.json 的始祖提交
