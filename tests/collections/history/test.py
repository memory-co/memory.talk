"""collections/history -- git log per object, read at revision. See README.md."""
CP = "memory.talk/配置/配置只来自环境变量"


def test_history_lists_edits_newest_first_with_reason(client):
    client.post(f"/api/collections/card/{CP}", json={"data": {"title": "t", "body": "v1"}, "reason": "初写"})
    client.put(f"/api/collections/card/{CP}", json={"data": {"body": "v2"}, "reason": "补理由"})
    hist = client.get(f"/api/collections/history/card/{CP}").json()
    assert [h["subject"] for h in hist] == [f"[card] edit {CP}", f"[card] write {CP}"]
    assert hist[0]["body"] == "Reason: 补理由"


def test_read_at_revision_returns_the_old_body(client):
    client.post(f"/api/collections/card/{CP}", json={"data": {"title": "t", "body": "v1"}})
    client.put(f"/api/collections/card/{CP}", json={"data": {"body": "v2"}})
    old_sha = client.get(f"/api/collections/history/card/{CP}").json()[1]["sha"]
    assert client.get(f"/api/collections/card/{CP}", params={"rev": old_sha}).json()["body"]["body"] == "v1"


def test_history_of_missing_object_is_404(client):
    assert client.get("/api/collections/history/card/nope").status_code == 404
