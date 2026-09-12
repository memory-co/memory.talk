"""collections/tree_and_search -- catalog, grep. See README.md."""
IP = "memory.talk/配置/该走文件还是环境变量"


def _seed(client):
    client.post("/api/collections/card/memory.talk/配置/配置只来自环境变量", json={"data": {"title": "配置只来自环境变量", "body": "多一份状态要同步"}})
    client.post("/api/collections/card/其他/一张卡", json={"data": {"title": "一张卡"}})
    client.post(f"/api/collections/issue/{IP}", json={"files": {"readme.md": "背景", "positions/只用环境变量.md": "够用"}})


def test_catalog_groups_by_directory(client):
    _seed(client)
    cat = client.get("/api/collections/card").json()
    assert {d["dir"] for d in cat["subdirs"]} == {"memory.talk", "其他"}
    only = client.get("/api/collections/card", params={"dir": "memory.talk"}).json()
    assert [o["title"] for d in only["subdirs"] for o in d["objects"]] == ["配置只来自环境变量"]


def test_issue_catalog_uses_the_directory_name(client):
    _seed(client)
    cat = client.get("/api/collections/issue", params={"dir": "memory.talk/配置"}).json()
    assert [o["title"] for o in cat["objects"]] == ["该走文件还是环境变量"]


def test_tree_folds_objects_into_one_item(client):
    _seed(client)
    items = {i["name"]: i for i in client.get("/api/collections/tree", params={"path": "memory.talk/配置"}).json()}
    assert items["配置只来自环境变量.card"]["kind"] == "object" and items["该走文件还是环境变量.issue"]["layer"] == "issue"


def test_search_is_grep_optionally_per_layer(client):
    _seed(client)
    hits = client.get("/api/collections/search", params={"q": "一份状态", "layer": "card"}).json()
    assert hits and hits[0]["path"] == "memory.talk/配置/配置只来自环境变量"
    inside = client.get("/api/collections/search", params={"q": "够用"}).json()
    assert [(h["layer"], h["path"], h["file"]) for h in inside] == [("issue", IP, f"{IP}.issue/positions/只用环境变量.md")]
    assert client.get("/api/collections/search", params={"q": "不存在的词"}).json() == []
