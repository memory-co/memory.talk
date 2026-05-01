"""单测：_fmt_latency 在 ms / s 边界的格式。

规则：
- < 1000 ms → "{int}ms"
- ≥ 1000 ms → "{x.x}s"（保留 1 位小数）
"""
from __future__ import annotations

from memorytalk.cli.setup.steps.embedding import _fmt_latency


def test_sub_millisecond_rounds_to_zero_ms():
    assert _fmt_latency(0.0001) == "0ms"


def test_few_hundred_ms():
    assert _fmt_latency(0.412) == "412ms"


def test_just_under_one_second():
    assert _fmt_latency(0.999) == "999ms"


def test_exactly_one_second_uses_seconds():
    assert _fmt_latency(1.0) == "1.0s"


def test_multi_second():
    assert _fmt_latency(12.345) == "12.3s"
