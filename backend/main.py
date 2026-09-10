"""FastAPI 实例:装配 services、挂路由、错误映射。"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from config import Config, RuntimeConfig, load_config, load_runtime_config
from controllers import collections, servers, system, works
from models.server import ServerError
from services.collections import CollectionsError, CollectionsService
from services.servers import ServerService
from services.store import StoreService
from services.work import SessionNotFound, WorkConflict, WorkNotFound, WorkService


def create_app(config: Config | None = None, runtime: RuntimeConfig | None = None) -> FastAPI:
    config = config or load_config()
    runtime = runtime or load_runtime_config()
    app = FastAPI(title="memory.talk v5", version="5.0.0a0",
                  description="work 树 + Collections(origin / issue / card 三层,可加用户层)+ 协议 server。")

    store = StoreService(config)
    collect_svc = CollectionsService(config, store.works)
    server_svc = ServerService(runtime)
    work_svc = WorkService(store, server_svc)
    app.state.config, app.state.runtime = config, runtime
    app.state.store, app.state.collections = store, collect_svc
    app.state.servers, app.state.works = server_svc, work_svc

    for r in (system.router, works.router, servers.router, collections.router):
        app.include_router(r)

    def _err(status: int, code: str):
        async def handler(_: Request, exc: Exception):
            return JSONResponse({"error": code, "message": str(exc)}, status_code=status)
        return handler

    for exc_type in (WorkNotFound, SessionNotFound):
        app.add_exception_handler(exc_type, _err(404, "not_found"))
    app.add_exception_handler(WorkConflict, _err(409, "conflict"))

    @app.exception_handler(CollectionsError)
    async def _collect(_: Request, exc: CollectionsError):
        return JSONResponse({"error": exc.code, "message": str(exc)}, status_code=exc.status)

    @app.exception_handler(ServerError)
    async def _server(_: Request, exc: ServerError):
        status = {"bad_uri": 400, "cmd_not_found": 400, "no_server": 400, "platform": 502}.get(exc.code, 500)
        return JSONResponse({"error": exc.code, "message": str(exc)}, status_code=status)

    return app
