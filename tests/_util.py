"""场景共用的小工具(conftest 里的函数导出一份,避免 import conftest)。"""
from tests.conftest import git_authors, git_log  # noqa: F401


def _value(v: dict):
    """OTLP AnyValue → Python 值;intValue 是十进制字符串,解回 int。"""
    if "intValue" in v:
        return int(v["intValue"])
    for k in ("stringValue", "boolValue", "doubleValue"):
        if k in v:
            return v[k]
    return v


def attrs(kvs: list[dict]) -> dict:
    return {kv["key"]: _value(kv["value"]) for kv in kvs}


def trace(client, work_id: str, subtree: bool = False, agent: bool = True, **params) -> tuple[list[dict], list[dict]]:
    """GET /works/{id}/trace 拍平成两张表:段一行一个(name / spanId / parentSpanId / start / end / status / links + 展开的属性),
    点一行一个(event / spanId / time / body + 展开的属性)。时间解成 int,没结束的段 end 是 None。
    默认带上 agent 那几层和正文(接口默认不带;测默认的场景自己传 agent=False)。"""
    params = {"subtree": subtree, "agent": agent, "bodies": agent, **params}
    body = client.get(f"/api/works/{work_id}/trace", params=params).json()
    spans = [{"name": s["name"], "traceId": s["traceId"], "spanId": s["spanId"], "parentSpanId": s.get("parentSpanId"),
              "start": int(s["startTimeUnixNano"]), "end": int(s["endTimeUnixNano"]) if "endTimeUnixNano" in s else None,
              "status": s["status"]["code"], "links": [l["spanId"] for l in s.get("links", [])], **attrs(s["attributes"])}
             for rs in body["traces"]["resourceSpans"] for ss in rs["scopeSpans"] for s in ss["spans"]]
    points = [{"event": r["eventName"], "traceId": r["traceId"], "spanId": r.get("spanId"), "time": int(r["timeUnixNano"]),
               **({"body": r["body"]["stringValue"]} if "body" in r else {}), **attrs(r["attributes"])}
              for rl in body["logs"]["resourceLogs"] for sl in rl["scopeLogs"] for r in sl["logRecords"]]
    return spans, points


# ---- 节点放在测试进程里跑:中心和节点之间不走 socket,直接调对方(协议一样:watch / flush,推的就是 POST 的那个 body) ----

class LocalCenter:
    """节点眼里的中心:推一批 = WorkService.write_trace(POST /works/{id}/trace 进的就是它)。"""

    def __init__(self, works) -> None:
        self.works, self.pushed = works, []

    def push(self, work_id: str, body: dict) -> dict:
        self.pushed.append(body)
        return self.works.write_trace(work_id, {"traces": body["traces"], "logs": body["logs"]}, body.get("cursors", []))

    def cursors(self, work_id: str, worklet_id: str) -> list[dict]:
        return self.works.cursors(work_id, worklet_id).cursors


class LocalNodes:
    """中心眼里的节点(替掉 WorkService.nodes)。"""

    def __init__(self, node) -> None:
        self.node = node

    def watch(self, spec: dict) -> bool:
        self.node.watch(spec)
        return True

    def flush(self, worklet_id: str, reason: str) -> bool:
        return self.node.flush(worklet_id, reason)["flushed"]

    def list(self) -> dict:
        return self.node.list()
