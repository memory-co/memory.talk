"""统一响应信封:所有 /api/* 端点返回 Result[T] = {"data": T, "message": "ok"};出错时 data 为 null、多一个 error 机器码。
显式写在每个端点的 response_model 上,OpenAPI 文档和实际响应一致。"""
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field, model_serializer

T = TypeVar("T")


class Result(BaseModel, Generic[T]):
    data: T | None = None
    message: str = "ok"
    error: str | None = Field(None, description="出错时的机器码;成功时没有")

    @model_serializer(mode="wrap")
    def _drop_empty_error(self, handler):
        out = handler(self)
        if out.get("error") is None:
            out.pop("error", None)            # 成功时就是 {"data", "message"},没有 error 键
        return out


def ok(data=None, message: str = "ok") -> dict:
    return {"data": data, "message": message}


def fail(error: str, message: str) -> dict:
    return {"data": None, "message": message, "error": error}
