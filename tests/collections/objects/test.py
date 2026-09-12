"""collections/objects -- CRUD across the three built-in layers. See README.md."""
IP = "memory.talk/配置/该走文件还是环境变量"
CP = "memory.talk/配置/配置只来自环境变量"


def test_issue_is_a_suffixed_dir_titled_by_its_name(client, svc):
    r = client.post(f"/api/collections/issue/{IP}", json={"files": {"readme.md": "背景……"}})
    assert r.status_code == 201 and r.json()["title"] == "该走文件还是环境变量" and r.json()["files"] == ["readme.md"]
    assert svc.collections.repo.read(f"{IP}.issue/readme.md") == "背景……".encode()


def test_empty_issue_still_gets_its_readme(client, svc):
    assert client.post(f"/api/collections/issue/{IP}", json={}).status_code == 201
    assert svc.collections.repo.read(f"{IP}.issue/readme.md") == b""


def test_issue_files_are_validated_as_a_directory(client):
    assert client.post(f"/api/collections/issue/{IP}", json={"files": {"notes.txt": "x"}}).status_code == 422
    assert client.post(f"/api/collections/issue/{IP}", json={"files": {"meta.yaml": "links: [{type: nope, target: x}]"}}).status_code == 422
    assert client.post(f"/api/collections/issue/{IP}", json={"data": {"question": "q"}}).status_code == 400


def test_card_is_markdown_with_frontmatter(client, svc):
    client.post(f"/api/collections/card/{CP}", json={"data": {"title": "配置只来自环境变量", "context": "v5", "body": "正文"}})
    raw = svc.collections.repo.read(f"{CP}.card/card.md").decode()
    assert raw.startswith("---\ntitle: 配置只来自环境变量\ncontext: v5\n---\n\n正文")
    assert client.get(f"/api/collections/card/{CP}").json()["body"] == {"title": "配置只来自环境变量", "context": "v5", "links": [], "issue": None, "body": "正文"}


def test_card_can_also_be_written_as_a_file(client):
    client.post(f"/api/collections/card/{CP}", json={"files": {"card.md": "---\ntitle: 直接写文件\n---\n\n正文"}})
    assert client.get(f"/api/collections/card/{CP}").json()["title"] == "直接写文件"


def test_origin_is_a_plain_file_with_raw_content(client):
    client.post("/api/collections/origin/memory.talk/配置/旧方案.md", json={"content": "这是原文"})
    assert client.get("/api/collections/origin/memory.talk/配置/旧方案.md").json()["body"] == "这是原文"


def test_three_layers_live_side_by_side(client):
    client.post("/api/collections/origin/memory.talk/配置/旧方案.md", json={"content": "x"})
    client.post(f"/api/collections/issue/{IP}", json={})
    client.post(f"/api/collections/card/{CP}", json={"data": {"title": "t"}})
    names = {i["name"]: i for i in client.get("/api/collections/tree", params={"path": "memory.talk/配置"}).json()}
    assert names["旧方案.md"]["layer"] == "origin"
    assert names["该走文件还是环境变量.issue"]["kind"] == "object" and names["该走文件还是环境变量.issue"]["path"] == IP
    assert names["配置只来自环境变量.card"]["layer"] == "card"


def test_schema_violation_is_422_and_duplicate_is_409(client):
    assert client.post("/api/collections/card/x/缺标题", json={"data": {"context": "v5"}}).status_code == 422
    assert client.post("/api/collections/card/x/多余字段", json={"data": {"title": "t", "score": 1}}).status_code == 422
    client.post(f"/api/collections/issue/{IP}", json={})
    assert client.post(f"/api/collections/issue/{IP}", json={}).status_code == 409


def test_edit_merges_fields(client):
    client.post(f"/api/collections/card/{CP}", json={"data": {"title": "t", "context": "v5", "body": "旧"}})
    body = client.put(f"/api/collections/card/{CP}", json={"data": {"body": "新"}}).json()["body"]
    assert body["body"] == "新" and body["context"] == "v5"


def test_edit_touches_only_the_named_files_and_null_deletes(client):
    client.post(f"/api/collections/issue/{IP}", json={"files": {"readme.md": "r", "positions/甲.md": "a", "positions/乙.md": "b"}})
    o = client.put(f"/api/collections/issue/{IP}", json={"files": {"positions/乙.md": None, "meta.yaml": "summary: 先这样"}}).json()
    assert o["files"] == ["meta.yaml", "positions/甲.md", "readme.md"] and o["body"]["summary"] == "先这样"
    assert client.put(f"/api/collections/issue/{IP}", json={"files": {"readme.md": None}}).status_code == 422   # 必需的不能删


def test_delete_then_404(client):
    client.post("/api/collections/origin/memory.talk/配置/旧方案.md", json={"content": "x"})
    assert client.delete("/api/collections/origin/memory.talk/配置/旧方案.md").status_code == 200
    assert client.get("/api/collections/origin/memory.talk/配置/旧方案.md").status_code == 404
    client.post(f"/api/collections/issue/{IP}", json={"files": {"positions/甲.md": "a"}})
    assert client.delete(f"/api/collections/issue/{IP}").status_code == 200
    assert client.get(f"/api/collections/issue/{IP}").status_code == 404
    assert client.get("/api/collections/nope").status_code == 404
