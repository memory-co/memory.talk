from memorytalk.backend.models.result import Result, ok
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/health", summary="健康检查", response_model=Result[dict])
def health():
    return ok({"ok": True})


@router.get("/info", summary="运行信息:路径、存储 provider、tmux socket、有没有窗", response_model=Result[dict])
def info(request: Request):
    cfg, rt = request.app.state.config, request.app.state.runtime
    store = request.app.state.store.provider
    return ok({"home": str(cfg.home), "metas": str(cfg.metas_dir),
               "store": {"family": store.family, "backend": type(store).__name__},
               "workspace": str(rt.workspace), "tmux_socket": rt.tmux_socket, "ttyd_url": rt.ttyd_url})
