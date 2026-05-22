"""Entrypoint: `python -m dolby_tool` starts the FastAPI server on localhost:7878."""
from __future__ import annotations

import argparse
import ipaddress

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(prog="dolby-tool")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7878)
    parser.add_argument("--reload", action="store_true", help="Auto-reload on code changes (dev).")
    args = parser.parse_args()

    try:
        is_loopback = ipaddress.ip_address(args.host).is_loopback
    except ValueError:
        is_loopback = args.host in {"localhost"}

    if not is_loopback:
        print(
            f"⚠️  Warning: binding to non-loopback host {args.host}. "
            "This tool can inspect arbitrary local file paths."
        )

    uvicorn.run(
        "dolby_tool.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
