"""最小 CLI:serve。start / stop / status / daemon 等 task 层一起做。"""
from __future__ import annotations

import argparse

import uvicorn


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="memory.talk")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="前台起 API")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--reload", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "serve":
        uvicorn.run("main:create_app", factory=True, host=args.host, port=args.port,
                    reload=args.reload)


if __name__ == "__main__":
    main()
