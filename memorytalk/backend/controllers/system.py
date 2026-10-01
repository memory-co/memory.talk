from memorytalk.backend.models.result import Result, ok
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/health", summary="健康检查", response_model=Result[dict])
def health():
    return ok({"ok": True})


@router.get("/info", summary="运行信息:路径、存储(work 的两个库 + users / auth 的 provider)、tmux socket、有没有窗", response_model=Result[dict])
def info(request: Request):
    cfg, rt = request.app.state.config, request.app.state.runtime
    store = request.app.state.store.provider          # users / auth 的;work 固定是下面两个 sqlite
    tmuxd = request.app.state.work_servers.tmuxd
    return ok({"home": str(cfg.home), "metas": str(cfg.metas_dir),
               "store": {"family": store.family, "backend": type(store).__name__},
               "works_db": str(cfg.works_db), "worktrace_db": str(cfg.worktrace_db),
               "workspace": str(rt.workspace), "tmux_socket": tmuxd.tmux_socket,
               "tmuxd": {"listen": tmuxd.listen, "socket": tmuxd.socket_path, "mount": tmuxd.base_path}})
