"""FastAPI 实例:装配 services、挂路由、错误映射。"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from memorytalk.backend.models.result import fail
from memorytalk.backend.gateway import mount_frontend

from memorytalk.backend.config import Config, RuntimeConfig, load_config, load_runtime_config
from memorytalk.backend.controllers import auth, metas, search, system, users, works
from memorytalk.backend.models.work_server import WorkServerError
from memorytalk.backend.services.auth import AuthError, AuthService
from memorytalk.backend.services.metas import MetasError, MetasService
from memorytalk.backend.services.search import SearchService
from memorytalk.backend.services.work_servers import WorkServerService
from memorytalk.backend.services.store import StoreService
from memorytalk.backend.services.users import UserExists, UserNotFound, UserService
from memorytalk.backend.services.work import WorkletNotFound, WorkConflict, WorkNotFound, WorkService


def create_app(config: Config | None = None, runtime: RuntimeConfig | None = None) -> FastAPI:
    config = config or load_config()
    runtime = runtime or load_runtime_config()
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        app.state.work_servers.close()                 # 退出:收掉自己起的 ttyd;tmux 会话照跑

    app = FastAPI(title="memory.talk v5", version="5.0.0a0", lifespan=lifespan,
                  description="work 树 + Metas(origin / issue / card 三层,可加用户层)+ 协议 server。")

    store = StoreService(config)
    collect_svc = MetasService(config, store.work_repo)
    work_server_svc = WorkServerService(runtime)
    work_svc = WorkService(store, work_server_svc)
    user_svc = UserService(store.user_repo, store.work_repo, collect_svc)
    collect_svc.author_of = user_svc.author
    app.state.config, app.state.runtime = config, runtime
    app.state.store, app.state.metas = store, collect_svc
    app.state.work_servers, app.state.works = work_server_svc, work_svc
    app.state.users = user_svc
    app.state.auth = AuthService(user_svc, store.token_repo)
    app.state.search = SearchService(work_svc, collect_svc, user_svc)

    for r in (system.router, auth.router, works.router, users.router, metas.router, search.router):
        app.include_router(r)

    OPEN = {"/api/auth/status", "/api/auth/setup", "/api/auth/login", "/api/system/health"}

    @app.middleware("http")
    async def gate(request: Request, call_next):
        """门(docs/designs/v5/auth.md):没有 admin → 只放 setup;有了 → 没有效 token 的 /api 请求一律 401。前端页面和静态资源不拦。"""
        path = request.url.path
        if path.startswith("/api") and path not in OPEN:
            svc: AuthService = request.app.state.auth
            if svc.setup_required():
                return JSONResponse(fail("setup_required", "还没有 admin 账号,先 POST /api/auth/setup"), status_code=409)
            name = svc.resolve(auth.bearer(request))
            if name is None:
                return JSONResponse(fail("unauthorized", "要登录:Authorization: Bearer <token>"), status_code=401)
            request.state.user = name
        return await call_next(request)

    def _err(status: int, code: str):
        async def handler(_: Request, exc: Exception):
            return JSONResponse(fail(code, str(exc)), status_code=status)
        return handler

    for exc_type in (WorkNotFound, WorkletNotFound, UserNotFound):
        app.add_exception_handler(exc_type, _err(404, "not_found"))
    app.add_exception_handler(WorkConflict, _err(409, "conflict"))
    app.add_exception_handler(UserExists, _err(409, "exists"))

    @app.exception_handler(AuthError)
    async def _auth(_: Request, exc: AuthError):
        return JSONResponse(fail(exc.code, str(exc)), status_code=exc.status)

    @app.exception_handler(MetasError)
    async def _collect(_: Request, exc: MetasError):
        return JSONResponse(fail(exc.code, str(exc)), status_code=exc.status)

    @app.exception_handler(WorkServerError)
    async def _server(_: Request, exc: WorkServerError):
        status = {"bad_uri": 400, "cmd_not_found": 400, "no_server": 400, "platform": 502}.get(exc.code, 500)
        return JSONResponse(fail(exc.code, str(exc)), status_code=status)

    mount_frontend(app)
    return app
