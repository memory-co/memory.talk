"""metas/tree -- tree (per layer / recursive). See README.md."""
IP = "memory.talk/配置/该走文件还是环境变量"
CP = "memory.talk/配置/配置只来自环境变量"


def _seed(client):
    client.post(f"/api/metas/card/{CP}", json={"files": {"readme.md": "多一份状态要同步"}})
    client.post("/api/metas/card/其他/一张卡", json={"files": {"readme.md": ""}})
    client.post(f"/api/metas/issue/{IP}", json={"files": {"readme.md": "背景", "positions/只用环境变量.md": "够用"}})


def test_recursive_tree_per_layer_lists_objects_flat(client):
    _seed(client)
    cards = client.get("/api/metas/tree", params={"layer": "card", "recursive": 1}).json()["items"]
    assert [(i["path"], i["kind"]) for i in cards] == [(CP, "object"), ("其他/一张卡", "object")]
    only = client.get("/api/metas/tree", params={"path": "memory.talk/配置", "layer": "issue", "recursive": 1}).json()["items"]
    assert [i["path"] for i in only] == [IP]
    assert client.get("/api/metas/tree", params={"layer": "nope"}).status_code == 404


def test_layer_filter_keeps_directories_to_navigate(client):
    _seed(client)
    top = client.get("/api/metas/tree", params={"layer": "card"}).json()["items"]
    assert [(i["name"], i["kind"]) for i in top] == [("memory.talk", "dir"), ("其他", "dir")]


def test_tree_folds_objects_into_one_item(client):
    _seed(client)
    items = {i["name"]: i for i in client.get("/api/metas/tree", params={"path": "memory.talk/配置"}).json()["items"]}
    assert items["配置只来自环境变量.card"]["kind"] == "object" and items["该走文件还是环境变量.issue"]["layer"] == "issue"
