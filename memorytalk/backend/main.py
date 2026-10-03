"""FastAPI 实例:装配 services、挂路由、错误映射。"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from memorytalk.backend.models.result import fail
from memorytalk.backend.gateway import SURFACE_PATH, AuthMiddleware, mount_frontend

from memorytalk.backend.config import Config, RuntimeConfig, load_config, load_runtime_config
from memorytalk.backend.controllers import auth, metas, search, system, users, works
from memorytalk.backend.models.work_server import WorkServerError
from memorytalk.backend.services.auth import AuthError, AuthService, jwt
from memorytalk.backend.services.metas import MetasError, MetasService
from memorytalk.backend.services.search import SearchService
from memorytalk.backend.services.work_servers import WorkServerService
from memorytalk.backend.services.store import StoreService
from memorytalk.backend.services.users import UserExists, UserNotFound, UserService
from memorytalk.backend.services.work import (ColumnNotFound, InputRefused, TraceRejected, WorkletNotFound, WorkConflict,
                                              WorkNotFound, WorkService)
from memorytalk.backend.services.work.viewers import SWEEP_EVERY, Viewers

log = logging.getLogger(__name__)


async def _sweep_viewers(viewers: Viewers) -> None:
    """心跳只在内存里:没人来请求也得定时把超时的人清出 works.viewers。"""
    while True:
        await asyncio.sleep(SWEEP_EVERY)
        try:
            viewers.sweep()
        except Exception:
            log.exception("清 viewers 失败")


async def _reconcile(works: WorkService) -> None:
    """起来以后对一遍(work-node.md §7);等一下再做,让中心先把节点要推进来的那个口子开好。"""
    await asyncio.sleep(1)
    try:
        n = await asyncio.to_thread(works.reconcile)
        if n:
            log.info("让节点接着盯 %d 个工作单元", n)
    except Exception:
        log.exception("和节点对账失败")


def create_app(config: Config | None = None, runtime: RuntimeConfig | None = None) -> FastAPI:
    config = config or load_config()
    runtime = runtime or load_runtime_config()
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        sweeper = asyncio.create_task(_sweep_viewers(app.state.works.viewers))
        reconcile = asyncio.create_task(_reconcile(app.state.works))     # 中心起来了:活着的 agent 现场都让节点盯着
        yield
        reconcile.cancel()
        sweeper.cancel()
        with suppress(asyncio.CancelledError):
            await sweeper
        app.state.work_servers.close()                 # 退出:收掉自己起的 ttyd;tmux 会话照跑

    app = FastAPI(title="memory.talk v5", version="5.0.0a0", lifespan=lifespan,
                  description="work 树 + Metas(origin / issue / card 三层,可加用户层)+ 协议 server。")

    store = StoreService(config)
    collect_svc = MetasService(config, store.work_repo)
    work_server_svc = WorkServerService(runtime, SURFACE_PATH)   # 窗都挂在 /surface 下;下面有哪些窗由它自己定
    work_svc = WorkService(store, work_server_svc)
    user_svc = UserService(store.user_repo, store.work_repo, store.trace_repo, collect_svc)
    collect_svc.author_of = user_svc.author
    app.state.config, app.state.runtime = config, runtime
    app.state.store, app.state.metas = store, collect_svc
    app.state.work_servers, app.state.works = work_server_svc, work_svc
    app.state.users = user_svc
    app.state.auth = AuthService(user_svc, store.token_repo, jwt.load_key(config.home))
    app.state.search = SearchService(work_svc, collect_svc, user_svc)

    for r in (system.router, auth.router, works.router, users.router, metas.router, search.router):
        app.include_router(r)

    app.add_middleware(AuthMiddleware, auth=app.state.auth)   # 门:/api 和 /surface、HTTP 和 WebSocket 都先过它

    def _err(status: int, code: str):
        async def handler(_: Request, exc: Exception):
            return JSONResponse(fail(code, str(exc)), status_code=status)
        return handler

    for exc_type in (WorkNotFound, WorkletNotFound, ColumnNotFound, UserNotFound):
        app.add_exception_handler(exc_type, _err(404, "not_found"))
    app.add_exception_handler(WorkConflict, _err(409, "conflict"))
    app.add_exception_handler(UserExists, _err(409, "exists"))

    @app.exception_handler(AuthError)
    async def _auth(_: Request, exc: AuthError):
        return JSONResponse(fail(exc.code, str(exc)), status_code=exc.status)

    @app.exception_handler(InputRefused)
    async def _input(_: Request, exc: InputRefused):
        return JSONResponse(fail(exc.code, str(exc)), status_code=409)

    @app.exception_handler(TraceRejected)
    async def _trace(_: Request, exc: TraceRejected):
        return JSONResponse(fail("forbidden" if exc.status == 403 else "invalid", str(exc)), status_code=exc.status)

    @app.exception_handler(MetasError)
    async def _collect(_: Request, exc: MetasError):
        return JSONResponse(fail(exc.code, str(exc)), status_code=exc.status)

    @app.exception_handler(WorkServerError)
    async def _server(_: Request, exc: WorkServerError):
        status = {"bad_uri": 400, "cmd_not_found": 400, "no_server": 400, "platform": 502}.get(exc.code, 500)
        return JSONResponse(fail(exc.code, str(exc)), status_code=status)

    for path, surface in work_server_svc.surfaces():   # 窗:/surface/tmuxd(经 unix socket 到 ttyd)……;门在 AuthMiddleware,这里不再设
        app.mount(path, surface)
    mount_frontend(app)
    return app
