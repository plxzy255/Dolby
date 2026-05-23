"""Entrypoint: `python -m dolby_tool` starts the FastAPI server on localhost:7878."""
from __future__ import annotations

import argparse
import ipaddress
import json
import sys

import uvicorn

from .movpkg import analyze_movpkg, movpkg_summary_markdown


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "movpkg":
        _main_movpkg(sys.argv[2:])
        return

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


def _main_movpkg(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="dolby-tool movpkg")
    parser.add_argument("path", help="Path to a downloaded TV.app .movpkg package.")
    parser.add_argument(
        "--selected-group",
        help="Optional HLS AudioGroup selected in a TV Capture, used to refine the verdict.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    args = parser.parse_args(argv)

    summary = analyze_movpkg(args.path, selected_group=args.selected_group)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(movpkg_summary_markdown(summary))


if __name__ == "__main__":
    main()
