"""Entrypoint: `python -m dolby_tool` starts the FastAPI server on localhost:7878."""
from __future__ import annotations

import argparse
import ipaddress
import json
import sys
import time

import uvicorn

from .local_hls import create_hls_server, open_hls_url, playlist_url
from .movpkg import analyze_movpkg, movpkg_summary_markdown
from .tvlog import (
    LOCAL_PLAYER_PREDICATE,
    PREDICATE,
    LogCapture,
    summarize_log_file,
    tvlog_summary_markdown,
)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "movpkg":
        _main_movpkg(sys.argv[2:])
        return
    if len(sys.argv) > 1 and sys.argv[1] == "tvlog-parse":
        _main_tvlog_parse(sys.argv[2:])
        return
    if len(sys.argv) > 1 and sys.argv[1] == "tvlog-capture":
        _main_tvlog_capture(sys.argv[2:])
        return
    if len(sys.argv) > 1 and sys.argv[1] == "hls-serve":
        _main_hls_serve(sys.argv[2:])
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


def _main_tvlog_parse(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="dolby-tool tvlog-parse")
    parser.add_argument("path", help="Path to a saved `log stream --style compact` text file.")
    parser.add_argument(
        "--profile",
        choices=["tv", "local-player"],
        default="local-player",
        help="Predicate profile recorded with the capture. Used only for summary metadata.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    args = parser.parse_args(argv)

    summary = summarize_log_file(args.path, predicate=_predicate_for_profile(args.profile))
    _print_tvlog_summary(summary, as_json=args.json)


def _main_tvlog_capture(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="dolby-tool tvlog-capture")
    parser.add_argument(
        "--profile",
        choices=["tv", "local-player"],
        default="tv",
        help="Use `tv` for normal TV.app capture or `local-player` for QuickTime/Safari controls.",
    )
    parser.add_argument("--seconds", type=float, default=60.0, help="Capture duration.")
    parser.add_argument("--output", help="Optional path to write the structured JSON summary.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    args = parser.parse_args(argv)

    capture = LogCapture(predicate=_predicate_for_profile(args.profile))
    print(
        f"Capturing {args.profile} playback logs for {args.seconds:g}s...",
        file=sys.stderr,
    )
    capture.start()
    try:
        time.sleep(max(args.seconds, 0))
    except KeyboardInterrupt:
        pass
    summary = capture.stop()
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, sort_keys=True)
            f.write("\n")
    _print_tvlog_summary(summary, as_json=args.json)


def _main_hls_serve(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="dolby-tool hls-serve")
    parser.add_argument("directory", help="Prepared HLS directory containing a playlist.")
    parser.add_argument("--playlist", default="master.m3u8", help="Playlist filename to print/open.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host; keep loopback for local playback.")
    parser.add_argument("--port", type=int, default=8765, help="Bind port. Use 0 for an ephemeral port.")
    parser.add_argument(
        "--open",
        choices=["none", "quicktime", "safari"],
        default="none",
        help="Optionally open the playlist URL in an Apple player.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress request logging.")
    args = parser.parse_args(argv)

    server = create_hls_server(args.directory, host=args.host, port=args.port, quiet=args.quiet)
    url = playlist_url(server, args.playlist)
    print(f"Serving HLS from {args.directory}", flush=True)
    print(f"URL: {url}", flush=True)
    if args.open != "none":
        open_hls_url(url, args.open)
        print(f"Opened in {args.open}.", flush=True)
    print("Press Ctrl-C to stop.", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _predicate_for_profile(profile: str) -> str:
    if profile == "local-player":
        return LOCAL_PLAYER_PREDICATE
    return PREDICATE


def _print_tvlog_summary(summary: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(tvlog_summary_markdown(summary))


if __name__ == "__main__":
    main()
