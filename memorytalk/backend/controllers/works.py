"""/api/works —— 树、列、工作单元(attach = 经 server 建现场)、痕迹(round,旧路径)、轨迹(trace:读写一个接口)、谁在看。"""
from __future__ import annotations

from memorytalk.backend.models.result import Result, ok
from fastapi import APIRouter, Depends, Query, Request
from starlette.concurrency import run_in_threadpool

from memorytalk.backend.models.metas import InboxItem
from memorytalk.backend.models.work_server import WorkServerInfo
from memorytalk.backend.models.work import (Column, ColumnCreate, ColumnUpdate, InputResult, Round, TracePush, WorkletCreate,
                         WorkletInput, WorkletMove, WorkletUpdate, WorkletView, Work, WorkCreate, WorkNode, WorkTrace, WorkUpdate,
                         WorkUsers)
from memorytalk.backend.services.metas import MetasService
from memorytalk.backend.services.work import TraceRejected, WorkService

WAIT_MAX = 60.0                # 长轮询最多挂这么久(秒)

router = APIRouter(prefix="/api/works", tags=["works"])


def works(request: Request) -> WorkService:
    return request.app.state.works


def metas(request: Request) -> MetasService:
    return request.app.state.metas


def user(request: Request) -> str | None:
    """谁在操作:门(中间件)解析 token 放进 request.state 的名字(身份,不是权限)。"""
    return request.state.user


@router.get("", response_model=Result[list[WorkNode]], summary="work 树(森林;root= 只看一棵;created_by= 只看某人建的)")
def forest(root: str | None = None, created_by: str | None = None, svc: WorkService = Depends(works)):
    return ok(svc.forest(root, created_by))


@router.get("/servers", response_model=Result[list[WorkServerInfo]],
            summary="有哪些 work server(bash / claude / codex / kimi / http / default)及各自响应的协议;attach 时按协议去找它们")
def servers(request: Request):
    return ok(request.app.state.work_servers.list())


@router.post("", response_model=Result[Work], status_code=201, summary="开工:建一个 work(parent= 挂到树上)")
def create(req: WorkCreate, svc: WorkService = Depends(works), who: str | None = Depends(user)):
    return ok(svc.create(req, created_by=who))


@router.get("/{work_id}", response_model=Result[Work], summary="读一个 work(带身份 = 打开它,算一次心跳:在看)")
def get(work_id: str, svc: WorkService = Depends(works), who: str | None = Depends(user)):
    svc.touch(work_id, who)
    return ok(svc.get(work_id))


@router.patch("/{work_id}", response_model=Result[Work],
              summary="改目标 / 状态(running / archived);归档后工作单元冻结,重新打开 = 轨迹上新的一段")
def update(work_id: str, req: WorkUpdate, svc: WorkService = Depends(works), who: str | None = Depends(user)):
    svc.touch(work_id, who)
    return ok(svc.update(work_id, req, by=who))


@router.get("/{work_id}/trace", response_model=Result[WorkTrace], response_model_exclude_none=True,
            summary="轨迹:OTLP/JSON 的段(开着的没有终点、带 memorytalk.open)+ 点 + seq(变更序号)。"
                    "agent 的 output 就是它:worklet + agent=1 + bodies=1 是一个工作单元的对话,after + wait 等变化")
async def trace(work_id: str, request: Request, subtree: bool = False,
                worklet: str | None = Query(None, description="只看一个工作单元"),
                agent: bool = Query(False, description="带上 agent 那几层(会话 / 轮次 / 工具段,消息 / 状态点)"),
                bodies: bool = Query(False, description="带正文(点的 body)"),
                after: int | None = Query(None, ge=0, description="只要这个变更序号之后写的或改过的"),
                wait: float = Query(0, ge=0, description="配合 after:没变化就等着,最多这么多秒(长轮询)"),
                fields: str | None = Query(None, pattern="^(cursors|spans)$",
                                           description="cursors = 只要节点推到哪了(要带 worklet);spans = 只要段、不要点(甘特图 / 火焰图用)"),
                svc: WorkService = Depends(works)):
    if fields == "cursors":
        return ok(await run_in_threadpool(svc.cursors, work_id, worklet))
    if after is not None and wait > 0:
        await svc.wait_trace(work_id, after, min(wait, WAIT_MAX), subtree=subtree, worklet=worklet, agent=agent)
    return ok(await run_in_threadpool(lambda: svc.trace_of(work_id, subtree, worklet=worklet, agent=agent, bodies=bodies, after=after,
                                                           points=fields != "spans")))


@router.post("/{work_id}/trace", response_model=Result[dict],
             summary="写轨迹:节点推上来的一批(和读同一个形状,外加 cursors);只有节点能写,登录的人只能读")
def push_trace(work_id: str, req: TracePush, request: Request, svc: WorkService = Depends(works)):
    if not getattr(request.state, "node", False):
        raise TraceRejected(403, "trace 只由节点写(经中心的 unix socket);登录的人只能读")
    return ok(svc.write_trace(work_id, req.model_dump(include={"traces", "logs"}), [c.model_dump() for c in req.cursors]))


@router.get("/{work_id}/inbox", response_model=Result[list[InboxItem]],
            summary="收件箱:被 manager.json 路由过来的变动(Metas 的对象、子 work 的状态)")
def inbox(work_id: str, svc: WorkService = Depends(works)):
    return ok(svc.read_inbox(work_id))


@router.get("/{work_id}/manager", summary="这个 work 的变动打给谁:设了 manager 就是它,没有则父 work", response_model=Result[dict])
def get_manager(work_id: str, svc: WorkService = Depends(works)) -> dict:
    return ok({"work": svc.manager_of(work_id)})


@router.put("/{work_id}/manager", summary="改写默认:这棵子树的变动打给指定 work(null = 删掉,回到父)", response_model=Result[dict])
def put_manager(work_id: str, req: dict, svc: WorkService = Depends(works)) -> dict:
    return ok({"work": svc.set_manager(work_id, req.get("work"))})


@router.get("/{work_id}/users", response_model=Result[WorkUsers],
            summary="现在谁在看这个 work(current,按名字排)。只做可见性,不做权限;谁做过什么看 /trace")
def users(work_id: str, svc: WorkService = Depends(works)):
    return ok(svc.list_users(work_id))


@router.post("/{work_id}/users/touch", response_model=Result[WorkUsers], summary="我在看这个 work(心跳;身份来自登录态)")
def touch(work_id: str, svc: WorkService = Depends(works), who: str | None = Depends(user)):
    svc.touch(work_id, who)
    return ok(svc.list_users(work_id))


@router.post("/{work_id}/users/leave", response_model=Result[WorkUsers], summary="我不看了(关页面 / 切走时发;不用等心跳超时)")
def leave(work_id: str, svc: WorkService = Depends(works), who: str | None = Depends(user)):
    return ok(svc.leave(work_id, who))


@router.get("/{work_id}/columns", response_model=Result[list[Column]], summary="列清单(从左到右;工作单元在哪一列看 /worklets)")
def columns(work_id: str, svc: WorkService = Depends(works)):
    return ok(svc.list_columns(work_id))


@router.post("/{work_id}/columns", response_model=Result[list[Column]], status_code=201,
             summary="加一列(服务端发编号 c<n>,永不复用;beside + side 定位置,不给 = 最右);交回列清单")
def add_column(work_id: str, req: ColumnCreate, svc: WorkService = Depends(works), who: str | None = Depends(user)):
    svc.touch(work_id, who)
    return ok(svc.add_column(work_id, req, by=who))


@router.patch("/{work_id}/columns/{column_id}", response_model=Result[list[Column]], summary="改别名(编号不动)/ 收起展开;交回列清单")
def update_column(work_id: str, column_id: str, req: ColumnUpdate, svc: WorkService = Depends(works), who: str | None = Depends(user)):
    svc.touch(work_id, who)
    return ok(svc.update_column(work_id, column_id, req, by=who))


@router.delete("/{work_id}/columns/{column_id}", response_model=Result[list[Column]], summary="删一列:只有空列能删,最后一列不能删;交回列清单")
def remove_column(work_id: str, column_id: str, svc: WorkService = Depends(works), who: str | None = Depends(user)):
    svc.touch(work_id, who)
    return ok(svc.remove_column(work_id, column_id, by=who))


@router.get("/{work_id}/worklets", response_model=Result[list[WorkletView]], summary="工作单元清单(含活没活着、在哪一列第几个、收没收起)")
def worklets(work_id: str, svc: WorkService = Depends(works)):
    return ok(svc.list_worklets(work_id))


@router.post("/{work_id}/worklets", response_model=Result[WorkletView], status_code=201,
             summary="在 work 里打开一个块:协议 → server 建现场,登记工作单元并放进 column 那列末尾(不给 = 最左一列),交回窗 + 把手")
def attach(work_id: str, req: WorkletCreate, svc: WorkService = Depends(works), who: str | None = Depends(user)):
    svc.touch(work_id, who)
    return ok(svc.attach(work_id, req.uri, req.column, by=who))


@router.post("/{work_id}/worklets/{worklet_id}/attach", response_model=Result[WorkletView],
             summary="重入:幂等取回同一个现场")
def reattach(work_id: str, worklet_id: str, svc: WorkService = Depends(works), who: str | None = Depends(user)):
    svc.touch(work_id, who)
    return ok(svc.reattach(work_id, worklet_id, by=who))


@router.delete("/{work_id}/worklets/{worklet_id}", summary="关闭即回收:销毁现场 + 删登记")
def detach(work_id: str, worklet_id: str, svc: WorkService = Depends(works), who: str | None = Depends(user)):
    svc.touch(work_id, who)
    svc.detach(work_id, worklet_id, by=who)
    return ok()


@router.post("/{work_id}/worklets/{worklet_id}/move", response_model=Result[list[WorkletView]],
             summary="挪工作单元:到哪一列、列里第几个(不给 = 末尾);交回工作单元清单")
def move_worklet(work_id: str, worklet_id: str, req: WorkletMove, svc: WorkService = Depends(works), who: str | None = Depends(user)):
    svc.touch(work_id, who)
    return ok(svc.move_worklet(work_id, worklet_id, req, by=who))


@router.patch("/{work_id}/worklets/{worklet_id}", response_model=Result[list[WorkletView]], summary="收起 / 展开工作单元(不进轨迹);交回工作单元清单")
def update_worklet(work_id: str, worklet_id: str, req: WorkletUpdate, svc: WorkService = Depends(works), who: str | None = Depends(user)):
    svc.touch(work_id, who)
    return ok(svc.update_worklet(work_id, worklet_id, req))


@router.post("/{work_id}/worklets/{worklet_id}/input", response_model=Result[InputResult],
             summary="往现场里送:打字(text,submit 再按回车)/ 按键(keys)。agent 正在干活或在等确认时默认不送"
                     "(409 busy / blocked),要送带 force;现场不在 409 gone,不收这种 409 unsupported。trace 里记一个 worklet.input 点,不存原文")
def send_input(work_id: str, worklet_id: str, req: WorkletInput, svc: WorkService = Depends(works), who: str | None = Depends(user)):
    svc.touch(work_id, who)
    return ok(svc.send_input(work_id, worklet_id, req, by=who))


@router.get("/{work_id}/worklets/{worklet_id}/rounds", response_model=Result[list[Round]],
            summary="痕迹(旧路径,只剩 Codex / Kimi):先从把手同步新 round,再按顺序读 worktrace.db 的 rounds;"
                    "claude 的对话在 trace 里,这里是空的")
def rounds(work_id: str, worklet_id: str, svc: WorkService = Depends(works)):
    return ok(svc.rounds(work_id, worklet_id))
