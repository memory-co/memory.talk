"""Search-quality scoring + 5-tier pytest gate.

Score function is mean reciprocal rank (MRR) over a probe set:
    rank 1 → 1.0, rank 2 → 0.5, rank 3 → 0.333, ..., not in top-k → 0.0
Averaged over a case's probes, the per-case score lands smoothly in [0, 1].

Tier mapping (per the agreed spec):
    Excellent  ≥ 0.9   pass + baseline regression check
    Acceptable 0.7-0.9 pass
    Marginal   0.5-0.7 pass + warnings.warn
    Degraded   0.3-0.5 pytest.xfail (known weak — not blocking)
    Failed     < 0.3   AssertionError (blocks CI)

Baseline tolerance is 0.10: a previously-Excellent case can drop by up to 0.10
without failing, so noise from re-runs (vector recall jitter) doesn't trip CI.
Tighten this once baselines are stable.
"""
from __future__ import annotations
import json
import warnings
from pathlib import Path

import pytest


BASELINE_TOLERANCE = 0.10


def mrr(retrieved_ids: list[str], expected_id: str) -> float:
    try:
        return 1.0 / (retrieved_ids.index(expected_id) + 1)
    except ValueError:
        return 0.0


def quality_gate(score: float, name: str, baseline: float | None) -> None:
    """Apply the 5-tier mapping. Mutates pytest's report state via xfail/warn."""
    if score < 0.3:
        raise AssertionError(f"{name}: score={score:.3f} < 0.3 (Failed)")
    if score < 0.5:
        pytest.xfail(f"{name}: score={score:.3f} (Degraded — known weak)")
    if score < 0.7:
        warnings.warn(
            f"{name}: score={score:.3f} (Marginal — trending down)",
            stacklevel=2,
        )
    # Acceptable (0.7-0.9): pass silently
    # Excellent (≥0.9): regression check against committed baseline
    if baseline is not None and score < baseline - BASELINE_TOLERANCE:
        raise AssertionError(
            f"{name}: score={score:.3f} regressed from baseline {baseline:.3f} "
            f"(tolerance {BASELINE_TOLERANCE})"
        )


def load_baselines(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_baselines(path: Path, baselines: dict[str, float]) -> None:
    path.write_text(
        json.dumps(baselines, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
