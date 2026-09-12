import asyncio

import httpx
from fastapi import FastAPI

from memorytalk.backend.gateway import mount_frontend


def request(app, path):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.get(path)
    return asyncio.run(run())


def test_frontend_build_is_served_without_shadowing_api(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text('<div id="root">memory.talk</div>')
    (tmp_path / "assets" / "app.js").write_text('console.log("memory.talk")')
    app = FastAPI()

    @app.get("/api/check")
    async def check():
        return {"data": "ok"}

    mount_frontend(app, tmp_path)
    page = request(app, "/")
    assert page.status_code == 200 and 'id="root"' in page.text
    assert page.headers["cache-control"] == "no-cache"
    assert request(app, "/assets/app.js").status_code == 200
    assert '"data":"ok"' in request(app, "/api/check").text
    assert request(app, "/api/unknown").status_code == 404
    assert request(app, "/assets/missing.js").status_code == 404


def test_missing_build_does_not_add_a_broken_frontend_route(tmp_path):
    app = FastAPI()
    mount_frontend(app, tmp_path)
    assert request(app, "/").status_code == 404
    assert request(app, "/openapi.json").status_code == 200
