"""works/recall -- catalog injection. See README.md."""


def test_recall_lists_card_titles(client):
    w = client.post("/api/works", json={"goal": "x"}).json()
    client.post("/api/collections/card/memory.talk/配置只来自环境变量", json={"data": {"title": "配置只来自环境变量"}})
    text = client.get(f"/api/works/{w['id']}/recall").json()
    assert "配置只来自环境变量" in text and "memory.talk/" in text


def test_recall_dir_narrows_and_layer_switches(client):
    w = client.post("/api/works", json={"goal": "x"}).json()
    client.post("/api/collections/card/a/卡A", json={"data": {"title": "卡A"}})
    client.post("/api/collections/card/b/卡B", json={"data": {"title": "卡B"}})
    client.post("/api/collections/issue/a/问题A", json={"data": {"question": "问题A?"}})
    assert "卡B" not in client.get(f"/api/works/{w['id']}/recall", params={"dir": "a"}).json()
    assert "问题A?" in client.get(f"/api/works/{w['id']}/recall", params={"layer": "issue"}).json()
