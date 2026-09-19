"""画布:work 的视图,可随时重排;version 乐观锁。形状是列 × 会话:默认一列,会话从上到下摆,可收起。"""
from __future__ import annotations

from memorytalk.backend.models.work import Canvas, CanvasPut, Column, Panel

from .repo import WorkRepo
from .tree import WorkConflict

DEFAULT_COLUMN = "c1"


class CanvasStore:
    def __init__(self, repo: WorkRepo) -> None:
        self.repo = repo

    def get(self, work_id: str) -> Canvas:
        data = self.repo.get_doc(work_id, "canvas")
        return Canvas() if data is None else Canvas(**data)

    def put(self, work_id: str, req: CanvasPut) -> Canvas:
        cur = self.get(work_id)
        if req.version != cur.version:
            raise WorkConflict(f"canvas version {req.version} != {cur.version}")
        ids = [c.id for c in req.columns]
        if len(set(ids)) != len(ids):
            raise WorkConflict("column id 重复")
        seen: set[str] = set()
        for c in req.columns:
            for p in c.panels:
                if p.session in seen:
                    raise WorkConflict(f"会话 {p.session} 出现了两次")
                seen.add(p.session)
        return self._save(work_id, cur, req.columns)

    def _save(self, work_id: str, cur: Canvas, columns: list[Column]) -> Canvas:
        new = Canvas(version=cur.version + 1, columns=columns)
        self.repo.put_doc(work_id, "canvas", new.model_dump())
        return new

    # ---- 跟会话同步:开了进第一列末尾,关了拿掉(画布不建、不删会话,只是跟着记) ----

    def place(self, work_id: str, session_id: str) -> None:
        cur = self.get(work_id)
        if any(p.session == session_id for c in cur.columns for p in c.panels):
            return
        columns = [c.model_copy(deep=True) for c in cur.columns] or [Column(id=DEFAULT_COLUMN)]
        columns[0].panels.append(Panel(session=session_id))
        self._save(work_id, cur, columns)

    def remove(self, work_id: str, session_id: str) -> None:
        cur = self.get(work_id)
        if not any(p.session == session_id for c in cur.columns for p in c.panels):
            return
        columns = [Column(id=c.id, panels=[p for p in c.panels if p.session != session_id]) for c in cur.columns]
        self._save(work_id, cur, columns)
