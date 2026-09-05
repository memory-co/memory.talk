"""FastAPI 实例:装配 services、挂路由、错误映射。"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from config import Config, RuntimeConfig, load_config, load_runtime_config
from controllers import cards, issues, servers, system, tasks
from models.server import ServerError
from services.card import CardExists, CardNotFound, CardService
from services.issue import IssueNotFound, IssueService, PositionNotFound
from services.servers import ServerService
from services.store import GitError, StoreService
from services.task import MemberNotFound, TaskConflict, TaskNotFound, TaskService


def create_app(config: Config | None = None, runtime: RuntimeConfig | None = None) -> FastAPI:
    config = config or load_config()
    runtime = runtime or load_runtime_config()
    app = FastAPI(title="memory.talk v5", version="5.0.0a0",
                  description="task / issue / card 三层工作台 + 协议 server。")

    store = StoreService(config)
    card_svc = CardService(store)
    issue_svc = IssueService(store, card_svc)
    server_svc = ServerService(runtime)
    task_svc = TaskService(store, server_svc)
    app.state.config, app.state.runtime = config, runtime
    app.state.store, app.state.cards, app.state.issues = store, card_svc, issue_svc
    app.state.servers, app.state.tasks = server_svc, task_svc

    for r in (system.router, tasks.router, servers.router, cards.router, issues.router):
        app.include_router(r)

    def _err(status: int, code: str):
        async def handler(_: Request, exc: Exception):
            return JSONResponse({"error": code, "message": str(exc)}, status_code=status)
        return handler

    for exc_type in (CardNotFound, IssueNotFound, PositionNotFound, TaskNotFound, MemberNotFound):
        app.add_exception_handler(exc_type, _err(404, "not_found"))
    app.add_exception_handler(CardExists, _err(409, "exists"))
    app.add_exception_handler(TaskConflict, _err(409, "conflict"))
    app.add_exception_handler(GitError, _err(500, "git"))

    @app.exception_handler(ServerError)
    async def _server(_: Request, exc: ServerError):
        status = {"bad_uri": 400, "cmd_not_found": 400, "no_server": 400, "platform": 502}.get(exc.code, 500)
        return JSONResponse({"error": exc.code, "message": str(exc)}, status_code=status)

    return app
