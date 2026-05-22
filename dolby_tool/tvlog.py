"""macOS `log stream` wrapper that captures TV.app playback events and parses them.

Usage from server:

    capture = LogCapture()
    capture.start()              # spawns `log stream` subprocess
    ...                          # events stream into capture.events
    summary = capture.stop()     # collapses the buffer into a structured summary

`events` is a list[dict]. Each dict has `kind`, `raw`, `ts`, plus parsed fields.

The predicate targets the four processes that emit useful playback telemetry on macOS:
mediaplaybackd, VTDecoderXPCService, coremediaxpc, audiomxd — covering both HLS
streaming (Apple TV+) and FigFilePlayer (local library) paths.
"""
from __future__ import annotations

import asyncio
import re
import signal
import subprocess
import threading
import time
from typing import Any

PREDICATE = (
    'process == "mediaplaybackd"'
    ' OR process == "VTDecoderXPCService"'
    ' OR process == "coremediaxpc"'
    ' OR process == "audiomxd"'
    ' OR process == "TV"'
)


# ---------------------------------------------------------------------------
# regexes — kept loose, errors of omission are fine, errors of commission are not


# FigAlternate(504) [Peak/Avg 30570719/24765202] [3840x1606] [dvh1.05.06,ec-3]
# [VideoRange PQ] [HDCP Type1] [FrameRate 23.976]
RE_FIG_ALT = re.compile(
    r"FigAlternate\((?P<id>\d+)\)"
    r"(?:\s*\[Peak/Avg\s+(?P<peak>\d+)/(?P<avg>\d+)\])?"
    r"(?:\s*\[(?P<width>\d+)x(?P<height>\d+)\])?"
    r"(?:\s*\[(?P<codecs>[^\]]+)\])?"
    r"(?:\s*\[VideoRange\s+(?P<range>\w+)\])?"
    r"(?:\s*\[HDCP\s+(?P<hdcp>[^\]]+)\])?"
    r"(?:\s*\[FrameRate\s+(?P<fps>[\d.]+)\])?"
)

# Normalized/compact capture output may only preserve the variant resolution.
# HLS_VARIANT nullxnull
RE_HLS_VARIANT_SUMMARY = re.compile(
    r"HLS_VARIANT\s+(?P<width>\d+|null)x(?P<height>\d+|null)",
    re.IGNORECASE,
)

# CodecType: dvh1 (HW decoder), DecodedPixelBuffer: &xv0, 3840 x 1600
# CODEC_TYPE qdh1 (HW decoder)
RE_CODEC_TYPE = re.compile(
    r"(?:CodecType:\s*|CODEC_TYPE\s+)(?P<fourcc>\w+)"
    r"(?:\s*\((?P<decoder>[^)]+)\))?"
    r"(?:[^,]*?,\s*(?P<width>\d+)\s*x\s*(?P<height>\d+))?"
)

# codecType: HEVC, encryptionScheme N, W x H
# FILE_PLAYER HEVC enc=4 3840x1606
RE_FILE_PLAYER = re.compile(
    r"(?:codecType:\s*|FILE_PLAYER\s+)(?P<codec>\w+)"
    r"(?:,\s*encryptionScheme\s+|\s+enc=)?(?P<enc>\d+)?"
    r"(?:,\s*|\s+)?(?P<width>\d+)?\s*x?\s*(?P<height>\d+)?",
    re.IGNORECASE,
)

# [AudioFormat ec+3] [AudioChannels 16] [SampleRate 48000] [Spatialization Eligible yes] [Spatialization yes]
# AUDIO_FORMAT qc+3 is decodable ch=16
RE_AUDIO_FORMAT = re.compile(
    r"(?:"
    r"\[AudioFormat\s+(?P<bracket_format>[^\]]+)\]"
    r"(?:\s*\[AudioChannels\s+(?P<bracket_channels>\d+)\])?"
    r"(?:\s*\[SampleRate\s+(?P<bracket_rate>\d+)\])?"
    r"(?:\s*\[Spatialization\s+Eligible\s+(?P<bracket_spat_elig>\w+)\])?"
    r"(?:\s*\[Spatialization\s+(?P<bracket_spat>\w+)\])?"
    r"|"
    r"AUDIO_FORMAT\s+(?P<summary_format>\S+)"
    r"(?:\s+is\s+(?P<summary_decodable>decodable|not decodable))?"
    r"(?:\s+ch=(?P<summary_channels>\d+))?"
    r")",
    re.IGNORECASE,
)

# luma depth 10 chroma format 1
# LUMA_CHROMA luma=10 chroma=1
RE_LUMA = re.compile(
    r"(?:luma depth\s+|LUMA_CHROMA\s+luma=)(?P<luma>\d+)"
    r".*?(?:chroma format\s+|chroma=)(?P<chroma>\d+)",
    re.IGNORECASE,
)


def _parse_line(line: str) -> dict[str, Any] | None:
    if m := RE_FIG_ALT.search(line):
        d = m.groupdict()
        return {
            "kind": "hls_variant",
            "raw": line.rstrip(),
            "id": _int(d["id"]),
            "peak_bps": _int(d["peak"]),
            "avg_bps": _int(d["avg"]),
            "width": _int(d["width"]),
            "height": _int(d["height"]),
            "codecs": d["codecs"],
            "video_range": d["range"],
            "hdcp": d["hdcp"],
            "fps": _float(d["fps"]),
        }
    if m := RE_HLS_VARIANT_SUMMARY.search(line):
        d = m.groupdict()
        return {
            "kind": "hls_variant",
            "raw": line.rstrip(),
            "id": None,
            "peak_bps": None,
            "avg_bps": None,
            "width": _int(d["width"]),
            "height": _int(d["height"]),
            "codecs": None,
            "video_range": None,
            "hdcp": None,
            "fps": None,
        }
    if m := RE_CODEC_TYPE.search(line):
        d = m.groupdict()
        return {
            "kind": "codec_type",
            "raw": line.rstrip(),
            "fourcc": d["fourcc"],
            "decoder": d["decoder"],
            "width": _int(d["width"]),
            "height": _int(d["height"]),
        }
    if m := RE_AUDIO_FORMAT.search(line):
        d = m.groupdict()
        fmt = d["bracket_format"] or d["summary_format"]
        channels = d["bracket_channels"] or d["summary_channels"]
        return {
            "kind": "audio_format",
            "raw": line.rstrip(),
            "format": fmt,
            "channels": _int(channels),
            "sample_rate": _int(d["bracket_rate"]),
            "spatialization_eligible": d["bracket_spat_elig"],
            "spatialization": d["bracket_spat"],
            "decodable": d["summary_decodable"] == "decodable" if d["summary_decodable"] else None,
        }
    if m := RE_FILE_PLAYER.search(line):
        d = m.groupdict()
        if d["codec"]:
            return {
                "kind": "file_player",
                "raw": line.rstrip(),
                "codec": d["codec"],
                "encryption_scheme": _int(d["enc"]),
                "width": _int(d["width"]),
                "height": _int(d["height"]),
            }
    if m := RE_LUMA.search(line):
        d = m.groupdict()
        return {
            "kind": "luma_chroma",
            "raw": line.rstrip(),
            "luma_depth": _int(d["luma"]),
            "chroma_format": _int(d["chroma"]),
        }
    return None


def _int(v: Any) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------


class LogCapture:
    """Spawns `log stream` and accumulates parsed events until stopped."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self._proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._stop = threading.Event()
        self._started_at: float | None = None
        self._listeners: list[asyncio.Queue] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    # -- lifecycle ---------------------------------------------------------

    def start(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        if self._proc is not None:
            return
        self._loop = loop
        self._started_at = time.time()
        self._proc = subprocess.Popen(
            [
                "log",
                "stream",
                "--info",
                "--debug",
                "--style",
                "compact",
                "--predicate",
                PREDICATE,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        proc = self._proc
        if proc and proc.poll() is None:
            try:
                proc.send_signal(signal.SIGINT)
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        if self._reader and self._reader.is_alive():
            self._reader.join(timeout=2)
        self._proc = None
        self._reader = None
        return self.summarize()

    # -- subscription ------------------------------------------------------

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._listeners.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._listeners:
            self._listeners.remove(q)

    # -- reader thread -----------------------------------------------------

    def _read_loop(self) -> None:
        proc = self._proc
        if not proc or not proc.stdout:
            return
        for line in proc.stdout:
            if self._stop.is_set():
                break
            event = _parse_line(line)
            if not event:
                continue
            event["ts"] = time.time()
            self.events.append(event)
            self._broadcast(event)

    def _broadcast(self, event: dict[str, Any]) -> None:
        loop = self._loop
        for q in list(self._listeners):
            if loop and loop.is_running():
                try:
                    loop.call_soon_threadsafe(q.put_nowait, event)
                except (RuntimeError, asyncio.QueueFull):
                    pass

    # -- summary -----------------------------------------------------------

    def summarize(self) -> dict[str, Any]:
        if not self.events:
            return {
                "started_at": self._started_at,
                "duration_s": time.time() - self._started_at if self._started_at else 0,
                "event_count": 0,
                "playback": None,
                "events": [],
                "predicate": PREDICATE,
            }

        # Pick the last HLS variant (final ABR rung) if any
        hls_variants = [e for e in self.events if e["kind"] == "hls_variant"]
        last_variant = hls_variants[-1] if hls_variants else None

        codec_events = [e for e in self.events if e["kind"] == "codec_type"]
        last_codec = codec_events[-1] if codec_events else None

        audio_events = [e for e in self.events if e["kind"] == "audio_format"]
        last_audio = audio_events[-1] if audio_events else None

        file_events = [e for e in self.events if e["kind"] == "file_player"]
        last_file = file_events[-1] if file_events else None

        playback: dict[str, Any] = {
            "source": "hls" if hls_variants else ("local_file" if file_events else "unknown"),
        }
        if last_variant:
            playback["hls_variant"] = last_variant
            # parse codecs string e.g. "dvh1.05.06,ec-3"
            codecs = (last_variant.get("codecs") or "").split(",")
            playback["video_fourcc"] = codecs[0].split(".")[0] if codecs and codecs[0] else None
            playback["audio_codec"] = codecs[1] if len(codecs) > 1 else None
            playback["peak_mbps"] = (
                round(last_variant["peak_bps"] / 1_000_000, 2)
                if last_variant.get("peak_bps")
                else None
            )
            playback["avg_mbps"] = (
                round(last_variant["avg_bps"] / 1_000_000, 2)
                if last_variant.get("avg_bps")
                else None
            )
        if last_codec:
            playback["decoded_fourcc"] = last_codec.get("fourcc")
            playback["decoder"] = last_codec.get("decoder")
            if last_codec.get("width"):
                playback["decoded_resolution"] = (
                    f"{last_codec['width']}x{last_codec['height']}"
                )
        if last_audio:
            audio_format = (last_audio.get("format") or "").lower()
            is_known_atmos = audio_format in {"ec+3", "ec-3", "ec3"} and last_audio.get("spatialization") == "yes"
            playback["audio"] = {
                "format": last_audio.get("format"),
                "channels": last_audio.get("channels"),
                "sample_rate": last_audio.get("sample_rate"),
                "spatialization": last_audio.get("spatialization"),
                "spatialization_eligible": last_audio.get("spatialization_eligible"),
                "decodable": last_audio.get("decodable"),
                "is_atmos": is_known_atmos,
            }
            if audio_format == "qc+3":
                playback["audio"]["diagnosis"] = (
                    "Audio format 'qc+3' was reported as decodable by TV.app. "
                    "Preserving it as an unknown Dolby-like Apple/QuickTime path, not confirmed Atmos."
                )
        if last_file:
            playback["file_player"] = last_file

        # DV verdict
        decoded = (playback.get("decoded_fourcc") or "").lower()
        if decoded in {"dvh1", "dvhe"}:
            playback["dolby_vision_active"] = True
        elif decoded == "hvc1" and playback.get("source") == "local_file":
            playback["dolby_vision_active"] = False
            playback["dv_diagnosis"] = (
                "Local file decoded as 'hvc1' — TV.app did NOT engage DV pipeline. "
                "Re-tag sample-entry to 'dvh1' to fix."
            )
        elif decoded == "qdh1":
            playback["dolby_vision_active"] = None
            playback["dv_label"] = "Possibly DV / Apple private HDR path"
            playback["dv_diagnosis"] = (
                "Decoded as 'qdh1' via hardware decoder. This is not the known hvc1 fallback, "
                "but it is also not the standard dvh1/dvhe Dolby Vision marker. Treat as an "
                "Apple/QuickTime private HDR/DV-like path until correlated with display output."
            )
        else:
            playback["dolby_vision_active"] = None

        return {
            "started_at": self._started_at,
            "duration_s": time.time() - self._started_at if self._started_at else 0,
            "event_count": len(self.events),
            "playback": playback,
            "events": self.events,
            "predicate": PREDICATE,
        }


__all__ = ["LogCapture", "PREDICATE"]
