"""前端构建产物的静态托管。页面用 hash 路由，API 保留独立的路径空间。"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def mount_frontend(app: FastAPI, directory: Path | None = None) -> None:
    root = directory if directory is not None else Path(__file__).resolve().parents[1] / "frontend" / "dist"
    if not (root / "index.html").is_file():
        return

    @app.get("/", include_in_schema=False)
    def frontend():
        return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})

    if (root / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=root / "assets"), name="frontend-assets")
