"""search -- one query fans out to every service. See README.md."""
IP = "memory.talk/配置/该走文件还是环境变量"


def _seed(client):
    client.post("/api/works", json={"goal": "把配置改成环境变量"})
    client.post("/api/works", json={"goal": "写文档"})
    client.post(f"/api/collections/issue/{IP}", json={"files": {"readme.md": "配置该走文件还是环境变量?", "positions/只用环境变量.md": "够用"}})
    client.post("/api/collections/card/其他/一张卡", json={"files": {"readme.md": "多一份状态要同步"}})
    client.put("/api/users/alice", json={"display_name": "环境变量爱好者"})


def test_hits_come_grouped_by_kind(client):
    _seed(client)
    r = client.get("/api/search", params={"q": "环境变量"}).json()
    kinds = [h["kind"] for h in r["hits"]]
    assert kinds == sorted(kinds, key=["work", "collection", "user"].index) and set(kinds) == {"work", "collection", "user"}
    work = next(h for h in r["hits"] if h["kind"] == "work")
    assert work["title"] == "把配置改成环境变量" and work["status"] == "todo"
    coll = next(h for h in r["hits"] if h["kind"] == "collection")
    assert (coll["layer"], coll["id"], coll["file"], coll["line"]) == ("issue", IP, f"{IP}.issue/readme.md", 1)
    user = next(h for h in r["hits"] if h["kind"] == "user")
    assert (user["id"], user["title"]) == ("alice", "环境变量爱好者")
    assert r["counts"] == {"work": 1, "collection": 1, "user": 1}


def test_collections_search_is_grep_over_every_file(client):
    _seed(client)
    hits = client.get("/api/search", params={"q": "一份状态"}).json()["hits"]
    assert [(h["kind"], h["layer"], h["id"]) for h in hits] == [("collection", "card", "其他/一张卡")]


def test_limit_is_per_kind_and_counts_are_before_truncation(client):
    _seed(client)
    r = client.get("/api/search", params={"q": "配", "limit": 1}).json()
    assert [h["kind"] for h in r["hits"]] == ["work", "collection"] and r["counts"]["work"] == 1 and r["counts"]["collection"] >= 1


def test_no_match_and_empty_query(client):
    _seed(client)
    assert client.get("/api/search", params={"q": "不存在的词"}).json() == {"query": "不存在的词", "hits": [], "counts": {}}
    assert client.get("/api/search", params={"q": ""}).status_code == 422
