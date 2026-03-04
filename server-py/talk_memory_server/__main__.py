"""Entry point for running the server."""
import argparse
import uvicorn

from talk_memory_server.app import create_app


def main():
    parser = argparse.ArgumentParser(description="talk-memory server")
    parser.add_argument("--host", default="localhost", help="Host to bind to")
    parser.add_argument("--port", type=int, default=7900, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
