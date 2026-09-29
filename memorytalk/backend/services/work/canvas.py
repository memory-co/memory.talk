"""画布:work 的视图。形状是列 × 工作单元;一列 = 固定编号 + 别名。
不整份覆盖——每个动作一个方法,在当前画布上做、存回、version +1(docs/designs/v5/work-events.md)。
事件不在这写:方法把「动了哪一列」交回去,由 WorkService 记。"""
from __future__ import annotations

import re
import threading

from memorytalk.backend.models.work import Canvas, Column, Panel

from .repo import WorkRepo
from .tree import WorkConflict

_NUMBERED = re.compile(r"c(\d+)")


class ColumnNotFound(LookupError):
    pass


class PanelNotFound(LookupError):
    pass


def _number(column_id: str) -> int | None:
    m = _NUMBERED.fullmatch(column_id)
    return int(m.group(1)) if m else None


class CanvasStore:
    def __init__(self, repo: WorkRepo) -> None:
        self.repo = repo
        self._lock = threading.Lock()          # 读-改-写串行;动作都很小,一把锁够了

    # ---- 读:顺手把旧数据规整成「至少一列、编号都是 c<n>、next_column 在最大号之后」 ----

    def get(self, work_id: str) -> Canvas:
        data = self.repo.get_doc(work_id, "canvas")
        cv = Canvas() if data is None else Canvas(**data)
        columns = [c.model_copy(deep=True) for c in cv.columns]
        top = max((n for c in columns if (n := _number(c.id)) is not None), default=0)
        for c in columns:                       # 早期的非 c<n> id(left / right)按从左到右接着发号
            if _number(c.id) is None:
                top += 1
                c.id = f"c{top}"
        if not columns:
            top += 1
            columns = [Column(id=f"c{top}")]
        return cv.model_copy(update={"columns": columns, "next_column": max(cv.next_column, top + 1)})

    def _save(self, work_id: str, cur: Canvas) -> Canvas:
        new = cur.model_copy(update={"version": cur.version + 1})
        self.repo.put_doc(work_id, "canvas", new.model_dump())
        return new

    @staticmethod
    def _column(cv: Canvas, column_id: str) -> Column:
        for c in cv.columns:
            if c.id == column_id:
                return c
        raise ColumnNotFound(column_id)

    @staticmethod
    def _find(cv: Canvas, worklet_id: str) -> tuple[Column, int] | None:
        for c in cv.columns:
            for i, p in enumerate(c.panels):
                if p.worklet == worklet_id:
                    return c, i
        return None

    # ---- 列 ----

    def add_column(self, work_id: str, alias: str, beside: str | None, side: str) -> tuple[Canvas, Column]:
        with self._lock:
            cv = self.get(work_id)
            col = Column(id=f"c{cv.next_column}", alias=alias)
            at = len(cv.columns)
            if beside is not None:
                i = cv.columns.index(self._column(cv, beside))
                at = i + (1 if side == "right" else 0)
            cv.columns.insert(at, col)
            cv.next_column += 1
            return self._save(work_id, cv), col

    def update_column(self, work_id: str, column_id: str, alias: str | None, collapsed: bool | None) -> tuple[Canvas, Column, Column]:
        """交回(画布, 改前, 改后)。"""
        with self._lock:
            cv = self.get(work_id)
            col = self._column(cv, column_id)
            before = col.model_copy(deep=True)
            if alias is not None:
                col.alias = alias
            if collapsed is not None:
                col.collapsed = collapsed
            return self._save(work_id, cv), before, col

    def remove_column(self, work_id: str, column_id: str) -> tuple[Canvas, Column]:
        with self._lock:
            cv = self.get(work_id)
            col = self._column(cv, column_id)
            if col.panels:
                raise WorkConflict(f"列 {column_id} 里还有工作单元,只有空列能删")
            if len(cv.columns) == 1:
                raise WorkConflict("最后一列不能删")
            cv.columns.remove(col)
            return self._save(work_id, cv), col

    # ---- 格子(工作单元在画布上的位置) ----

    def place(self, work_id: str, worklet_id: str, column_id: str | None) -> tuple[Canvas, Column]:
        """放进某一列末尾(不给 = 最左一列);已经在画布上就不动。"""
        with self._lock:
            cv = self.get(work_id)
            if found := self._find(cv, worklet_id):
                return cv, found[0]
            col = self._column(cv, column_id) if column_id else cv.columns[0]
            col.panels.append(Panel(worklet=worklet_id))
            return self._save(work_id, cv), col

    def check_column(self, work_id: str, column_id: str) -> None:
        """attach 之前先验列在不在——现场建起来了才发现列不存在就晚了。"""
        self._column(self.get(work_id), column_id)

    def move(self, work_id: str, worklet_id: str, column_id: str, index: int | None) -> tuple[Canvas, tuple[Column, int], tuple[Column, int]]:
        """交回(画布, (原列, 原位置), (新列, 新位置))。"""
        with self._lock:
            cv = self.get(work_id)
            found = self._find(cv, worklet_id)
            if not found:
                raise PanelNotFound(worklet_id)
            src, i = found
            dst = self._column(cv, column_id)
            src_snap = src.model_copy(deep=True)
            panel = src.panels.pop(i)
            j = len(dst.panels) if index is None else min(index, len(dst.panels))
            dst.panels.insert(j, panel)
            return self._save(work_id, cv), (src_snap, i), (dst, j)

    def set_collapsed(self, work_id: str, worklet_id: str, collapsed: bool) -> Canvas:
        with self._lock:
            cv = self.get(work_id)
            found = self._find(cv, worklet_id)
            if not found:
                raise PanelNotFound(worklet_id)
            found[0].panels[found[1]].collapsed = collapsed
            return self._save(work_id, cv)

    def remove(self, work_id: str, worklet_id: str) -> Column | None:
        """工作单元关了,从格子里拿掉;交回它原来在哪一列(不在画布上 = None)。"""
        with self._lock:
            cv = self.get(work_id)
            found = self._find(cv, worklet_id)
            if not found:
                return None
            col, i = found
            snap = col.model_copy(deep=True)
            col.panels.pop(i)
            self._save(work_id, cv)
            return snap
