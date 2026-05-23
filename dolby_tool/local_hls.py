"""Range-capable localhost serving for prepared HLS folders."""
from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import threading
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote, urlparse


class RangeRequestHandler(SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler variant with single-range support."""

    range: tuple[int, int] | None = None

    def send_head(self) -> BinaryIO | None:
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()
        ctype = self.guess_type(path)
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return None

        size = os.fstat(f.fileno()).st_size
        start, end = self._parse_range(size)
        if start is None:
            self.range = None
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-type", ctype)
            self.send_header("Content-Length", str(size))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Last-Modified", self.date_time_string(os.fstat(f.fileno()).st_mtime))
            self.end_headers()
            return f

        if start >= size or end < start:
            f.close()
            self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            return None

        end = min(end, size - 1)
        self.range = (start, end)
        f.seek(start)
        self.send_response(HTTPStatus.PARTIAL_CONTENT)
        self.send_header("Content-type", ctype)
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Last-Modified", self.date_time_string(os.fstat(f.fileno()).st_mtime))
        self.end_headers()
        return f

    def copyfile(self, source: BinaryIO, outputfile: BinaryIO) -> None:
        if self.range is None:
            return super().copyfile(source, outputfile)

        start, end = self.range
        remaining = end - start + 1
        while remaining > 0:
            chunk = source.read(min(64 * 1024, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)

    def _parse_range(self, size: int) -> tuple[int | None, int]:
        header = self.headers.get("Range")
        if not header:
            return None, size - 1
        if not header.startswith("bytes=") or "," in header:
            return size, 0

        spec = header.removeprefix("bytes=").strip()
        start_s, sep, end_s = spec.partition("-")
        if sep != "-":
            return size, 0
        try:
            if start_s == "":
                suffix = int(end_s)
                if suffix <= 0:
                    return size, 0
                return max(size - suffix, 0), size - 1
            start = int(start_s)
            end = int(end_s) if end_s else size - 1
        except ValueError:
            return size, 0
        return start, end

    def log_message(self, format: str, *args: object) -> None:
        if not getattr(self.server, "quiet", False):
            super().log_message(format, *args)


def create_hls_server(
    directory: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    quiet: bool = False,
) -> ThreadingHTTPServer:
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"HLS directory does not exist: {root}")
    handler = partial(RangeRequestHandler, directory=str(root))
    server = ThreadingHTTPServer((host, port), handler)
    server.quiet = quiet  # type: ignore[attr-defined]
    return server


def playlist_url(server: ThreadingHTTPServer, playlist: str = "master.m3u8") -> str:
    host, port = server.server_address[:2]
    return f"http://{host}:{port}/{quote(playlist)}"


@contextlib.contextmanager
def running_hls_server(
    directory: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    quiet: bool = False,
) -> Iterator[ThreadingHTTPServer]:
    server = create_hls_server(directory, host=host, port=port, quiet=quiet)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def open_hls_url(url: str, app: str) -> None:
    if app == "none":
        return
    app_name = {
        "quicktime": "QuickTime Player",
        "safari": "Safari",
    }[app]
    subprocess.run(["open", "-a", app_name, url], check=False)


def prepare_hls_from_movpkg(
    movpkg: str | Path,
    output_dir: str | Path,
    *,
    overwrite: bool = False,
) -> dict[str, object]:
    """Flatten a simple persisted-HLS `.movpkg` into a serveable HLS folder."""
    source = Path(movpkg).expanduser().resolve()
    output = Path(output_dir).expanduser().resolve()
    if not source.is_dir():
        raise ValueError(f".movpkg directory does not exist: {source}")
    if output.exists() and any(output.iterdir()) and not overwrite:
        raise ValueError(f"Output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    master_source = _master_playlist_path(source)
    (output / "master.m3u8").write_text(_read_playlist(master_source), encoding="utf-8")

    stream_outputs: list[dict[str, object]] = []
    for stream in _boot_streams(source):
        stream_dir = source / stream["path"]
        stream_info = _parse_stream_info(stream_dir)
        playlist_name = _url_basename(stream["network_url"]) or stream_info["playlist"].name
        segment_name = _segment_uri_from_playlist(stream_info["playlist"])
        segment_path = output / segment_name

        with segment_path.open("wb") as f:
            for fragment in stream_info["fragments"]:
                f.write((stream_dir / fragment["path"]).read_bytes())

        (output / playlist_name).write_text(_read_playlist(stream_info["playlist"]), encoding="utf-8")
        stream_outputs.append(
            {
                "stream_id": stream["id"],
                "playlist": playlist_name,
                "segment": segment_name,
                "bytes": segment_path.stat().st_size,
                "fragments": len(stream_info["fragments"]),
                "media_bytes_stored": stream_info["media_bytes_stored"],
            }
        )

    return {
        "source": str(source),
        "output_dir": str(output),
        "master_playlist": "master.m3u8",
        "streams": stream_outputs,
    }


def prepare_hls_summary_markdown(summary: dict[str, object]) -> str:
    lines = ["# Local HLS prepare summary\n"]
    lines.append(f"- source: `{summary['source']}`")
    lines.append(f"- output: `{summary['output_dir']}`")
    lines.append(f"- master playlist: `{summary['master_playlist']}`")
    lines.append("")
    lines.append("| stream ID | playlist | segment | fragments | bytes | media bytes stored |")
    lines.append("| --- | --- | --- | ---: | ---: | ---: |")
    for stream in summary.get("streams", []):
        row = stream if isinstance(stream, dict) else {}
        lines.append(
            "| "
            f"`{row.get('stream_id')}` | "
            f"`{row.get('playlist')}` | "
            f"`{row.get('segment')}` | "
            f"{row.get('fragments')} | "
            f"{row.get('bytes')} | "
            f"{row.get('media_bytes_stored')} |"
        )
    return "\n".join(lines) + "\n"


def package_hls_from_file(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    overwrite: bool = False,
    audio_stream: int = 0,
    segment_time: float = 6.0,
    split_audio_group: bool = True,
) -> dict[str, object]:
    """Stream-copy a local media file into fMP4 HLS for QuickTime/Safari controls."""
    source = Path(input_path).expanduser().resolve()
    output = Path(output_dir).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"Input media file does not exist: {source}")
    if audio_stream < 0:
        raise ValueError("audio_stream must be >= 0")
    if segment_time <= 0:
        raise ValueError("segment_time must be > 0")

    if output.exists() and any(output.iterdir()):
        if not overwrite:
            raise ValueError(f"Output directory is not empty: {output}")
        _clear_directory(output)
    output.mkdir(parents=True, exist_ok=True)

    var_stream_map = (
        "v:0,agroup:audio,name:video "
        "a:0,agroup:audio,language:eng,name:English,default:yes"
        if split_audio_group
        else "v:0,a:0,name:main"
    )
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y" if overwrite else "-n",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        f"0:a:{audio_stream}",
        "-c",
        "copy",
        "-f",
        "hls",
        "-hls_time",
        _format_float(segment_time),
        "-hls_playlist_type",
        "vod",
        "-hls_segment_type",
        "fmp4",
        "-hls_flags",
        "independent_segments",
        "-master_pl_name",
        "master.m3u8",
        "-var_stream_map",
        var_stream_map,
        "-hls_segment_filename",
        str(output / "stream_%v_%04d.m4s"),
        str(output / "stream_%v.m3u8"),
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    stderr_lines = result.stderr.splitlines()
    return {
        "source": str(source),
        "output_dir": str(output),
        "master_playlist": "master.m3u8",
        "audio_stream": audio_stream,
        "segment_time": segment_time,
        "split_audio_group": split_audio_group,
        "playlists": _hls_playlist_inventory(output),
        "ffmpeg_stderr_tail": stderr_lines[-20:],
    }


def package_hls_summary_markdown(summary: dict[str, object]) -> str:
    lines = ["# Local HLS package summary\n"]
    lines.append(f"- source: `{summary['source']}`")
    lines.append(f"- output: `{summary['output_dir']}`")
    lines.append(f"- master playlist: `{summary['master_playlist']}`")
    lines.append(f"- audio stream: `{summary['audio_stream']}`")
    lines.append(f"- split audio group: `{summary['split_audio_group']}`")
    lines.append("")
    lines.append("| playlist | media segments | init maps | referenced bytes |")
    lines.append("| --- | ---: | ---: | ---: |")
    for playlist in summary.get("playlists", []):
        row = playlist if isinstance(playlist, dict) else {}
        lines.append(
            "| "
            f"`{row.get('playlist')}` | "
            f"{row.get('segments')} | "
            f"{row.get('init_maps')} | "
            f"{row.get('bytes')} |"
        )
    return "\n".join(lines) + "\n"


def _clear_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _format_float(value: float) -> str:
    return f"{value:g}"


def _hls_playlist_inventory(output: Path) -> list[dict[str, object]]:
    rows = []
    for playlist in sorted(output.glob("*.m3u8")):
        references = _playlist_references(playlist)
        segment_uris = [uri for uri in references["segments"] if not uri.endswith(".m3u8")]
        init_uris = references["init_maps"]
        byte_total = 0
        for uri in [*init_uris, *segment_uris]:
            path = output / uri
            if path.exists():
                byte_total += path.stat().st_size
        rows.append(
            {
                "playlist": playlist.name,
                "segments": len(segment_uris),
                "init_maps": len(init_uris),
                "bytes": byte_total,
            }
        )
    return rows


def _playlist_references(path: Path) -> dict[str, list[str]]:
    init_maps = []
    segments = []
    for line in _read_playlist(path).splitlines():
        line = line.strip()
        if line.startswith("#EXT-X-MAP:"):
            marker = 'URI="'
            if marker in line:
                init_maps.append(line.split(marker, 1)[1].split('"', 1)[0])
            continue
        if not line or line.startswith("#"):
            continue
        segments.append(line)
    return {"init_maps": init_maps, "segments": segments}


def _master_playlist_path(movpkg: Path) -> Path:
    boot = _parse_xml(movpkg / "boot.xml")
    data_item = boot.find(".//{*}DataItem[{*}Role='Master']")
    if data_item is None:
        raise ValueError(f"No master playlist DataItem in {movpkg / 'boot.xml'}")
    data_path = data_item.findtext("{*}DataPath")
    if not data_path:
        raise ValueError("Master playlist DataItem has no DataPath")
    data_dir = boot.find(".//{*}DataItems")
    directory = data_dir.attrib.get("Directory", "Data") if data_dir is not None else "Data"
    return movpkg / directory / data_path


def _boot_streams(movpkg: Path) -> list[dict[str, str]]:
    boot = _parse_xml(movpkg / "boot.xml")
    streams = []
    for stream in boot.findall(".//{*}Streams/{*}Stream"):
        stream_id = stream.attrib.get("ID")
        path = stream.attrib.get("Path")
        network_url = stream.attrib.get("NetworkURL", "")
        complete = stream.findtext("{*}Complete")
        if not stream_id or not path:
            continue
        if complete and complete.upper() != "YES":
            continue
        streams.append({"id": stream_id, "path": path, "network_url": network_url})
    if not streams:
        raise ValueError(f"No complete streams found in {movpkg / 'boot.xml'}")
    return streams


def _parse_stream_info(stream_dir: Path) -> dict[str, object]:
    info = _parse_xml(stream_dir / "StreamInfoBoot.xml")
    playlist_rel = info.findtext(".//{*}MediaPlaylist/{*}PathToLocalCopy")
    if not playlist_rel:
        raise ValueError(f"No local media playlist in {stream_dir / 'StreamInfoBoot.xml'}")
    fragments = []
    for element in info.findall(".//{*}MediaInitializationSegments/{*}ISEG"):
        fragments.append(_fragment_row(element))
    for element in sorted(
        info.findall(".//{*}MediaSegments/{*}SEG"),
        key=lambda e: int(e.attrib.get("SeqNum", "0")),
    ):
        fragments.append(_fragment_row(element))
    media_bytes = int(info.findtext("{*}MediaBytesStored") or "0")
    return {
        "playlist": stream_dir / playlist_rel,
        "fragments": fragments,
        "media_bytes_stored": media_bytes,
    }


def _fragment_row(element: ET.Element) -> dict[str, object]:
    path = element.attrib.get("PATH")
    if not path:
        raise ValueError("StreamInfo fragment is missing PATH")
    return {
        "path": path,
        "len": int(element.attrib.get("Len", "0")),
        "off": int(element.attrib.get("Off", "0")),
    }


def _segment_uri_from_playlist(path: Path) -> str:
    text = _read_playlist(path)
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        return line
    raise ValueError(f"No segment URI found in {path}")


def _read_playlist(path: Path) -> str:
    return path.read_text(errors="replace").rstrip("\x00\r\n") + "\n"


def _url_basename(url: str) -> str | None:
    parsed = urlparse(url)
    if not parsed.path:
        return None
    return Path(parsed.path).name


def _parse_xml(path: Path) -> ET.Element:
    return ET.fromstring(path.read_text(encoding="utf-8"))
