"""memory-talk server daemon entry point.

Launched by ``memory-talk server start`` via ``python -m memorytalk.server``.
Configures logging to a rotated file under
``~/.memory-talk/logs/server.log`` BEFORE starting uvicorn, so the
daemon's diagnostics survive the parent CLI process exiting. The
previous design piped the daemon's stderr to the parent CLI's
``subprocess.PIPE``, which was only drained inside a 1.2s failure
probe — anything written afterwards was orphaned (and could even
SIGPIPE the daemon dead once the parent exited).

Two-layer redirect:

1. ``os.dup2`` reassigns OS-level fd 1/2 to ``server.log`` so output
   from C extensions and rogue ``print()`` calls is captured before
   Python's ``logging`` is even configured.
2. ``uvicorn.run(..., log_config=...)`` then installs a
   ``RotatingFileHandler`` on the ``memorytalk`` and ``uvicorn.*``
   loggers, so structured logs rotate (10 MB × 5 = 50 MB cap).

Trade-off: when ``RotatingFileHandler`` rotates ``server.log`` →
``server.log.1``, the dup2'd fd 1/2 still point at the rotated inode.
Raw stderr writes after rotation land in the rotated file rather than
the live one. Accepted because raw stderr should be near-empty in
steady state — Python ``logging`` handles everything from uvicorn and
the app.
"""
from __future__ import annotations
import os
from pathlib import Path

import uvicorn

from memorytalk.config import Config


_LOG_FORMAT = "%(asctime)s %(levelname)-5s %(name)s :: %(message)s"
_LOG_DATEFMT = "%Y-%m-%dT%H:%M:%S%z"
_LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB per file
_LOG_BACKUPS = 5                    # → 50 MB cap


def _redirect_os_fds_to(log_path: Path) -> None:
    """Reassign OS-level stdout/stderr to ``log_path`` so even output
    that bypasses Python's logging system (C extensions, bare prints)
    ends up in the same file."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(log_path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.dup2(fd, 1)
        os.dup2(fd, 2)
    finally:
        os.close(fd)


def build_log_config(log_path: Path) -> dict:
    """``logging.config.dictConfig`` payload — also accepted by
    ``uvicorn.run(log_config=...)``. Exposed so tests can stage it
    against a tmp path without spinning up the full server."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {"format": _LOG_FORMAT, "datefmt": _LOG_DATEFMT},
        },
        "handlers": {
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(log_path),
                "maxBytes": _LOG_MAX_BYTES,
                "backupCount": _LOG_BACKUPS,
                "encoding": "utf-8",
                "formatter": "default",
            },
        },
        "loggers": {
            "memorytalk": {"level": "INFO", "handlers": ["file"], "propagate": False},
            "uvicorn": {"level": "INFO", "handlers": ["file"], "propagate": False},
            "uvicorn.error": {"level": "INFO", "handlers": ["file"], "propagate": False},
            "uvicorn.access": {"level": "INFO", "handlers": ["file"], "propagate": False},
        },
    }


def main() -> None:
    cfg = Config()
    cfg.ensure_dirs()
    log_path = cfg.logs_dir / "server.log"
    _redirect_os_fds_to(log_path)
    uvicorn.run(
        "memorytalk.api:app",
        host="127.0.0.1",
        port=cfg.settings.server.port,
        log_config=build_log_config(log_path),
    )


if __name__ == "__main__":
    main()
