from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/health", summary="健康检查")
def health():
    return {"ok": True}


@router.get("/info", summary="运行信息:路径、存储 provider、tmux socket、有没有窗")
def info(request: Request):
    cfg, rt = request.app.state.config, request.app.state.runtime
    store = request.app.state.store.provider
    return {"home": str(cfg.home), "collections": str(cfg.collections_dir),
            "store": {"family": store.family, "backend": type(store).__name__},
            "workspace": str(rt.workspace), "tmux_socket": rt.tmux_socket, "ttyd_url": rt.ttyd_url}
