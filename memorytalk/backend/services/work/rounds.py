"""agent 工作单元的 round:append-only;从把手拉新 round 追加进来。"""
from __future__ import annotations

from memorytalk.backend.models.work import Round

from .repo import WorkRepo


class Rounds:
    def __init__(self, repo: WorkRepo) -> None:
        self.repo = repo

    def read(self, work_id: str, worklet_id: str) -> list[Round]:
        return [Round(**l) for l in self.repo.read(work_id, "rounds", sub=worklet_id)]

    def sync(self, work_id: str, worklet_id: str, fresh: list[Round]) -> int:
        seen = {r.id for r in self.read(work_id, worklet_id)}
        added = 0
        for r in fresh:
            if r.id in seen:
                continue
            self.repo.append(work_id, "rounds", r.model_dump(), sub=worklet_id)
            seen.add(r.id)
            added += 1
        return added
