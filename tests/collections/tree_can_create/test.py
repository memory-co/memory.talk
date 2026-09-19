"""collections/tree_can_create -- can_create and candidate on the tree endpoint. See README.md."""
IP = "memory.talk/配置/该走文件还是环境变量"


def test_plain_directory_lists_object_kinds_per_layer(client):
    v = client.get("/api/collections/tree", params={"path": "memory.talk/配置"}).json()
    assert v["layer"] is None
    assert [(o["layer"], o["example"], o["can"]) for o in v["can_create"]["objects"]] == [("issue", "{name}.issue", True), ("card", "{name}.card", True)]
    assert v["can_create"]["files"] == [{"layer": "origin", "can": True}]


def test_object_directory_lists_file_kinds_with_state(client):
    client.post(f"/api/collections/issue/{IP}", json={"files": {"readme.md": "", "positions/甲.md": "a"}})
    v = client.get("/api/collections/tree", params={"path": f"{IP}.issue"}).json()
    assert v["layer"] == "issue" and v["can_create"]["objects"] == []
    readme, position = v["can_create"]["files"]
    assert (readme["example"], readme["can"], readme["reason"], readme["existing"]) == ("readme.md", False, "固定文件,已存在", ["readme.md"])
    assert (position["example"], position["name"], position["can"], position["existing"]) == ("positions/{name}.md", "主张", True, ["positions/甲.md"])


def test_inside_an_object_items_are_its_files(client):
    client.post(f"/api/collections/issue/{IP}", json={"files": {"readme.md": "", "positions/甲.md": "a"}})
    v = client.get("/api/collections/tree", params={"path": f"{IP}.issue"}).json()
    assert [(i["name"], i["kind"], i["layer"], i.get("object"), i.get("rel")) for i in v["items"]] == [
        ("positions", "dir", None, None, None), ("readme.md", "file", "issue", IP, "readme.md")]
    assert {f["layer"] for f in v["can_create"]["files"]} == {"issue"}
    inner = client.get("/api/collections/tree", params={"path": f"{IP}.issue/positions"}).json()["items"]
    assert [(i["name"], i["rel"]) for i in inner] == [("甲.md", "positions/甲.md")]


def test_subdirectory_only_lists_kinds_that_land_there(client):
    client.post(f"/api/collections/issue/{IP}", json={"files": {"readme.md": ""}})
    v = client.get("/api/collections/tree", params={"path": f"{IP}.issue/positions"}).json()
    assert [f["example"] for f in v["can_create"]["files"]] == ["positions/{name}.md"]


def test_candidate_in_a_plain_directory_is_an_object_name(client):
    ok = client.get("/api/collections/tree", params={"path": "memory.talk/配置", "candidate": "要不要加配置文件.issue"}).json()["candidate"]
    assert ok == {"name": "要不要加配置文件.issue", "matches": {"layer": "issue", "name": "要不要加配置文件"}, "exists": False, "can": True}
    client.post(f"/api/collections/issue/{IP}", json={"files": {"readme.md": ""}})
    dup = client.get("/api/collections/tree", params={"path": "memory.talk/配置", "candidate": "该走文件还是环境变量.issue"}).json()["candidate"]
    assert dup["exists"] and not dup["can"]
    no = client.get("/api/collections/tree", params={"path": "memory.talk/配置", "candidate": "笔记.txt"}).json()["candidate"]
    assert no["matches"] is None and not no["can"]


def test_candidate_in_an_object_is_a_file_path(client):
    client.post(f"/api/collections/issue/{IP}", json={"files": {"readme.md": ""}})
    q = lambda c: client.get("/api/collections/tree", params={"path": f"{IP}.issue", "candidate": c}).json()["candidate"]
    assert q("positions/走配置文件.md") == {"name": "positions/走配置文件.md", "matches": {"pattern": "^positions/(?P<name>[^/]+)\\.md$", "label": "立场"}, "exists": False, "can": True}
    assert q("readme.md")["reason"] == "已存在"
    assert q("notes.txt")["matches"] is None and "不匹配" in q("notes.txt")["reason"]
