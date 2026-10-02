"""中心 → 节点:经节点的 unix socket 说 watch / flush / list(work-node.md §7)。

节点没起来、说不通都不挡人的动作(开 / 关 / 归档照做,只记日志):agent 的记录晚一点进 trace,
关掉的时候没 flush 上的,由中心兜底把开着的 agent 段跟着 worklet 段结束(Trace.agent_ended)。
"""
from __future__ import annotations

import logging
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

FLUSH_TIMEOUT = 15.0           # 秒;等不到就不等,迟到的点照收,段不重开


class NodeClient:
    def __init__(self, socket_path: Path, timeout: float = 5.0) -> None:
        self.socket_path = Path(socket_path)
        self.timeout = timeout

    def _client(self, timeout: float) -> httpx.Client:
        return httpx.Client(transport=httpx.HTTPTransport(uds=str(self.socket_path)), base_url="http://node", timeout=timeout)

    def watch(self, spec: dict) -> bool:
        """让节点盯着这个工作单元(幂等)。交回说没说通。"""
        try:
            with self._client(self.timeout) as c:
                c.post("/watch", json=spec).raise_for_status()
            return True
        except (httpx.HTTPError, OSError) as e:
            log.warning("没让节点盯上 %s:%s", spec.get("worklet_id"), e)
            return False

    def flush(self, worklet_id: str, reason: str) -> bool:
        """让节点读到头、推完,结束开着的 agent 段,不再盯。交回节点说没说「完了」。"""
        try:
            with self._client(FLUSH_TIMEOUT) as c:
                r = c.post("/flush", json={"worklet_id": worklet_id, "reason": reason})
                r.raise_for_status()
                return bool(r.json().get("flushed"))
        except (httpx.HTTPError, OSError, ValueError) as e:
            log.warning("节点没 flush %s(%s):%s", worklet_id, reason, e)
            return False

    def list(self) -> dict | None:
        try:
            with self._client(self.timeout) as c:
                return c.get("/list").json()
        except (httpx.HTTPError, OSError, ValueError):
            return None
