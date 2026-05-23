"""FastAPI app: REST endpoints + WebSocket for live TV.app log stream."""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from .compare import compare_files
from .convert import mux, subs_pgs
from .convert.cli import resolve_metadata
from .convert.metadata import tagger
from .inspect import InspectError, inspect_file
from .tvlog import PREDICATE, LogCapture

WEB_DIR = Path(__file__).parent / "web"

app = FastAPI(title="dolby-tool", version="0.1.0")

# Single-process capture state — this tool is single-user single-tab by design.
_capture: LogCapture | None = None
_capture_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# static


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


# ---------------------------------------------------------------------------
# inspect / compare


class PathPayload(BaseModel):
    path: str


class PathsPayload(BaseModel):
    paths: list[str]
    weights: dict[str, float] | None = None


@app.post("/api/inspect")
async def api_inspect(body: PathPayload) -> dict[str, Any]:
    return await run_in_threadpool(_inspect_response, body)


@app.post("/api/compare")
async def api_compare(body: PathsPayload) -> dict[str, Any]:
    return await run_in_threadpool(_compare_response, body)


@app.get("/api/capabilities")
async def api_capabilities() -> dict[str, Any]:
    return {
        "platform": os.uname().sysname,
        "tools": {
            "ffprobe": shutil.which("ffprobe") is not None,
            "mediainfo": shutil.which("mediainfo") is not None,
            "osascript": shutil.which("osascript") is not None,
            "log": shutil.which("log") is not None,
            "mdfind": shutil.which("mdfind") is not None,
        },
    }


# ---------------------------------------------------------------------------
# file picker (native macOS dialog via osascript)


@app.get("/api/pick")
async def api_pick(multi: bool = False) -> JSONResponse:
    """Pop the macOS 'choose file' dialog and return absolute path(s)."""
    if multi:
        script = (
            'set theFiles to (choose file with prompt "Pick file(s)" with multiple selections allowed)\n'
            'set out to ""\n'
            'repeat with f in theFiles\n'
            '  set out to out & POSIX path of f & "\\n"\n'
            'end repeat\n'
            'return out'
        )
    else:
        script = 'POSIX path of (choose file with prompt "Pick a file")'
    try:
        result = subprocess.run(
            ["osascript", "-e", script], capture_output=True, text=True, timeout=300
        )
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="osascript not available")
    if result.returncode != 0:
        # user pressed cancel → return empty list
        return JSONResponse({"paths": []})
    paths = [
        line.strip() for line in result.stdout.splitlines() if line.strip()
    ]
    return JSONResponse({"paths": paths})


# ---------------------------------------------------------------------------
# find by name — drag-drop fallback (Chrome gives File objects, not file:// URIs)


@app.get("/api/find")
async def api_find(name: str, hint: str = "") -> JSONResponse:
    return await run_in_threadpool(_find_response, name, hint)


def _inspect_response(body: PathPayload) -> dict[str, Any]:
    path = _normalize_path(body.path)
    try:
        return inspect_file(path)
    except InspectError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _compare_response(body: PathsPayload) -> dict[str, Any]:
    paths = [_normalize_path(p) for p in body.paths]
    if not paths:
        raise HTTPException(status_code=400, detail="no paths provided")
    return compare_files(paths, body.weights)


def _find_response(name: str, hint: str = "") -> JSONResponse:
    """Resolve a dropped filename to an absolute path.

    Strategy:
    1. Spotlight (mdfind) — fast, covers indexed volumes.
    2. If mdfind returns nothing, fall back to BSD find(1) searching common
       media roots (/Volumes, ~/Movies, ~/Desktop, ~/Downloads) plus any
       `hint` directory the client already knows about (e.g. the last-used
       directory).  find(1) reaches external/network drives Spotlight skips.
    """
    exts = {".mp4", ".m4v", ".mkv", ".mov", ".ts"}

    # 1. Spotlight
    paths: list[str] = []
    try:
        result = subprocess.run(
            ["mdfind", f"kMDItemDisplayName == '{name}'"],
            capture_output=True, text=True, timeout=5,
        )
        paths = [p.strip() for p in result.stdout.splitlines() if p.strip()]
        paths = [p for p in paths if Path(p).suffix.lower() in exts]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        paths = []

    # 2. find(1) fallback — used when Spotlight misses (external/excluded volumes)
    if not paths:
        search_roots = ["/Volumes", os.path.expanduser("~/Movies"),
                        os.path.expanduser("~/Desktop"), os.path.expanduser("~/Downloads")]
        if hint:
            h = os.path.expanduser(hint)
            if os.path.isdir(h):
                search_roots.insert(0, h)
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_roots = [r for r in search_roots if not (r in seen or seen.add(r))]  # type: ignore[func-returns-value]
        for root in unique_roots:
            if not os.path.exists(root):
                continue
            try:
                result = subprocess.run(
                    ["find", root, "-maxdepth", "8", "-name", name],
                    capture_output=True, text=True, timeout=10,
                )
                for p in result.stdout.splitlines():
                    p = p.strip()
                    if p and Path(p).suffix.lower() in exts and p not in paths:
                        paths.append(p)
            except subprocess.TimeoutExpired:
                continue

    return JSONResponse({"name": name, "paths": paths[:20]})


# ---------------------------------------------------------------------------
# directory listing — used by Compare tab to pull all media in a folder


@app.get("/api/list")
async def api_list(path: str) -> dict[str, Any]:
    path = _normalize_path(path)
    if not os.path.isdir(path):
        raise HTTPException(status_code=400, detail="not a directory")
    exts = {".mp4", ".m4v", ".mkv", ".mov", ".ts"}
    entries = []
    for name in sorted(os.listdir(path)):
        full = os.path.join(path, name)
        if not os.path.isfile(full):
            continue
        if Path(name).suffix.lower() not in exts:
            continue
        try:
            size = os.path.getsize(full)
        except OSError:
            size = None
        entries.append({"path": full, "name": name, "size": size})
    return {"path": path, "files": entries}


# ---------------------------------------------------------------------------
# convert — MKV → Apple-TV-ready .m4v (sync, runs in threadpool)


class ConvertPayload(BaseModel):
    input: str
    output: str
    overwrite: bool = False
    no_metadata: bool = True  # web UI defaults to OFF — metadata is interactive
    metadata_id: str | None = None
    storefront: str = "US"
    show: str | None = None
    season: int | None = None
    episode: int | None = None
    skip_pgs: bool = False
    season_artwork: str | None = None  # path to an image to stamp as covr


class TagPayload(BaseModel):
    file: str  # may be a file OR a directory (loops every .mp4/.m4v inside)
    metadata_id: str | None = None
    storefront: str = "US"
    show: str | None = None
    season: int | None = None
    episode: int | None = None
    season_artwork: str | None = None


@app.post("/api/convert")
async def api_convert(body: ConvertPayload) -> dict[str, Any]:
    return await run_in_threadpool(_run_convert, body)


@app.post("/api/tag")
async def api_tag(body: TagPayload) -> dict[str, Any]:
    return await run_in_threadpool(_run_tag, body)


def _run_convert(body: ConvertPayload) -> dict[str, Any]:
    src = Path(_normalize_path(body.input))
    dst = Path(_normalize_path(body.output))
    if not src.is_file():
        raise HTTPException(status_code=400, detail=f"input not found: {src}")
    summary: dict[str, Any] = {"input": str(src), "output": str(dst)}
    try:
        summary["mux"] = mux.mux(src, dst, overwrite=body.overwrite)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not body.skip_pgs:
        info = mux.probe(src)
        if info.bitmap_subs:
            pgs_out = dst.with_suffix(".pgs.m4v")
            r = subs_pgs.convert_and_remux(src, dst, info.bitmap_subs, output=pgs_out)
            summary["pgs"] = {
                "converted": r.converted, "skipped": r.skipped, "reason": r.reason,
            }
            if r.converted:
                pgs_out.replace(dst)

    if not body.no_metadata:
        meta = resolve_metadata(
            str(src), storefront=body.storefront, language=None,
            content_id=body.metadata_id, interactive=False,
            show_override=body.show, season_override=body.season,
            episode_override=body.episode,
        )
        if meta is not None:
            summary["matched_title"] = meta.title
            summary["metadata"] = tagger.apply(dst, meta)
        else:
            summary["metadata"] = {"applied": False, "reason": "no match"}

    if body.season_artwork:
        art = Path(_normalize_path(body.season_artwork))
        summary["artwork"] = tagger.apply_artwork(dst, art)

    return summary


def _run_tag(body: TagPayload) -> dict[str, Any]:
    target = Path(_normalize_path(body.file))
    if target.is_dir():
        files = sorted(p for p in target.iterdir()
                       if p.is_file() and p.suffix.lower() in {".mp4", ".m4v"})
    elif target.is_file():
        files = [target]
    else:
        raise HTTPException(status_code=400, detail=f"not found: {target}")

    art = Path(_normalize_path(body.season_artwork)) if body.season_artwork else None
    art_only = art is not None and not (body.metadata_id or body.show)

    results: list[dict[str, Any]] = []
    for path in files:
        entry: dict[str, Any] = {"file": str(path)}
        if not art_only:
            meta = resolve_metadata(
                str(path), storefront=body.storefront, language=None,
                content_id=body.metadata_id, interactive=False,
                show_override=body.show, season_override=body.season,
                episode_override=body.episode,
            )
            if meta is None:
                entry["metadata"] = {"applied": False, "reason": "no match"}
            else:
                entry["matched_title"] = meta.title
                entry["metadata"] = tagger.apply(path, meta)
        if art is not None:
            entry["artwork"] = tagger.apply_artwork(path, art)
        results.append(entry)

    if len(results) == 1:
        return results[0]
    return {"directory": str(target), "files": results}


# ---------------------------------------------------------------------------
# TV.app log capture — WebSocket


@app.websocket("/ws/tvlog")
async def ws_tvlog(ws: WebSocket) -> None:
    global _capture
    await ws.accept()
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue | None = None
    pump_task: asyncio.Task | None = None
    try:
        while True:
            msg = await ws.receive_json()
            cmd = msg.get("cmd")

            if cmd == "start":
                async with _capture_lock:
                    if _capture is not None:
                        if queue is not None:
                            _capture.unsubscribe(queue)
                        _capture.stop()
                    if pump_task is not None:
                        pump_task.cancel()
                    _capture = LogCapture()
                    _capture.start(loop)
                    queue = _capture.subscribe()
                await ws.send_json({"type": "started", "predicate": PREDICATE})
                # Pump events to client while capture is live
                pump_task = asyncio.create_task(_pump(ws, queue))

            elif cmd == "stop":
                async with _capture_lock:
                    if _capture is None:
                        await ws.send_json({"type": "error", "message": "no capture running"})
                        continue
                    summary = _capture.stop()
                    if queue is not None:
                        _capture.unsubscribe(queue)
                    _capture = None
                    queue = None
                    if pump_task is not None:
                        pump_task.cancel()
                        pump_task = None
                await ws.send_json({"type": "summary", "summary": summary})

            elif cmd == "ping":
                await ws.send_json({"type": "pong"})

            else:
                await ws.send_json({"type": "error", "message": f"unknown cmd: {cmd}"})
    except WebSocketDisconnect:
        pass
    finally:
        if pump_task is not None:
            pump_task.cancel()
        async with _capture_lock:
            if _capture is not None:
                if queue is not None:
                    _capture.unsubscribe(queue)
                _capture.stop()
                _capture = None


async def _pump(ws: WebSocket, queue: asyncio.Queue) -> None:
    try:
        while True:
            event = await queue.get()
            await ws.send_json({"type": "event", "event": event})
    except (WebSocketDisconnect, RuntimeError):
        return


# ---------------------------------------------------------------------------
# helpers


def _normalize_path(p: str) -> str:
    """Strip file:// prefix and decode percent-escapes so the UI can send drag-drop URIs."""
    p = p.strip()
    if p.startswith("file://"):
        from urllib.parse import unquote
        p = unquote(p[len("file://") :])
    return os.path.expanduser(p)
