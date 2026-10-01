"""现在谁在看这个 work(docs/designs/v5/work-store.md §3、user.md §3)。只做可见性,不做权限。

心跳只在进程内存里(work → 人 → 最后一次心跳的时刻),不进库;works.viewers 是它的投影:
每次变了就按内存整份算出来再写(按名字排),从不读出来追加。超过 ACTIVE_WINDOW 没心跳的人由 sweep 清出去;
「离开」立刻拿掉;服务起来时所有 work 的 viewers 清空——重启那一刻谁也没在看。
"""
from __future__ import annotations

import threading
import time
from typing import Callable

from .repo import WorkRepo

ACTIVE_WINDOW = 120   # 秒:这么久没心跳就不算在看
SWEEP_EVERY = 30      # 秒:后台清一遍的间隔(main.py 的 lifespan 里跑)


class Viewers:
    def __init__(self, repo: WorkRepo, clock: Callable[[], float] = time.time) -> None:
        self.repo = repo
        self.clock = clock
        self._beats: dict[str, dict[str, float]] = {}
        self._lock = threading.Lock()
        repo.clear_viewers()

    def _write(self, work_id: str) -> list[str]:
        """持锁调用:按内存整份算出 viewers 写回去。"""
        names = sorted(self._beats.get(work_id, {}))
        if not names:
            self._beats.pop(work_id, None)
        self.repo.set_viewers(work_id, names)
        return names

    def _expire(self) -> None:
        """持锁调用:把超时的人清掉,动过的 work 重写一遍。"""
        cutoff = self.clock() - ACTIVE_WINDOW
        for work_id, beats in list(self._beats.items()):
            stale = [u for u, t in beats.items() if t < cutoff]
            if stale:
                for u in stale:
                    del beats[u]
                self._write(work_id)

    def sweep(self) -> None:
        with self._lock:
            self._expire()

    def touch(self, work_id: str, user: str) -> list[str]:
        """心跳:记下这一刻;他本来就在看就不用重写。"""
        with self._lock:
            self._expire()
            beats = self._beats.setdefault(work_id, {})
            fresh = user not in beats
            beats[user] = self.clock()
            return self._write(work_id) if fresh else sorted(beats)

    def leave(self, work_id: str, user: str) -> list[str]:
        with self._lock:
            self._expire()
            if user in self._beats.get(work_id, {}):
                del self._beats[work_id][user]
                return self._write(work_id)
            return sorted(self._beats.get(work_id, {}))
