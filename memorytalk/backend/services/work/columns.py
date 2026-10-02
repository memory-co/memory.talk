"""列:弱编排。一个 work 有几列(有序、可起别名、可收起),每个工作单元摆在某一列的某个位置——就这些,没有别的布局。
一列 = 固定编号 + 别名;列是 work_columns 的行,工作单元摆在哪是 worklets 自己的 column_number / position / collapsed,
下一列的编号在 works 上(work-store.md §4)。每个动作一个方法、一个事务:挪几行,position 始终连续。
轨迹不在这写:方法把「动了哪一列」交回去,由 WorkService 记。"""
from __future__ import annotations

import re

from memorytalk.backend.models.work import Column

from .repo import WorkRepo
from .tree import WorkConflict
from .worklets import WorkletNotFound

_NUMBERED = re.compile(r"c(\d+)")
_MAX_NUMBER = 2**63 - 1                                       # sqlite INTEGER 装得下的最大数;再大的编号不可能发过


class ColumnNotFound(LookupError):
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
    return Column(id=f"c{row['number']}", alias=row["alias"], collapsed=row["collapsed"], position=row["position"])


class Columns:
    def __init__(self, repo: WorkRepo) -> None:
        self.repo = repo

    def list(self, work_id: str) -> list[Column]:
        """从左到右(按 position)。"""
        return [_column(r) for r in self.repo.list_columns(work_id)]

    def _row(self, work_id: str, column_id: str) -> dict:
        row = self.repo.get_column(work_id, number_of(column_id))
        if row is None:
            raise ColumnNotFound(column_id)
        return row

    def _placed(self, work_id: str, worklet_id: str) -> dict:
        m = self.repo.get_worklet(work_id, worklet_id)
        if m is None or m["column_number"] is None:
            raise WorkletNotFound(f"{work_id}/{worklet_id} 不在任何一列里")
        return m

    # ---- 列:动作交回(动完的列清单, 动了哪一列……),清单和动作在一个事务里读 ----

    def add(self, work_id: str, alias: str, beside: str | None, side: str) -> tuple[list[Column], Column]:
        """加在 beside 的左边(占它的位置)或右边(+1);不给 = 最右。"""
        with self.repo.tx():
            at = len(self.repo.list_columns(work_id))
            if beside is not None:
                at = self._row(work_id, beside)["position"] + (1 if side == "right" else 0)
            n = self.repo.take_column_number(work_id)
            self.repo.shift_columns(work_id, at, +1)
            self.repo.insert_column(work_id, n, alias, at)
            return self.list(work_id), Column(id=f"c{n}", alias=alias, position=at)

    def update(self, work_id: str, column_id: str, alias: str | None, collapsed: bool | None) -> tuple[list[Column], Column, Column]:
        """交回(列清单, 改前, 改后)。"""
        with self.repo.tx():
            row = self._row(work_id, column_id)
            changes = {k: v for k, v in (("alias", alias), ("collapsed", collapsed)) if v is not None}
            if changes:
                self.repo.update_column(work_id, row["number"], **changes)
            return self.list(work_id), _column(row), _column({**row, **changes})

    def remove(self, work_id: str, column_id: str) -> tuple[list[Column], Column]:
        with self.repo.tx():
            row = self._row(work_id, column_id)
            if self.repo.column_worklets(work_id, row["number"]):
                raise WorkConflict(f"列 {column_id} 里还有工作单元,只有空列能删")
            if len(self.repo.list_columns(work_id)) == 1:
                raise WorkConflict("最后一列不能删")
            self.repo.delete_column(work_id, row["number"])
            self.repo.shift_columns(work_id, row["position"] + 1, -1)
            return self.list(work_id), _column(row)

    def check(self, work_id: str, column_id: str) -> None:
        """attach 之前先验列在不在——现场建起来了才发现列不存在就晚了。"""
        self._row(work_id, column_id)

    # ---- 工作单元摆在哪:哪一列、列里第几个、收没收起(都是 worklets 那一行自己的列) ----

    def place(self, work_id: str, worklet_id: str, column_id: str | None) -> tuple[Column, int]:
        """放进某一列末尾(不给 = 最左一列,即 position 0 那列);已经在某一列里就不动。交回(在哪一列, 列里第几个)。"""
        with self.repo.tx():
            m = self.repo.get_worklet(work_id, worklet_id)
            if m["column_number"] is not None:
                return _column(self.repo.get_column(work_id, m["column_number"])), m["position"]
            row = self._row(work_id, column_id) if column_id else self.repo.list_columns(work_id)[0]
            pos = len(self.repo.column_worklets(work_id, row["number"]))
            self.repo.update_worklet(worklet_id, column_number=row["number"], position=pos)
            return _column(row), pos

    def move(self, work_id: str, worklet_id: str, column_id: str, index: int | None) -> tuple[tuple[Column, int], tuple[Column, int]]:
        """交回((原列, 原位置), (新列, 新位置))。index 按「先从原列拿掉」之后数,超出就放末尾;不给 = 末尾。"""
        with self.repo.tx():
            m = self._placed(work_id, worklet_id)
            dst = self._row(work_id, column_id)
            src, i = self.repo.get_column(work_id, m["column_number"]), m["position"]
            self.repo.shift_worklets(work_id, src["number"], i + 1, -1, skip=worklet_id)
            others = [w for w in self.repo.column_worklets(work_id, dst["number"]) if w["id"] != worklet_id]
            j = len(others) if index is None else min(index, len(others))
            self.repo.shift_worklets(work_id, dst["number"], j, +1, skip=worklet_id)
            self.repo.update_worklet(worklet_id, column_number=dst["number"], position=j)
            return (_column(src), i), (_column(dst), j)

    def set_collapsed(self, work_id: str, worklet_id: str, collapsed: bool) -> None:
        with self.repo.tx():
            self._placed(work_id, worklet_id)
            self.repo.update_worklet(worklet_id, collapsed=collapsed)

    def unplace(self, work_id: str, worklet_id: str) -> Column | None:
        """工作单元关了,从列里拿掉(行由登记那边删),后面的往上补;交回它原来在哪一列(不在任何一列 = None)。"""
        with self.repo.tx():
            m = self.repo.get_worklet(work_id, worklet_id)
            if m is None or m["column_number"] is None:
                return None
            col = self.repo.get_column(work_id, m["column_number"])
            self.repo.update_worklet(worklet_id, column_number=None, position=None)
            self.repo.shift_worklets(work_id, m["column_number"], m["position"] + 1, -1)
            return _column(col)

    def column_of(self, work_id: str, worklet_id: str) -> Column | None:
        """它现在在哪一列(不在任何一列 = None)。两次读在一个事务里:中间夹进别人的「挪走 + 删掉空列」,就读到一列已经没了的。"""
        with self.repo.tx():
            m = self.repo.get_worklet(work_id, worklet_id)
            if m is None or m["column_number"] is None:
                return None
            return _column(self.repo.get_column(work_id, m["column_number"]))
