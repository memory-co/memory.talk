"""画布:task 的视图,可随时重排;version 乐观锁(照 shellbase windows)。"""
from __future__ import annotations

from models.task import Canvas, CanvasPut
from services.store import TasksLayout, atomic_write, read_text

from .tree import TaskConflict


class CanvasStore:
    def __init__(self, layout: TasksLayout) -> None:
        self.layout = layout

    def get(self, task_id: str) -> Canvas:
        text = read_text(self.layout.canvas_json(task_id))
        return Canvas() if text is None else Canvas.model_validate_json(text)

    def put(self, task_id: str, req: CanvasPut) -> Canvas:
        cur = self.get(task_id)
        if req.version != cur.version:
            raise TaskConflict(f"canvas version {req.version} != {cur.version}")
        for p in req.panels:
            if p.x < 0 or p.y < 0 or p.w < 1 or p.h < 1 or p.x + p.w > cur.cols or p.y + p.h > cur.rows:
                raise TaskConflict(f"panel {p.id} 越界")
        new = Canvas(cols=cur.cols, rows=cur.rows, version=cur.version + 1, panels=req.panels)
        atomic_write(self.layout.canvas_json(task_id), new.model_dump_json(indent=2) + "\n")
        return new
