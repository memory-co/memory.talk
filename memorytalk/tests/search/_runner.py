"""Shared runner for search-quality tests.

Each test case owns its own ``probes.json`` (a list of ``[query, expected_id]``
pairs). The runner is mode-agnostic — it just posts every probe to /v2/search,
collects ranks, computes mean MRR, and applies the quality gate. If the score
lands in the Excellent band (≥0.9) it bumps the in-memory baselines dict —
conftest writes that back to ``_baselines.json`` at session-end when
``UPDATE_BASELINES=1``.
"""
from __future__ import annotations
import json
from pathlib import Path

from memorytalk.tests.search._quality import mrr, quality_gate


def _ids_for(expected_id: str, response: dict) -> list[str]:
    if expected_id.startswith("card_"):
        return [r["card_id"] for r in response["cards"]["results"]]
    if expected_id.startswith("sess_"):
        return [r["session_id"] for r in response["sessions"]["results"]]
    raise ValueError(f"unrecognized expected_id prefix: {expected_id!r}")


def load_probes(probes_path: Path) -> list[tuple[str, str]]:
    raw = json.loads(probes_path.read_text(encoding="utf-8"))
    return [(item[0], item[1]) for item in raw]


def run_case(
    client,
    baselines: dict[str, float],
    name: str,
    probes: list[tuple[str, str]],
) -> float:
    """Run all probes for one case and apply the quality gate.

    Returns the computed score so callers (or fixture finalizers) can record it.
    """
    scores: list[float] = []
    for query, expected_id in probes:
        r = client.post("/v2/search", json={"query": query, "top_k": 5})
        assert r.status_code == 200, f"{name} probe {query!r}: {r.status_code} {r.text}"
        ids = _ids_for(expected_id, r.json())
        scores.append(mrr(ids, expected_id))

    score = sum(scores) / len(scores)
    baseline = baselines.get(name)

    if score >= 0.9 and (baseline is None or score > baseline):
        baselines[name] = round(score, 4)

    quality_gate(score, name, baseline)
    return score
