"""工作单元(现场)登记:工作单元 id ↔ URI ↔ server ↔ cwd。唯一权威,身份脱离布局(worklet.md)。"""
from __future__ import annotations

from memorytalk.backend.models.work import Worklet

from .repo import WorkRepo
from .tree import now


class WorkletNotFound(LookupError):
    pass


class WorkletRegistry:
    def __init__(self, repo: WorkRepo) -> None:
        self.repo = repo

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

    def add(self, work_id: str, uri: str, scheme: str, server: str, cwd: str | None) -> Worklet:
        worklets = self._load(work_id)
        n = 1 + max((int(m.id.rsplit("-w", 1)[1]) for m in worklets if m.id.rsplit("-w", 1)[-1].isdigit()), default=0)
        ts = now()
        m = Worklet(id=f"{work_id}-w{n}", uri=uri, scheme=scheme, server=server, cwd=cwd, created_at=ts, last_attached=ts)
        worklets.append(m)
        self._save(work_id, worklets)
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
