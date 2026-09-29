"""工作单元(现场)登记:工作单元 id ↔ URI ↔ server ↔ cwd。唯一权威,身份脱离布局(worklet.md)。"""
from __future__ import annotations

import threading

from memorytalk.backend.models.work import Worklet

from .repo import WorkRepo
from .tree import now


class WorkletNotFound(LookupError):
    pass


class WorkletRegistry:
    def __init__(self, repo: WorkRepo) -> None:
        self.repo = repo
        self._lock = threading.Lock()

    def _load(self, work_id: str) -> list[Worklet]:
        return [Worklet(**m) for m in (self.repo.get_doc(work_id, "worklets") or [])]

    def _save(self, work_id: str, worklets: list[Worklet]) -> None:
        self.repo.put_doc(work_id, "worklets", [m.model_dump() for m in worklets])

    def list(self, work_id: str) -> list[Worklet]:
        return self._load(work_id)

    def get(self, work_id: str, worklet_id: str) -> Worklet:
        for m in self._load(work_id):
            if m.id == worklet_id:
                return m
        raise WorkletNotFound(f"{work_id}/{worklet_id}")

    def _next(self, work_id: str, worklets: list[Worklet]) -> int:
        """下一个编号:单调递增,关掉的号不再用(work-events.md §4)。计数存在 seq 里;
        没有计数的旧 work,从现有的和事件里出现过的所有号之后接着发。"""
        seq = self.repo.get_doc(work_id, "seq") or {}
        if "worklet" in seq:
            return seq["worklet"]
        ids = [m.id for m in worklets] + [e.get("data", {}).get("worklet", "") for e in self.repo.read(work_id, "events")]
        return 1 + max((int(tail) for i in ids if (tail := str(i).rsplit("-w", 1)[-1]).isdigit() and "-w" in str(i)), default=0)

    def add(self, work_id: str, uri: str, scheme: str, server: str, cwd: str | None) -> Worklet:
        with self._lock:
            worklets = self._load(work_id)
            n = self._next(work_id, worklets)
            ts = now()
            m = Worklet(id=f"{work_id}-w{n}", uri=uri, scheme=scheme, server=server, cwd=cwd, created_at=ts, last_attached=ts)
            worklets.append(m)
            self._save(work_id, worklets)
            self.repo.put_doc(work_id, "seq", {**(self.repo.get_doc(work_id, "seq") or {}), "worklet": n + 1})
            return m

    def replace(self, work_id: str, worklet: Worklet) -> Worklet:
        worklets = self._load(work_id)
        for i, m in enumerate(worklets):
            if m.id == worklet.id:
                worklets[i] = worklet
                self._save(work_id, worklets)
                return worklet
        raise WorkletNotFound(f"{work_id}/{worklet.id}")

    def touch(self, work_id: str, worklet_id: str) -> Worklet:
        return self.replace(work_id, self.get(work_id, worklet_id).model_copy(update={"last_attached": now()}))

    def remove(self, work_id: str, worklet_id: str) -> None:
        worklets = self._load(work_id)
        if not any(m.id == worklet_id for m in worklets):
            raise WorkletNotFound(f"{work_id}/{worklet_id}")
        self._save(work_id, [m for m in worklets if m.id != worklet_id])
