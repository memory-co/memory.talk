"""agent 轮次怎么切(docs/designs/v5/work-trace.md §2、§10):纯函数,只看 round 的 id / 时刻 / 角色,不碰库。

一轮 = 人的一条输入(role human)起,到下一条人的输入之前;第一条人的输入之前的 round 不属于任何一轮。
后面已经有下一条人的输入,这一轮就结束了(终点 = 它最后一条 round 的时刻);没有就还开着。
round 的时刻各 adapter 写法不一样,统一成 Unix 纳秒:Claude Code / Codex 是 ISO 串(Z 或带时区),Kimi 是 Unix 秒(数字或数字串)。
解不出来的沿用前面(按顺序)最近一条解得出来的;一轮里一个时刻都没有,就不出这一轮。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Sequence

from memorytalk.backend.models.work import Round

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_FRACTION = re.compile(r"\.(\d+)")


def round_time_ns(ts) -> int | None:
    """round 的时刻 → Unix 纳秒;解不出来 → None。"""
    if ts is None or isinstance(ts, bool):
        return None
    s = str(ts).strip()
    if not s:
        return None
    try:
        sec = Decimal(s)                                   # Kimi:Unix 秒
    except InvalidOperation:
        return _iso_ns(s)
    return int(sec * 1_000_000_000) if sec.is_finite() else None


def _iso_ns(s: str) -> int | None:
    """ISO 串 → Unix 纳秒。小数秒自己拆出来(到纳秒),没写时区的当 UTC;Z 和任意位小数 3.10 的 fromisoformat 不认,先改写。"""
    if s[-1] in "Zz":
        s = s[:-1] + "+00:00"
    frac = 0
    if m := _FRACTION.search(s):
        frac = int((m.group(1) + "0" * 9)[:9])
        s = s[:m.start()] + s[m.end():]
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    d = dt - _EPOCH
    return (d.days * 86400 + d.seconds) * 1_000_000_000 + frac


@dataclass(frozen=True)
class Turn:
    first: str          # 第一条 round(人的那条)的 id:这一轮的身份,段 id 由它算
    last: str           # 最后一条 round 的 id
    count: int
    start: int          # Unix 纳秒
    last_at: int        # 最后一条 round 的时刻
    closed: bool        # 后面已经有下一条人的输入了

    @property
    def end(self) -> int | None:
        return self.last_at if self.closed else None


def slice_turns(rounds: Sequence[Round]) -> list[Turn]:
    """按顺序的 round → 一轮一轮;没有时刻的轮次不出。"""
    groups: list[list[tuple[Round, int | None]]] = []
    prev: int | None = None
    for r in rounds:
        t = round_time_ns(r.timestamp)
        if t is None:
            t = prev                                       # 沿用前面最近一条
        else:
            prev = t
        if r.role == "human":
            groups.append([])
        if groups:                                         # 第一条人的输入之前的不算
            groups[-1].append((r, t))
    out = []
    for i, g in enumerate(groups):
        times = [t for _, t in g if t is not None]
        if not times:
            continue
        start = times[0]
        last_at = max(g[-1][1], start)                     # 前面有过时刻,最后一条一定沿用得到;时钟倒着走就别让终点早于起点
        out.append(Turn(first=g[0][0].id, last=g[-1][0].id, count=len(g), start=start, last_at=last_at,
                        closed=i < len(groups) - 1))
    return out


__all__ = ["Turn", "round_time_ns", "slice_turns"]
