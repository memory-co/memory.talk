"""Insight service errors.

The old v3 card subsystem ("insight") is READ-ONLY in v4 — there is no
create / tag / delete service. Reading is handled by ``ReadService``
(``read_insight``) and listing by the ``GET /v4/insights`` route directly
over ``db.insights``. Only the error types live here, kept as the
canonical place callers import insight lifecycle errors from.
"""
from __future__ import annotations


class InsightServiceError(Exception):
    """4xx-equivalent: request rejected."""


class InsightConflict(InsightServiceError):
    """409-equivalent: id already exists."""


class InsightNotFound(InsightServiceError):
    """404-equivalent: insight_id doesn't exist."""
