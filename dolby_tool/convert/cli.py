"""CLI dispatch helpers for `dolby-tool convert` and `dolby-tool tag`.

Wired from `dolby_tool/__main__.py`. Kept thin: argparse + glue.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import atoms, mux, subs_pgs
from .metadata import apple_tv, storefronts, tagger


_TV_RE = re.compile(r"(?P<show>.+?)[. _-]*[sS](?P<s>\d{1,2})[eE](?P<e>\d{1,3})")
_YEAR_RE = re.compile(r"(?P<title>.+?)[. _(]+(?P<year>(19|20)\d{2})")
# Apple-TV / Subler layout: ".../TV Shows/<Show>/Season N/EE Title.ext"
_SEASON_DIR_RE = re.compile(r"^(?:Season|Sezon|Series|Staffel)[\s_]*(\d{1,2})$", re.IGNORECASE)
_EP_PREFIX_RE = re.compile(r"^(?P<ep>\d{1,3})[\s._-]+(?P<title>.+)$")


def guess_query(filename: str | Path) -> tuple[str, str, int | None, int | None]:
    """Heuristic title/year/season/episode guess from a filename (or path).

    Returns (kind, title, season, episode) where kind is "movie" or "tvShow".
    Path is preferred over bare filename so we can pick up the
    `…/<Show>/Season N/EE Title.ext` library layout.
    """
    p = Path(filename)
    stem = p.stem
    tv = _TV_RE.search(stem)
    if tv:
        return ("tvShow", _clean(tv.group("show")), int(tv.group("s")), int(tv.group("e")))

    # Library-layout fallback: parent directory matches "Season N", episode
    # number is the leading digits of the filename, show name is the dir above.
    parents = list(p.resolve().parents) if str(p).startswith("/") else list(p.parents)
    if parents:
        season_match = _SEASON_DIR_RE.match(parents[0].name)
        ep_match = _EP_PREFIX_RE.match(stem)
        if season_match and ep_match and len(parents) >= 2:
            return (
                "tvShow",
                _clean(parents[1].name),
                int(season_match.group(1)),
                int(ep_match.group("ep")),
            )

    yr = _YEAR_RE.search(stem)
    if yr:
        return ("movie", _clean(yr.group("title")), None, None)
    return ("movie", _clean(stem), None, None)


def _clean(s: str) -> str:
    return re.sub(r"[._]+", " ", s).strip()


def _pick_interactive(prompt: str, options: list[str]) -> int | None:
    print(prompt, file=sys.stderr)
    for i, opt in enumerate(options, start=1):
        print(f"  {i}. {opt}", file=sys.stderr)
    print("  -. skip metadata", file=sys.stderr)
    try:
        raw = input("Pick: ").strip()
    except EOFError:
        return None
    if raw in ("", "-", "0"):
        return None
    try:
        idx = int(raw) - 1
        if 0 <= idx < len(options):
            return idx
    except ValueError:
        pass
    return None


def resolve_metadata(
    source_name: str,
    *,
    storefront: str,
    language: str | None,
    content_id: str | None,
    interactive: bool,
    show_override: str | None = None,
    season_override: int | None = None,
    episode_override: int | None = None,
) -> apple_tv.Metadata | None:
    store = storefronts.resolve(storefront, language)
    kind, title, season, episode = guess_query(source_name)
    if show_override:
        kind, title = "tvShow", show_override
    if season_override is not None:
        season, kind = season_override, "tvShow"
    if episode_override is not None:
        episode, kind = episode_override, "tvShow"

    if content_id:
        # Direct fetch path
        fake_hit = apple_tv.SearchHit(
            id=content_id, type=("Show" if kind == "tvShow" else "Movie"),
            title=None, description=None, release_date_ms=None,
            images={}, roles_summary=None, rating_display=None, raw={},
        )
        if kind == "tvShow" and season is not None and episode is not None:
            return apple_tv.fetch_episode(fake_hit, season, episode, store)
        return apple_tv.fetch_movie(fake_hit, store)

    if kind == "tvShow":
        hits = apple_tv.search_shows(title, store)
    else:
        hits = apple_tv.search_movies(title, store)

    if not hits:
        print(f"No Apple TV matches for {title!r} ({storefront}).", file=sys.stderr)
        return None

    if interactive:
        labels = [
            f"{(h.title or '?')} ({h.year or '?'}) — id={h.id}"
            for h in hits[:8]
        ]
        idx = _pick_interactive(f"Apple TV results for {title!r}:", labels)
        if idx is None:
            return None
        chosen = hits[idx]
    else:
        chosen = hits[0]

    if kind == "tvShow" and season is not None and episode is not None:
        return apple_tv.fetch_episode(chosen, season, episode, store)
    return apple_tv.fetch_movie(chosen, store)


def main_convert(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="dolby-tool convert")
    parser.add_argument("input", help="Source media file (MKV, MP4, etc.).")
    parser.add_argument("output", help="Output .m4v path.")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--no-metadata", action="store_true", help="Skip Apple TV metadata lookup.")
    parser.add_argument("--metadata-id", help="Apple TV content id (skip search).")
    parser.add_argument("--storefront", default="US", help="Country code (US, GB, AU, ...).")
    parser.add_argument("--language", default=None, help="Locale, e.g. en_US.")
    parser.add_argument("--non-interactive", action="store_true", help="Auto-pick top metadata hit.")
    parser.add_argument("--show", help="Override show name (forces TV mode).")
    parser.add_argument("--season", type=int, help="Override season number.")
    parser.add_argument("--episode", type=int, help="Override episode number.")
    parser.add_argument("--skip-pgs", action="store_true", help="Don't try PGS→VobSub conversion.")
    parser.add_argument(
        "--patch-colr",
        action="store_true",
        help="After mux, ensure video colr is nclx (same-size patch only).",
    )
    parser.add_argument(
        "--patch-dec3-joc",
        action="store_true",
        help="After mux, force EAC-3 dec3 JOC flag bit (Atmos hint for TV.app).",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    src = Path(args.input).expanduser().resolve()
    dst = Path(args.output).expanduser().resolve()

    summary: dict[str, object] = {"input": str(src), "output": str(dst)}
    summary["mux"] = mux.mux(src, dst, overwrite=args.overwrite)

    # PGS pass (re-mux source bitmap subs as VobSub into a sibling .m4v)
    if not args.skip_pgs:
        info = mux.probe(src)
        if info.bitmap_subs:
            pgs_out = dst.with_suffix(".pgs.m4v")
            r = subs_pgs.convert_and_remux(src, dst, info.bitmap_subs, output=pgs_out)
            summary["pgs"] = {
                "converted": r.converted, "skipped": r.skipped, "reason": r.reason,
                "output": str(pgs_out) if r.converted else None,
            }
            if r.converted:
                pgs_out.replace(dst)

    if args.patch_colr:
        # Defaults: BT.709 / SDR (1,1,1) full-range off — caller should override per source.
        summary["colr_patched"] = atoms.patch_colr_nclx(dst, 1, 1, 1, False)
    if args.patch_dec3_joc:
        summary["dec3_joc_patched"] = atoms.patch_dec3_joc(dst)

    if not args.no_metadata:
        meta = resolve_metadata(
            str(src),
            storefront=args.storefront,
            language=args.language,
            content_id=args.metadata_id,
            interactive=not args.non_interactive and sys.stdin.isatty(),
            show_override=args.show,
            season_override=args.season,
            episode_override=args.episode,
        )
        if meta is not None:
            summary["metadata"] = tagger.apply(dst, meta)
            summary["matched_title"] = meta.title
        else:
            summary["metadata"] = {"applied": False, "reason": "no match / skipped"}

    _print_summary(summary, as_json=args.json)


def main_tag(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="dolby-tool tag")
    parser.add_argument("file", help="Existing .m4v/.mp4 to tag in place.")
    parser.add_argument("--metadata-id", help="Apple TV content id.")
    parser.add_argument("--storefront", default="US")
    parser.add_argument("--language", default=None)
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--show", help="Override show name (forces TV mode).")
    parser.add_argument("--season", type=int, help="Override season number.")
    parser.add_argument("--episode", type=int, help="Override episode number.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    path = Path(args.file).expanduser().resolve()
    meta = resolve_metadata(
        str(path),
        storefront=args.storefront,
        language=args.language,
        content_id=args.metadata_id,
        interactive=not args.non_interactive and sys.stdin.isatty(),
        show_override=args.show,
        season_override=args.season,
        episode_override=args.episode,
    )
    summary: dict[str, object] = {"file": str(path)}
    if meta is None:
        summary["metadata"] = {"applied": False, "reason": "no match / skipped"}
    else:
        summary["matched_title"] = meta.title
        summary["metadata"] = tagger.apply(path, meta)
    _print_summary(summary, as_json=args.json)


def _print_summary(summary: dict[str, object], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(summary, indent=2, sort_keys=True, default=str))
        return
    print(f"# convert summary\n")
    for k, v in summary.items():
        print(f"- **{k}**: `{v}`")
