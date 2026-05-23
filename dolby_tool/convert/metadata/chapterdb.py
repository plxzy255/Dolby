"""ChapterDB (chapterdb.plex.tv) client.

Direct port of Subler's `ChapterDB.swift`. Returns named chapter sets
matched by title + (optionally) movie duration. Output gets embedded by
`chapters.embed()` via an ffmpeg remux pass with an ffmetadata file.

API:
  GET  https://chapterdb.plex.tv/chapters/search?title=<urlencoded>
  GET  https://chapterdb.plex.tv/chapters/<chapterSetId>
  Header: ApiKey: <key>   (Subler's public key 7WXY7WRDFBT33L1UX7OO now
                            returns 401 — endpoint is effectively
                            deprecated as of 2026-05. Set the
                            DOLBY_CHAPTERDB_API_KEY env var to override
                            with a working private key.)

Both endpoints return XML in the http://jvance.com/2008/ChapterGrabber
namespace.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from urllib.parse import quote
from xml.etree import ElementTree as ET

import httpx

_BASE = "https://chapterdb.plex.tv/chapters/"
_DEFAULT_API_KEY = "7WXY7WRDFBT33L1UX7OO"
_API_KEY = os.environ.get("DOLBY_CHAPTERDB_API_KEY", _DEFAULT_API_KEY)
_NS = "{http://jvance.com/2008/ChapterGrabber}"
# Match a duration result within ±20s of the input duration (Subler default).
_DURATION_DELTA_MS = 20_000


@dataclass
class Chapter:
    name: str
    timestamp_ms: int


@dataclass
class ChapterSet:
    set_id: int
    title: str
    duration_ms: int
    confirmations: int
    chapters: list[Chapter] = field(default_factory=list)


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=20.0,
        follow_redirects=True,
        headers={"ApiKey": _API_KEY, "User-Agent": "dolby-tool/0.1"},
    )


def _time_to_ms(s: str) -> int:
    """Parse 'HH:MM:SS.fff' (or similar) → milliseconds."""
    m = re.match(r"^(\d+):(\d{1,2}):(\d{1,2})(?:[.,](\d{1,6}))?$", s.strip())
    if not m:
        return 0
    h, mi, se, frac = m.groups()
    ms = int(h) * 3600_000 + int(mi) * 60_000 + int(se) * 1000
    if frac:
        ms += int((frac + "000")[:3])
    return ms


def search(title: str, duration_ms: int = 0) -> list[ChapterSet]:
    """Search ChapterDB; filter to sets near the source duration when known."""
    url = f"{_BASE}search?title={quote(title, safe='')}"
    with _client() as c:
        r = c.get(url)
        if r.status_code != 200 or not r.content:
            return []
        sets = _parse_search(r.content)
        # Hydrate each result with its chapter list (Subler does the same —
        # search response only carries metadata, not the chapter times).
        full: list[ChapterSet] = []
        for s in sets:
            r2 = c.get(f"{_BASE}{s.set_id}")
            if r2.status_code != 200:
                continue
            hydrated = _parse_full(r2.content)
            if hydrated and hydrated[0].chapters:
                # Keep the search metadata (duration/title/confirmations) but
                # take the chapter list from the detail fetch.
                s.chapters = hydrated[0].chapters
                full.append(s)

    if duration_ms <= 0:
        return full

    near = [s for s in full
            if abs(s.duration_ms - duration_ms) <= _DURATION_DELTA_MS]
    if near:
        return near
    # Fallback: sets whose last chapter lands before our duration (Subler logic)
    less = [s for s in full
            if s.chapters and s.chapters[-1].timestamp_ms < duration_ms]
    return less or full


def _parse_search(data: bytes) -> list[ChapterSet]:
    out: list[ChapterSet] = []
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return []
    for info in root.iter(f"{_NS}chapterInfo"):
        s = _info_to_set(info)
        if s is not None:
            out.append(s)
    return out


def _parse_full(data: bytes) -> list[ChapterSet]:
    sets = _parse_search(data)
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return sets
    # Walk each chapterInfo and attach chapters in document order.
    for s, info in zip(sets, root.iter(f"{_NS}chapterInfo"), strict=False):
        chapters: list[Chapter] = []
        last_ts = -1
        for ch in info.iterfind(f".//{_NS}chapter"):
            time = ch.get("time", "")
            name = ch.get("name", "") or f"Chapter {len(chapters) + 1}"
            ts = _time_to_ms(time)
            if ts < last_ts:
                # ChapterDB occasionally has non-monotonic dupes; stop there.
                break
            last_ts = ts
            chapters.append(Chapter(name=name, timestamp_ms=ts))
        s.chapters = chapters
    return sets


def _info_to_set(info: ET.Element) -> ChapterSet | None:
    title_el = info.find(f"{_NS}title")
    dur_el = info.find(f"{_NS}source/{_NS}duration")
    ref_id_el = info.find(f"{_NS}ref/{_NS}chapterSetId")
    confs = info.get("confirmations") or "0"
    if title_el is None or dur_el is None or ref_id_el is None:
        return None
    try:
        set_id = int((ref_id_el.text or "").strip())
    except ValueError:
        return None
    return ChapterSet(
        set_id=set_id,
        title=(title_el.text or "").strip(),
        duration_ms=_time_to_ms(dur_el.text or ""),
        confirmations=int(confs) if confs.isdigit() else 0,
    )
