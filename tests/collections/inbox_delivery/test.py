"""collections/inbox_delivery -- routing changes to a work's inbox. See README.md."""
import pytest

pytestmark = pytest.mark.skip(reason="/api/collections/manager 暂时注释掉了,等 work 实现后一起启用")

IP = "memory.talk/配置/该走文件还是环境变量"


def _managed(client):
    w = client.post("/api/works", json={"goal": "管配置这一片"}).json()
    client.post(f"/api/collections/issue/{IP}", json={"files": {"readme.md": ""}})
    client.put("/api/collections/manager", params={"path": "memory.talk"}, json={"work": w["id"]})
    return w


def test_changes_under_the_folder_are_delivered_regardless_of_layer(client, H):
    w = _managed(client)
    client.post(f"/api/collections/act/issue/position/{IP}", json={"claim": "a"}, headers=H("alice"))
    client.post("/api/collections/origin/memory.talk/资料.md", json={"content": "x"})
    items = client.get(f"/api/works/{w['id']}/inbox").json()
    assert [(i["layer"], i["path"], i["routed_by"]) for i in items] == [("issue", IP, "memory.talk"), ("origin", "memory.talk/资料.md", "memory.talk")]
    assert items[0]["by"] == "alice" and items[0]["subject"].startswith("position")


def test_self_caused_changes_are_not_delivered_back(client, H):
    w = _managed(client)
    client.post("/api/collections/card/memory.talk/一张卡", json={"files": {"readme.md": "一张卡"}}, headers={**H("alice"), "X-Memory-Talk-Work": w["id"]})
    assert client.get(f"/api/works/{w['id']}/inbox").json() == []


def test_manager_json_changes_are_mechanism_not_content(client):
    w = _managed(client)
    assert client.get(f"/api/works/{w['id']}/inbox").json() == []          # 绑定本身没投


def test_unmanaged_changes_go_to_the_unmanaged_log(client, svc):
    client.post("/api/collections/card/孤儿/一张卡", json={"files": {"readme.md": "一张卡"}})
    from memorytalk.backend.providers import LocalFS
    store = svc.store.provider                                    # 两种 store 落点不同,各看各的
    if isinstance(store, LocalFS):
        assert "孤儿/一张卡" in store.read("unmanaged.jsonl").decode()
    else:
        rows = store.select(svc.store.work_repo.logs).where(svc.store.work_repo.logs.c.key == "unmanaged").all()
        assert any("孤儿/一张卡" in r["line"]["path"] for r in rows)
