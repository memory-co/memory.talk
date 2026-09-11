"""FastAPI 实例:装配 services、挂路由、错误映射。"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from config import Config, RuntimeConfig, load_config, load_runtime_config
from controllers import collections, system, users, works
from models.work_server import WorkServerError
from services.collections import CollectionsError, CollectionsService
from services.work_servers import WorkServerService
from services.store import StoreService
from services.users import UserNotFound, UserService
from services.work import SessionNotFound, WorkConflict, WorkNotFound, WorkService


def create_app(config: Config | None = None, runtime: RuntimeConfig | None = None) -> FastAPI:
    config = config or load_config()
    runtime = runtime or load_runtime_config()
    app = FastAPI(title="memory.talk v5", version="5.0.0a0",
                  description="work 树 + Collections(origin / issue / card 三层,可加用户层)+ 协议 server。")

    store = StoreService(config)
    collect_svc = CollectionsService(config, store.work_repo)
    work_server_svc = WorkServerService(runtime)
    work_svc = WorkService(store, work_server_svc)
    user_svc = UserService(store.work_repo, collect_svc)
    app.state.config, app.state.runtime = config, runtime
    app.state.store, app.state.collections = store, collect_svc
    app.state.work_servers, app.state.works = work_server_svc, work_svc
    app.state.users = user_svc

    for r in (system.router, works.router, users.router, collections.router):
        app.include_router(r)

    def _err(status: int, code: str):
        async def handler(_: Request, exc: Exception):
            return JSONResponse({"error": code, "message": str(exc)}, status_code=status)
        return handler

    for exc_type in (WorkNotFound, SessionNotFound, UserNotFound):
        app.add_exception_handler(exc_type, _err(404, "not_found"))
    app.add_exception_handler(WorkConflict, _err(409, "conflict"))

    @app.exception_handler(CollectionsError)
    async def _collect(_: Request, exc: CollectionsError):
        return JSONResponse({"error": exc.code, "message": str(exc)}, status_code=exc.status)

    @app.exception_handler(WorkServerError)
    async def _server(_: Request, exc: WorkServerError):
        status = {"bad_uri": 400, "cmd_not_found": 400, "no_server": 400, "platform": 502}.get(exc.code, 500)
        return JSONResponse({"error": exc.code, "message": str(exc)}, status_code=status)

    return app
