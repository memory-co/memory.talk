"""FastAPI 实例:装配 services、挂路由、错误映射。task / server 两层本轮未实现。"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from config import Config, load_config
from controllers import cards, issues, system
from services.card import CardExists, CardNotFound, CardService
from services.issue import IssueNotFound, IssueService, PositionNotFound
from services.store import GitError, StoreService


def create_app(config: Config | None = None) -> FastAPI:
    config = config or load_config()
    app = FastAPI(title="memory.talk v5", version="5.0.0a0",
                  description="task / issue / card 三层工作台。本轮只有 issue 与 card 两层。")

    store = StoreService(config)
    card_svc = CardService(store)
    issue_svc = IssueService(store, card_svc)
    app.state.config = config
    app.state.store = store
    app.state.cards = card_svc
    app.state.issues = issue_svc

    app.include_router(system.router)
    app.include_router(cards.router)
    app.include_router(issues.router)

    @app.exception_handler(CardNotFound)
    @app.exception_handler(IssueNotFound)
    @app.exception_handler(PositionNotFound)
    async def _not_found(_: Request, exc: Exception):
        return JSONResponse({"error": "not_found", "message": str(exc)}, status_code=404)

    @app.exception_handler(CardExists)
    async def _conflict(_: Request, exc: Exception):
        return JSONResponse({"error": "exists", "message": str(exc)}, status_code=409)

    @app.exception_handler(GitError)
    async def _git(_: Request, exc: Exception):
        return JSONResponse({"error": "git", "message": str(exc)}, status_code=500)

    return app
