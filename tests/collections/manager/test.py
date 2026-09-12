"""collections/manager -- nearest manager.json. See README.md."""
from tests._util import git_log
import pytest

pytestmark = pytest.mark.skip(reason="/api/collections/manager 暂时注释掉了,等 work 实现后一起启用")

IP = "memory.talk/配置/该走文件还是环境变量"


def _setup(client):
    w = client.post("/api/works", json={"goal": "管配置这一片"}).json()
    client.post(f"/api/collections/issue/{IP}", json={"files": {"readme.md": ""}})
    return w


def test_unmanaged_object_is_listed_until_a_manager_exists(client):
    w = _setup(client)
    assert client.get("/api/collections/manager", params={"path": IP}).json() is None
    assert [o["path"] for o in client.get("/api/collections/managed").json()] == [IP]
    client.put("/api/collections/manager", params={"path": "memory.talk"}, json={"work": w["id"]})
    assert client.get("/api/collections/managed").json() == []
    assert [o["path"] for o in client.get("/api/collections/managed", params={"work": w["id"]}).json()] == [IP]


def test_folder_manager_covers_objects_beneath(client):
    w = _setup(client)
    m = client.put("/api/collections/manager", params={"path": "memory.talk"}, json={"work": w["id"]}).json()
    assert m == {"dir": "memory.talk", "work": w["id"]}
    assert client.get("/api/collections/manager", params={"path": IP}).json()["work"] == w["id"]


def test_object_level_manager_wins_over_folder(client):
    w = _setup(client)
    w2 = client.post("/api/works", json={"goal": "专管这个 issue"}).json()
    client.put("/api/collections/manager", params={"path": "memory.talk"}, json={"work": w["id"]})
    client.put("/api/collections/manager", params={"path": IP}, json={"work": w2["id"]})
    assert client.get("/api/collections/manager", params={"path": IP}).json() == {"dir": f"{IP}.issue", "work": w2["id"]}


def test_unset_falls_back_to_the_parent_folder(client):
    w = _setup(client)
    w2 = client.post("/api/works", json={"goal": "专管"}).json()
    client.put("/api/collections/manager", params={"path": "memory.talk"}, json={"work": w["id"]})
    client.put("/api/collections/manager", params={"path": IP}, json={"work": w2["id"]})
    assert client.delete("/api/collections/manager", params={"path": IP}).status_code == 200
    assert client.get("/api/collections/manager", params={"path": IP}).json()["work"] == w["id"]


def test_manager_json_belongs_to_the_layer_of_its_directory(client):
    w = _setup(client)
    client.put("/api/collections/manager", params={"path": "memory.talk"}, json={"work": w["id"]})
    client.put("/api/collections/manager", params={"path": IP}, json={"work": w["id"]})
    log = git_log(client)
    assert "[origin] manage memory.talk by" in log and f"[issue] manage {IP}.issue" in log
