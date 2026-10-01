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


def trace(client, work_id: str, subtree: bool = False) -> tuple[list[dict], list[dict]]:
    """GET /works/{id}/trace 拍平成两张表:段一行一个(name / spanId / parentSpanId / start / end / status / links + 展开的属性),
    点一行一个(event / spanId / time + 展开的属性)。时间解成 int,没结束的段 end 是 None。"""
    body = client.get(f"/api/works/{work_id}/trace", params={"subtree": subtree}).json()
    spans = [{"name": s["name"], "traceId": s["traceId"], "spanId": s["spanId"], "parentSpanId": s.get("parentSpanId"),
              "start": int(s["startTimeUnixNano"]), "end": int(s["endTimeUnixNano"]) if "endTimeUnixNano" in s else None,
              "status": s["status"]["code"], "links": [l["spanId"] for l in s.get("links", [])], **attrs(s["attributes"])}
             for rs in body["traces"]["resourceSpans"] for ss in rs["scopeSpans"] for s in ss["spans"]]
    points = [{"event": r["eventName"], "traceId": r["traceId"], "spanId": r.get("spanId"), "time": int(r["timeUnixNano"]),
               **attrs(r["attributes"])}
              for rl in body["logs"]["resourceLogs"] for sl in rl["scopeLogs"] for r in sl["logRecords"]]
    return spans, points
