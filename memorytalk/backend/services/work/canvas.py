"""画布:work 的视图。形状是列 × 工作单元;一列 = 固定编号 + 别名。
库里没有画布这张表:列是 work_columns 的行,工作单元摆在哪是 worklets 自己的 column_number / position / collapsed,
version 和下一列编号在 works 上(work-store.md §4)。每个动作一个方法、一个事务:挪几行、version +1,position 始终连续。
轨迹不在这写:方法把「动了哪一列」交回去,由 WorkService 记。"""
from __future__ import annotations

import re

from memorytalk.backend.models.work import Canvas, Column, Panel

from .repo import WorkRepo
from .tree import WorkConflict

_NUMBERED = re.compile(r"c(\d+)")
_MAX_NUMBER = 2**63 - 1                                       # sqlite INTEGER 装得下的最大数;再大的编号不可能发过


class ColumnNotFound(LookupError):
    pass


class PanelNotFound(LookupError):
    pass


def number_of(column_id: str) -> int:
    """c<编号> → 编号;别的写法一律当这列不存在。"""
    m = _NUMBERED.fullmatch(column_id)
    if not m or len(m.group(1)) > len(str(_MAX_NUMBER)):      # 先看位数:太长的 int() 自己就会报错
        raise ColumnNotFound(column_id)
    n = int(m.group(1))
    if f"c{n}" != column_id or n > _MAX_NUMBER:               # c01 也不算:id 是拼出来的,只有一种写法
        raise ColumnNotFound(column_id)
    return n


def _column(row: dict) -> Column:
    return Column(id=f"c{row['number']}", alias=row["alias"], collapsed=row["collapsed"])


class CanvasStore:
    def __init__(self, repo: WorkRepo) -> None:
        self.repo = repo

    # ---- 读:两次查询拼出来(列按 position,工作单元按 column_number, position)----

    def get(self, work_id: str) -> Canvas:
        with self.repo.tx():
            work = self.repo.get_work(work_id)
            cols = {r["number"]: _column(r) for r in self.repo.list_columns(work_id)}
            for m in self.repo.placed_worklets(work_id):
                if m["column_number"] in cols:
                    cols[m["column_number"]].panels.append(Panel(worklet=m["id"], collapsed=m["collapsed"]))
        return Canvas(version=work["canvas_version"], next_column=work["next_column"], columns=list(cols.values()))

    def _row(self, work_id: str, column_id: str) -> dict:
        row = self.repo.get_column(work_id, number_of(column_id))
        if row is None:
            raise ColumnNotFound(column_id)
        return row

    def _placed(self, work_id: str, worklet_id: str) -> dict:
        m = self.repo.get_worklet(work_id, worklet_id)
        if m is None or m["column_number"] is None:
            raise PanelNotFound(worklet_id)
        return m

    # ---- 列 ----

    def add_column(self, work_id: str, alias: str, beside: str | None, side: str) -> tuple[Canvas, Column]:
        """加在 beside 的左边(占它的位置)或右边(+1);不给 = 最右。"""
        with self.repo.tx():
            at = len(self.repo.list_columns(work_id))
            if beside is not None:
                at = self._row(work_id, beside)["position"] + (1 if side == "right" else 0)
            n = self.repo.take_column_number(work_id)
            self.repo.shift_columns(work_id, at, +1)
            self.repo.insert_column(work_id, n, alias, at)
            self.repo.bump_canvas(work_id)
            return self.get(work_id), Column(id=f"c{n}", alias=alias)

    def update_column(self, work_id: str, column_id: str, alias: str | None, collapsed: bool | None) -> tuple[Canvas, Column, Column]:
        """交回(画布, 改前, 改后)。什么都没改也算一个动作(version +1)。"""
        with self.repo.tx():
            row = self._row(work_id, column_id)
            changes = {k: v for k, v in (("alias", alias), ("collapsed", collapsed)) if v is not None}
            if changes:
                self.repo.update_column(work_id, row["number"], **changes)
            self.repo.bump_canvas(work_id)
            return self.get(work_id), _column(row), _column({**row, **changes})

    def remove_column(self, work_id: str, column_id: str) -> tuple[Canvas, Column]:
        with self.repo.tx():
            row = self._row(work_id, column_id)
            if self.repo.column_worklets(work_id, row["number"]):
                raise WorkConflict(f"列 {column_id} 里还有工作单元,只有空列能删")
            if len(self.repo.list_columns(work_id)) == 1:
                raise WorkConflict("最后一列不能删")
            self.repo.delete_column(work_id, row["number"])
            self.repo.shift_columns(work_id, row["position"] + 1, -1)
            self.repo.bump_canvas(work_id)
            return self.get(work_id), _column(row)

    def check_column(self, work_id: str, column_id: str) -> None:
        """attach 之前先验列在不在——现场建起来了才发现列不存在就晚了。"""
        self._row(work_id, column_id)

    # ---- 格子(工作单元在画布上的位置) ----

    def place(self, work_id: str, worklet_id: str, column_id: str | None) -> Column:
        """放进某一列末尾(不给 = 最左一列,即 position 0 那列);已经在画布上就不动。交回它在哪一列。"""
        with self.repo.tx():
            m = self.repo.get_worklet(work_id, worklet_id)
            if m["column_number"] is not None:
                return _column(self.repo.get_column(work_id, m["column_number"]))
            row = self._row(work_id, column_id) if column_id else self.repo.list_columns(work_id)[0]
            pos = len(self.repo.column_worklets(work_id, row["number"]))
            self.repo.update_worklet(worklet_id, column_number=row["number"], position=pos)
            self.repo.bump_canvas(work_id)
            return _column(row)

    def move(self, work_id: str, worklet_id: str, column_id: str, index: int | None) -> tuple[Canvas, tuple[Column, int], tuple[Column, int]]:
        """交回(画布, (原列, 原位置), (新列, 新位置))。index 按「先从原列拿掉」之后数,超出就放末尾;不给 = 末尾。"""
        with self.repo.tx():
            m = self._placed(work_id, worklet_id)
            dst = self._row(work_id, column_id)
            src, i = self.repo.get_column(work_id, m["column_number"]), m["position"]
            self.repo.shift_worklets(work_id, src["number"], i + 1, -1, skip=worklet_id)
            others = [w for w in self.repo.column_worklets(work_id, dst["number"]) if w["id"] != worklet_id]
            j = len(others) if index is None else min(index, len(others))
            self.repo.shift_worklets(work_id, dst["number"], j, +1, skip=worklet_id)
            self.repo.update_worklet(worklet_id, column_number=dst["number"], position=j)
            self.repo.bump_canvas(work_id)
            return self.get(work_id), (_column(src), i), (_column(dst), j)

    def set_collapsed(self, work_id: str, worklet_id: str, collapsed: bool) -> Canvas:
        with self.repo.tx():
            self._placed(work_id, worklet_id)
            self.repo.update_worklet(worklet_id, collapsed=collapsed)
            self.repo.bump_canvas(work_id)
            return self.get(work_id)

    def remove(self, work_id: str, worklet_id: str) -> Column | None:
        """工作单元关了,从格子里拿掉(行由登记那边删);交回它原来在哪一列(不在画布上 = None,version 不动)。"""
        with self.repo.tx():
            m = self.repo.get_worklet(work_id, worklet_id)
            if m is None or m["column_number"] is None:
                return None
            col = self.repo.get_column(work_id, m["column_number"])
            self.repo.update_worklet(worklet_id, column_number=None, position=None)
            self.repo.shift_worklets(work_id, m["column_number"], m["position"] + 1, -1)
            self.repo.bump_canvas(work_id)
            return _column(col)

    def column_of(self, work_id: str, worklet_id: str) -> Column | None:
        """它现在在哪一列(不在画布上 = None)。两次读在一个事务里:中间夹进别人的「挪走 + 删掉空列」,就读到一列已经没了的。"""
        with self.repo.tx():
            m = self.repo.get_worklet(work_id, worklet_id)
            if m is None or m["column_number"] is None:
                return None
            return _column(self.repo.get_column(work_id, m["column_number"]))
