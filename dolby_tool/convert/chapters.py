"""Embed a named chapter list into an existing MP4 via ffmpeg's ffmetadata.

We write a tiny ffmetadata file and run `ffmpeg -i in.mp4 -i chapters.ffmeta
-map_metadata 1 -map_chapters 1 -c copy -movflags +faststart out.mp4` to a
sibling temp file, then replace the original. Stream payloads are copied
bit-exactly — the only thing that changes is the chapter atom set.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from .metadata.chapterdb import Chapter


def write_ffmetadata(chapters: list[Chapter], path: Path, duration_ms: int) -> None:
    """Write an ffmetadata v1 file with one [CHAPTER] block per entry."""
    lines = [";FFMETADATA1"]
    for i, ch in enumerate(chapters):
        start = ch.timestamp_ms
        end = chapters[i + 1].timestamp_ms if i + 1 < len(chapters) else duration_ms
        if end <= start:
            end = start + 1
        lines.append("[CHAPTER]")
        lines.append("TIMEBASE=1/1000")
        lines.append(f"START={start}")
        lines.append(f"END={end}")
        lines.append(f"title={ch.name}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def embed(target_mp4: Path, chapters: list[Chapter], duration_ms: int) -> dict[str, object]:
    """Embed `chapters` into `target_mp4` in place via an ffmpeg remux."""
    if not chapters:
        return {"applied": False, "reason": "no chapters"}

    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        meta = tmp / "chapters.ffmeta"
        write_ffmetadata(chapters, meta, duration_ms)

        out = tmp / target_mp4.name
        cmd = [
            "ffmpeg", "-hide_banner", "-y",
            "-i", str(target_mp4),
            "-i", str(meta),
            "-map_metadata", "1", "-map_chapters", "1",
            "-c", "copy",
            "-movflags", "+faststart",
            str(out),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            return {
                "applied": False,
                "reason": f"ffmpeg exit {r.returncode}",
                "stderr_tail": r.stderr.splitlines()[-5:],
            }
        out.replace(target_mp4)

    return {"applied": True, "count": len(chapters)}
