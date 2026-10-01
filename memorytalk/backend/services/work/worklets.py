"""工作单元(现场)登记:工作单元 id ↔ URI ↔ server ↔ cwd。唯一权威,身份脱离布局(worklet.md)。
一个工作单元 = worklets 表的一行;摆在画布哪里也是这一行的列,但那几列归 CanvasStore 管。"""
from __future__ import annotations

from memorytalk.backend.models.work import Worklet

from .repo import WorkRepo
from .tree import now


class WorkletNotFound(LookupError):
    pass


def _worklet(row: dict) -> Worklet:
    return Worklet(**{k: row[k] for k in Worklet.model_fields})


class WorkletRegistry:
    def __init__(self, repo: WorkRepo) -> None:
        self.repo = repo

    def list(self, work_id: str) -> list[Worklet]:
        """按开的先后排(编号)。"""
        return [_worklet(r) for r in self.repo.list_worklets(work_id)]

    def get(self, work_id: str, worklet_id: str) -> Worklet:
        row = self.repo.get_worklet(work_id, worklet_id)
        if row is None:
            raise WorkletNotFound(f"{work_id}/{worklet_id}")
        return _worklet(row)

    def reserve(self, work_id: str) -> tuple[int, Worklet]:
        """先取号(一个短事务):现场要用工作单元 id 当名字,建现场之前就得知道。建不起来这个号也不还。
        交回(编号, 还没登记的工作单元)。"""
        n = self.repo.take_worklet_number(work_id)
        ts = now()
        return n, Worklet(id=f"{work_id}-w{n}", uri="", scheme="", server="", created_at=ts, last_attached=ts)

    def add(self, work_id: str, number: int, m: Worklet) -> Worklet:
        """登记一行(还没摆上画布;摆放由 CanvasStore.place 在同一个事务里做)。"""
        self.repo.insert_worklet({**m.model_dump(), "work_id": work_id, "number": number,
                                  "column_number": None, "position": None, "collapsed": False})
        return m

    def touch(self, work_id: str, worklet_id: str) -> Worklet:
        with self.repo.tx():
            self.get(work_id, worklet_id)
            self.repo.update_worklet(worklet_id, last_attached=now())
            return self.get(work_id, worklet_id)

    def remove(self, work_id: str, worklet_id: str) -> None:
        with self.repo.tx():
            self.get(work_id, worklet_id)
            self.repo.delete_worklet(worklet_id)
