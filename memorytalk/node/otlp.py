"""节点这一侧的 OTLP/JSON:算 id、编属性、拼一批推给中心的文档(和 GET /works/{id}/trace 读出来的一个形状)。

id 的算法和中心一样(work-trace.md §4),取 sha256 的前 8 字节;节点只算 agent 那三层,算得出来就不用问中心。
"""
from __future__ import annotations

import hashlib
import socket

KIND_INTERNAL = 1
STATUS_UNSET, STATUS_OK, STATUS_ERROR = 0, 1, 2
SCOPE = {"name": "memorytalk.node", "version": "5"}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def session_span_id(worklet_id: str, session_id: str, first_uid: str) -> str:
    """会话段:同一个会话 /resume 回来是新的一段,所以带上这一段第一条记录的 uid。"""
    return _sha(f"memorytalk/span/session/{worklet_id}/{session_id}/{first_uid}")


def turn_span_id(worklet_id: str, input_uid: str) -> str:
    """轮次段:由这一轮人那条输入的 uid 算。"""
    return _sha(f"memorytalk/span/turn/{worklet_id}/{input_uid}")


def tool_span_id(worklet_id: str, call_id: str) -> str:
    """工具段:由调用 id 算(Claude Code 的 tool_use.id)。"""
    return _sha(f"memorytalk/span/tool/{worklet_id}/{call_id}")


def value(v) -> dict:
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, int):
        return {"intValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    return {"stringValue": str(v)}


def kvs(attrs: dict) -> list[dict]:
    return [{"key": k, "value": value(v)} for k, v in attrs.items() if v is not None]


def span(trace_id: str, span_id: str, parent: str | None, name: str, start: int, attrs: dict, *,
         end: int | None = None, status: int = STATUS_UNSET, links: list[str] = ()) -> dict:
    """一个段:没有 end 就是开着的(中心那边按 spanId 合并属性),有 end 就结束(结束即定稿)。"""
    out = {"traceId": trace_id, "spanId": span_id}
    if parent:
        out["parentSpanId"] = parent
    out.update(name=name, kind=KIND_INTERNAL, startTimeUnixNano=str(start))
    if end is not None:
        out["endTimeUnixNano"] = str(end)
    out.update(attributes=kvs(attrs), links=[{"traceId": trace_id, "spanId": s, "attributes": []} for s in links],
               status={"code": status})
    return out


def record(trace_id: str, span_id: str | None, event: str, at: int, uid: str, attrs: dict, body: str | None = None) -> dict:
    """一个点:uid 是它的身份(中心按它去重),body 是正文。"""
    out = {"timeUnixNano": str(at), "eventName": event, "traceId": trace_id}
    if span_id:
        out["spanId"] = span_id
    if body is not None:
        out["body"] = {"stringValue": body}
    out["attributes"] = kvs({"log.record.uid": uid, **attrs})
    return out


def document(spans: list[dict], records: list[dict]) -> dict:
    resource = {"attributes": kvs({"service.name": "memory.talk", "memorytalk.node": socket.gethostname()})}
    return {"traces": {"resourceSpans": [{"resource": resource, "scopeSpans": [{"scope": SCOPE, "spans": spans}]}]},
            "logs": {"resourceLogs": [{"resource": resource, "scopeLogs": [{"scope": SCOPE, "logRecords": records}]}]}}
