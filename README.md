# dolby-tool

A local web app for inspecting Dolby Vision / HDR / Atmos files, comparing quality across multiple files, and live-capturing playback specs from macOS TV.app.

## Why

Apple TV.app silently falls back from Dolby Vision to plain HDR10 when an MP4's video sample-entry FourCC is `hvc1` instead of `dvh1`/`dvhe`, even when a valid `dvvC` configuration box is present. Diagnosing this requires juggling `ffprobe`, `log stream` predicates, and bitstream side-data — this tool puts it all behind a browser UI.

## Requirements

- macOS (uses `log stream` and `osascript`)
- Python 3.14+ (managed automatically by [uv](https://docs.astral.sh/uv/))
- `ffmpeg` / `ffprobe` (`brew install ffmpeg`)
- *(Optional)* `mediainfo` for richer Atmos detection (`brew install mediainfo`)

## Run

```bash
./dolby-tool          # start server + open Safari at http://localhost:7878
./dolby-tool stop     # kill the running instance
```

[uv](https://docs.astral.sh/uv/) is required — install with:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

First run syncs the venv and installs dependencies automatically. Subsequent runs reuse it.

## Tabs

### Inspect
Drag a file from Finder onto the dropzone (or paste an absolute path, or click Browse). The app runs `ffprobe` plus a single-frame side-data probe and renders:
- Dolby Vision profile (5 / 7 / 8.1 / 8.2 / 8.4 / 4) with BL compatibility ID
- HDR10 mastering display + content light level
- HDR10+ dynamic metadata presence
- Sample-entry FourCC (with a red warning if `hvc1` is used on a DV file — that's the TV.app-breaking bug)
- Audio streams: codec, channels, layout, bitrate, Atmos detection
- Subtitle tracks: language, title, default/forced/SDH dispositions
- Container bitrate, duration, resolution, fps, color primaries/transfer/space

### Compare
Add multiple files to the comparison. The table highlights the winner per dimension and assigns each file an overall score. Useful for picking the best release among multiple rips or seeing if a swap into your TV library is an upgrade or downgrade.

### TV Capture
Click **Start Capture**, play something in TV.app, click **Stop**. The app runs `log stream` with predicates tuned for `mediaplaybackd`, `VTDecoderXPCService`, `coremediaxpc`, and `audiomxd`, parses out `FigAlternate` / `FigFilePlayer` / `CodecType` / `AudioFormat` events, and shows a structured summary of what was actually playing — DV profile, HW decoder FourCC, audio format, channel count, spatialization, peak/average bitrate.

The default capture remains TV.app-focused. The parser also recognizes saved
QuickTime/Safari raw-log evidence for local-player controls, including
FigStreamPlayer, CoreAudio `ec+3` input, forced 7.1.4 Atmos decode, and
`AUSpatialMixerV2` Atmos layouts.

For saved raw logs or non-TV.app local-player controls:

```bash
uv run python -m dolby_tool tvlog-parse captures/alt_paths/example.log
uv run python -m dolby_tool tvlog-capture --profile local-player --seconds 60
```

### Local HLS Serve
Serve a prepared HLS folder with byte-range support for QuickTime/Safari tests:

```bash
uv run python -m dolby_tool hls-serve .tmp/alt_hls --open quicktime
```

This is intentionally loopback-only by default. Use it for local-player
controls where Python's basic `http.server` is not sufficient because the
player requests `Range: bytes=...` media segments.

### `.movpkg` Inventory
For downloaded TV.app packages, inspect local HLS manifests and stream inventories:

```bash
uv run python -m dolby_tool movpkg "/path/to/Episode.movpkg" \
  --selected-group audio-stereo-128_download-ap-aoc.tv.apple.com
```

This reports audio groups, codecs, roles/accessibility flags, `Complete` state,
local byte/segment counts, and an inventory verdict such as
`movpkg_atmos_variant_missing_or_incomplete`.

## Project layout

```
dolby_tool/
  __main__.py     # entrypoint
  server.py       # FastAPI app + WebSocket
  inspect.py      # ffprobe → structured spec
  compare.py      # diff/rank logic
  tvlog.py        # log stream subprocess + parser
  movpkg.py       # downloaded .movpkg inventory parser
  local_hls.py    # Range-capable local HLS server
  web/
    index.html
    app.js
    styles.css
pyproject.toml
uv.lock
dolby-tool        # bash launcher
README.md
```

## Notes

- File uploads are intentionally disabled — videos are too large. The tool works on file paths, which you can drag in from Finder or pick via the native macOS file picker.
- Drag-and-drop resolves paths via Spotlight first; falls back to `find(1)` searching `/Volumes` and common dirs (covers external drives Spotlight skips).
- `log stream` will likely prompt for permission on first capture; macOS may ask for Developer Tools or similar entitlements.
- The TV.app file detection works *retroactively* — start capture, play in TV.app, then stop.
