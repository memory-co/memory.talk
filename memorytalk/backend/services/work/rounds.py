"""agent 工作单元的 round:worktrace.db 的 rounds 表,只追加;从把手拉新 round 追加进来,按 (worklet_id, round_id) 去重。"""
from __future__ import annotations

import threading

from memorytalk.backend.models.work import Round

from .repo import TraceRepo


class Rounds:
    def __init__(self, repo: TraceRepo) -> None:
        self.repo = repo
        self._lock = threading.Lock()          # 两个人同时读 rounds 也只追加一份

    def read(self, worklet_id: str) -> list[Round]:
        return [Round(id=r["round_id"], timestamp=r["timestamp"], role=r["role"], text=r["text"])
                for r in self.repo.read_rounds(worklet_id)]

    def sync(self, work_id: str, worklet_id: str, fresh: list[Round]) -> int:
        with self._lock:
            seen = {r["round_id"] for r in self.repo.read_rounds(worklet_id)}
            added = 0
            with self.repo.tx():
                for r in fresh:
                    if r.id in seen:
                        continue
                    self.repo.insert_round({"work_id": work_id, "worklet_id": worklet_id, "round_id": r.id,
                                            "timestamp": r.timestamp, "role": r.role, "text": r.text})
                    seen.add(r.id)
                    added += 1
            return added
