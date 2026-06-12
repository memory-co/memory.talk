"""File logging wiring for searchbase/local.

Attaches three rotating file handlers — one per concern — so an
operator can ``tail -f`` what the backend is doing without parsing the
whole-app log.

Categories:

  - ``memorytalk.searchbase.maintenance`` → ``maintenance.log``
        compact start/finish, EMFILE recovery, reconnect outcomes.
  - ``memorytalk.searchbase.query`` → ``query.log``
        one line per ``backend.search()`` — collection, top_k,
        query length, filter keys, hit count, elapsed ms.
  - ``memorytalk.searchbase.index`` → ``index.log``
        one line per ``backend.upsert / delete / delete_where``.

Distinct from the business layer's ``logs/search/<UTC>.jsonl`` audit
(which captures full ``SearchResponse`` bodies, business-side). That's
the "what did the user see" log; ours is the "what hit the backend"
log. They're complementary — different granularities for different
operator questions.

Rotation is the stdlib default (``TimedRotatingFileHandler``,
midnight rollover, 14 days retained). No structured format — plain
text with ISO-Z timestamps so ``grep`` / ``tail -f`` are the entire
analysis toolkit. The business-layer search log already carries the
JSONL surface for ``jq``-style queries; we don't duplicate that.

``propagate=False`` on each logger so messages don't bubble to the
root logger and pollute stdout (caller asked for stdout to stay clean).
"""
from __future__ import annotations

import logging
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


_CATEGORIES = ("maintenance", "query", "index")
_LOGGER_PREFIX = "memorytalk.searchbase."


def setup_file_logging(log_dir: Path | str) -> None:
    """Wire ``maintenance.log`` / ``query.log`` / ``index.log`` under
    ``log_dir``. Idempotent — re-running won't stack duplicate handlers
    on the same logger (we tag our handler so we can find it again).

    The handler is daily-rotating with a two-week retention; messages
    don't propagate to the root logger.
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    formatter.converter = time.gmtime  # ISO-Z = UTC

    for category in _CATEGORIES:
        logger = logging.getLogger(_LOGGER_PREFIX + category)
        # Idempotency: skip if we've already attached our handler to
        # this logger (matching by tag on the handler instance).
        if any(getattr(h, "_searchbase_tag", None) == category
               for h in logger.handlers):
            continue
        handler = TimedRotatingFileHandler(
            log_dir / f"{category}.log",
            when="midnight",
            backupCount=14,
            encoding="utf-8",
            utc=True,
        )
        handler.setFormatter(formatter)
        handler._searchbase_tag = category  # marker for idempotency check
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        # Don't bubble to the root logger / stdout — caller asked for
        # stdout to stay clean; tail -f is the intended access pattern.
        logger.propagate = False
