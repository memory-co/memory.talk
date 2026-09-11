"""画布:work 的视图,可随时重排;version 乐观锁(照 shellbase windows)。"""
from __future__ import annotations

from memorytalk.models.work import Canvas, CanvasPut

from .repo import WorkRepo
from .tree import WorkConflict


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
        for p in req.panels:
            if p.x < 0 or p.y < 0 or p.w < 1 or p.h < 1 or p.x + p.w > cur.cols or p.y + p.h > cur.rows:
                raise WorkConflict(f"panel {p.id} 越界")
        new = Canvas(cols=cur.cols, rows=cur.rows, version=cur.version + 1, panels=req.panels)
        self.repo.put_doc(work_id, "canvas", new.model_dump())
        return new
