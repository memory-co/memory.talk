"""metas/migration -- old collections/ + collections.json still load. See README.md."""
import os
from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import PASSWORD


def _app():
    from memorytalk.backend.config import load_config, load_runtime_config
    from memorytalk.backend.main import create_app
    return create_app(load_config(), load_runtime_config())


def _legacy(home: Path) -> str:
    """起一次 app 写一张卡,然后把数据改成改名前的样子:目录叫 collections/,锚定文件叫 collections.json。"""
    with TestClient(_app()) as c:
        tok = c.post("/api/auth/setup", json={"password": PASSWORD}).json()["token"]
        c.headers["Authorization"] = f"Bearer {tok}"
        c.post("/api/metas/card/x/老卡", json={"files": {"readme.md": "改名前写的"}})
        repo = c.app.state.metas.repo
        repo.commit("origin", "[origin] pretend old anchor", {"collections.json": repo.read("metas.json")}, ["metas.json"], layer_of=lambda p: "origin")
    (home / "metas").rename(home / "collections")
    return tok


def test_first_start_after_rename_moves_dir_and_anchor(home):
    h = Path(os.environ["MEMORY_TALK_HOME"])
    tok = _legacy(h)
    with TestClient(_app()) as c:
        c.headers["Authorization"] = f"Bearer {tok}"
        assert (h / "metas").is_dir() and not (h / "collections").exists()
        r = c.get("/api/metas/config").json()
        assert [l["name"] for l in r["config"]["layers"]] == ["origin", "issue", "card"]
        assert r["history"][0]["subject"] == "[origin] metas: rename collections.json to metas.json"
        assert c.get("/api/metas/card/x/老卡").json()["files"]["readme.md"] == "改名前写的"
        names = [i["name"] for i in c.get("/api/metas/tree").json()["items"]]
        assert "collections.json" not in names and "metas.json" not in names
        n = len(r["history"])
    with TestClient(_app()) as c:                                    # 再起一次:不再重复提交
        c.headers["Authorization"] = f"Bearer {tok}"
        assert len(c.get("/api/metas/config").json()["history"]) == n
