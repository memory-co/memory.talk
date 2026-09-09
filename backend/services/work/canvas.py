"""画布:work 的视图,可随时重排;version 乐观锁(照 shellbase windows)。"""
from __future__ import annotations

from models.work import Canvas, CanvasPut
from services.store import WorksLayout, atomic_write, read_text

from .tree import WorkConflict


class CanvasStore:
    def __init__(self, layout: WorksLayout) -> None:
        self.layout = layout

    def get(self, work_id: str) -> Canvas:
        text = read_text(self.layout.canvas_json(work_id))
        return Canvas() if text is None else Canvas.model_validate_json(text)

    def put(self, work_id: str, req: CanvasPut) -> Canvas:
        cur = self.get(work_id)
        if req.version != cur.version:
            raise WorkConflict(f"canvas version {req.version} != {cur.version}")
        for p in req.panels:
            if p.x < 0 or p.y < 0 or p.w < 1 or p.h < 1 or p.x + p.w > cur.cols or p.y + p.h > cur.rows:
                raise WorkConflict(f"panel {p.id} 越界")
        new = Canvas(cols=cur.cols, rows=cur.rows, version=cur.version + 1, panels=req.panels)
        atomic_write(self.layout.canvas_json(work_id), new.model_dump_json(indent=2) + "\n")
        return new
