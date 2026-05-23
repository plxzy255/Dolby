"""MKV → Apple-TV-compatible .m4v stream-copy mux via ffmpeg.

Design: do as little as possible during mux. We `-c copy` video and audio so
HEVC/H.264 + AC-3/EAC-3/AC-4 passthrough is bit-exact; text subtitles are
converted to `mov_text` (the only sub codec MP4 natively supports), and PGS
bitmap subtitles are stripped here and re-injected by `subs_pgs.py` in a
second pass. After mux, `atoms.py` patches the boxes ffmpeg gets wrong/leaves
off so TV.app lights up DV / Atmos as predicted by reports/01_gate_model.md.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Codec families we recognise during stream selection / reporting.
_TEXT_SUB_CODECS = {"subrip", "ass", "ssa", "mov_text", "webvtt", "text"}
_BITMAP_SUB_CODECS = {"hdmv_pgs_subtitle", "dvb_subtitle", "dvd_subtitle"}


@dataclass
class StreamInfo:
    index: int
    codec: str
    codec_type: str
    language: str | None = None
    title: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProbeResult:
    video: StreamInfo
    audios: list[StreamInfo]
    text_subs: list[StreamInfo]
    bitmap_subs: list[StreamInfo]
    has_chapters: bool
    raw: dict[str, Any]

    def all_subs(self) -> list[StreamInfo]:
        return self.text_subs + self.bitmap_subs


def probe(source: Path) -> ProbeResult:
    """Run ffprobe and classify streams."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_streams", "-show_chapters", "-show_format",
        "-of", "json", str(source),
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    raw = json.loads(result.stdout or "{}")

    video: StreamInfo | None = None
    audios: list[StreamInfo] = []
    text_subs: list[StreamInfo] = []
    bitmap_subs: list[StreamInfo] = []
    for s in raw.get("streams", []):
        info = StreamInfo(
            index=int(s["index"]),
            codec=s.get("codec_name", ""),
            codec_type=s.get("codec_type", ""),
            language=(s.get("tags") or {}).get("language"),
            title=(s.get("tags") or {}).get("title"),
            raw=s,
        )
        if info.codec_type == "video" and video is None and info.codec != "mjpeg":
            video = info
        elif info.codec_type == "audio":
            audios.append(info)
        elif info.codec_type == "subtitle":
            if info.codec in _BITMAP_SUB_CODECS:
                bitmap_subs.append(info)
            else:
                text_subs.append(info)
    if video is None:
        raise ValueError(f"No video stream found in {source}")
    return ProbeResult(
        video=video,
        audios=audios,
        text_subs=text_subs,
        bitmap_subs=bitmap_subs,
        has_chapters=bool(raw.get("chapters")),
        raw=raw,
    )


def _default_audio_index(audios: list[StreamInfo]) -> int:
    """First English track wins; otherwise the first track."""
    for i, a in enumerate(audios):
        if (a.language or "").lower() in ("eng", "en"):
            return i
    return 0


def mux(
    source: Path,
    output: Path,
    *,
    overwrite: bool = False,
    include_bitmap_subs_as_passthrough: bool = False,
) -> dict[str, Any]:
    """Run the ffmpeg passthrough mux and return a summary dict.

    `include_bitmap_subs_as_passthrough=True` keeps PGS as a raw stream in the
    MP4 (broken on TV.app, fine on Infuse/VLC). Default: drop them — the
    PGS→VobSub step in `subs_pgs.py` re-adds them in a second pass.
    """
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found on PATH")
    if shutil.which("ffprobe") is None:
        raise RuntimeError("ffprobe not found on PATH")

    source = source.expanduser().resolve()
    output = output.expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"Input does not exist: {source}")
    if output.exists() and not overwrite:
        raise ValueError(f"Output already exists (pass overwrite=True): {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    info = probe(source)
    default_audio = _default_audio_index(info.audios)

    cmd: list[str] = [
        "ffmpeg", "-hide_banner",
        "-y" if overwrite else "-n",
        # Tolerate partial/truncated MKVs: drop corrupt frames rather than abort.
        "-fflags", "+discardcorrupt+genpts",
        "-err_detect", "ignore_err",
        "-i", str(source),
        "-map", f"0:v:{_video_pos(info)}",
    ]

    # All audio tracks, in source order.
    for i, _ in enumerate(info.audios):
        cmd += ["-map", f"0:a:{i}"]

    # Map subtitles by absolute input stream index so codec-class splitting
    # doesn't reorder them (a `0:s:N` index refers to subtitle-only ordering
    # in the input — using the original absolute index avoids the ambiguity
    # entirely and lets us set per-output-stream codec choices below).
    sub_codecs: list[str] = []  # codec per output subtitle stream, in order
    for s in info.text_subs:
        cmd += ["-map", f"0:{s.index}?"]
        sub_codecs.append("mov_text")
    if include_bitmap_subs_as_passthrough:
        for s in info.bitmap_subs:
            cmd += ["-map", f"0:{s.index}?"]
            sub_codecs.append("copy")

    cmd += ["-c:v", "copy", "-c:a", "copy"]
    for i, codec in enumerate(sub_codecs):
        cmd += [f"-c:s:{i}", codec]

    # Default audio track flag
    if info.audios:
        for i, _ in enumerate(info.audios):
            flag = "default" if i == default_audio else "0"
            cmd += [f"-disposition:a:{i}", flag]

    if info.has_chapters:
        cmd += ["-map_chapters", "0"]

    cmd += [
        "-movflags", "+faststart+use_metadata_tags",
        "-f", "mp4",
        str(output),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Bubble up stderr so callers can see why it failed.
        raise RuntimeError(
            f"ffmpeg mux failed (exit {result.returncode}):\n"
            f"  cmd: {' '.join(cmd)}\n"
            f"  stderr tail:\n{_tail(result.stderr, 40)}"
        )

    return {
        "source": str(source),
        "output": str(output),
        "video_codec": info.video.codec,
        "audio_streams": [{"codec": a.codec, "language": a.language} for a in info.audios],
        "default_audio_index": default_audio,
        "text_subs_included": len(info.text_subs),
        "bitmap_subs_dropped": 0 if include_bitmap_subs_as_passthrough else len(info.bitmap_subs),
        "chapters": info.has_chapters,
        "ffmpeg_stderr_tail": result.stderr.splitlines()[-20:],
    }


def _video_pos(info: ProbeResult) -> int:
    """Position of the chosen video stream within the input's video streams."""
    video_streams = [s for s in info.raw.get("streams", []) if s.get("codec_type") == "video"]
    for i, s in enumerate(video_streams):
        if int(s["index"]) == info.video.index:
            return i
    return 0


def _tail(text: str, n: int) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-n:])
