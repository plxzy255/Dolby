"""Round-trip tests for storefront / ratings lookups and filename guessing.

No network — these only exercise the JSON data + parsing code.
"""
from __future__ import annotations

import pytest

from dolby_tool.convert.cli import guess_query
from dolby_tool.convert.metadata import ratings, storefronts


def test_us_storefront() -> None:
    s = storefronts.resolve("US")
    assert s.store_code == 143441
    assert s.locale.startswith("en")


def test_gb_storefront_with_language() -> None:
    s = storefronts.resolve("GB", "en")
    assert s.store_code == 143444
    assert s.locale == "en_GB"


def test_au_storefront_known_code() -> None:
    assert storefronts.resolve("AU").store_code == 143460


def test_unknown_country_raises() -> None:
    with pytest.raises(KeyError):
        storefronts.resolve("ZZ")


def test_us_movie_pg13_rating() -> None:
    r = ratings.lookup(143441, ratings.MEDIA_MOVIE, "PG-13")
    assert r is not None
    assert r.prefix == "mpaa"
    assert r.itunes_value == "300"
    assert r.itunes_extc() == "mpaa|PG-13|300|"


def test_unknown_rating_returns_none() -> None:
    assert ratings.lookup(143441, ratings.MEDIA_MOVIE, "NOPE") is None


def test_guess_query_tv_show() -> None:
    kind, title, season, episode = guess_query("Severance.S02E03.1080p.mkv")
    assert kind == "tvShow"
    assert title == "Severance"
    assert season == 2
    assert episode == 3


def test_guess_query_movie_with_year() -> None:
    kind, title, season, episode = guess_query("Dune.Part.Two.2024.2160p.HDR.mkv")
    assert kind == "movie"
    assert title.startswith("Dune")
    assert season is None and episode is None


# --- chapterdb parsing -------------------------------------------------------

from pathlib import Path
import tempfile

from dolby_tool.convert import chapters as chapters_mod
from dolby_tool.convert.metadata import chapterdb


_SAMPLE_SEARCH_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<results xmlns="http://jvance.com/2008/ChapterGrabber">
  <chapterInfo confirmations="42">
    <title>Test Movie</title>
    <source><duration>02:10:30.000</duration></source>
    <ref><chapterSetId>12345</chapterSetId></ref>
    <chapters>
      <chapter time="00:00:00.000" name="Opening"/>
      <chapter time="00:10:15.500" name="Chapter Two"/>
      <chapter time="00:25:00.000" name="Climax"/>
    </chapters>
  </chapterInfo>
</results>
"""


def test_chapterdb_time_parsing() -> None:
    assert chapterdb._time_to_ms("00:00:00.000") == 0
    assert chapterdb._time_to_ms("00:01:00.000") == 60_000
    assert chapterdb._time_to_ms("01:00:00.500") == 3_600_500
    assert chapterdb._time_to_ms("00:00:00,250") == 250
    assert chapterdb._time_to_ms("garbage") == 0


def test_chapterdb_full_parse() -> None:
    sets = chapterdb._parse_full(_SAMPLE_SEARCH_XML)
    assert len(sets) == 1
    s = sets[0]
    assert s.set_id == 12345
    assert s.title == "Test Movie"
    assert s.confirmations == 42
    assert s.duration_ms == 2 * 3600_000 + 10 * 60_000 + 30_000
    assert [c.name for c in s.chapters] == ["Opening", "Chapter Two", "Climax"]
    assert [c.timestamp_ms for c in s.chapters] == [0, 615_500, 1_500_000]


def test_ffmetadata_writer() -> None:
    chs = [
        chapterdb.Chapter(name="Intro", timestamp_ms=0),
        chapterdb.Chapter(name="Middle", timestamp_ms=60_000),
        chapterdb.Chapter(name="End", timestamp_ms=120_000),
    ]
    with tempfile.TemporaryDirectory() as tmp_s:
        p = Path(tmp_s) / "c.ffmeta"
        chapters_mod.write_ffmetadata(chs, p, duration_ms=180_000)
        text = p.read_text()
    assert text.startswith(";FFMETADATA1")
    assert text.count("[CHAPTER]") == 3
    assert "TIMEBASE=1/1000" in text
    assert "title=Intro" in text
    assert "END=180000" in text  # last chapter clamps to duration
