# dolby-tool

A local web app for inspecting Dolby Vision / HDR / Atmos files, comparing quality across multiple files, and live-capturing playback specs from macOS TV.app.

## Why

Apple TV.app silently falls back from Dolby Vision to plain HDR10 when an MP4's video sample-entry FourCC is `hvc1` instead of `dvh1`/`dvhe`, even when a valid `dvvC` configuration box is present. Diagnosing this requires juggling `ffprobe`, `log stream` predicates, and bitstream side-data — this tool puts it all behind a browser UI.

## Requirements

- macOS (uses `log stream` and `osascript`)
- Python 3.10+
- `ffmpeg` / `ffprobe` (`brew install ffmpeg`)
- *(Optional)* `mediainfo` for richer Atmos detection (`brew install mediainfo`)

## Run

```bash
cd /Users/psp/Development/Dolby/dolby-tool
./dolby-tool
```

First run creates a venv and installs FastAPI + uvicorn. Subsequent runs reuse it. The browser opens at <http://localhost:7878>.

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

## Project layout

```
dolby-tool/
  dolby_tool/
    __main__.py     # entrypoint
    server.py       # FastAPI app + WebSocket
    inspect.py      # ffprobe → structured spec
    compare.py      # diff/rank logic
    tvlog.py        # log stream subprocess + parser
    web/
      index.html
      app.js
      styles.css
  requirements.txt
  dolby-tool        # bash launcher
  README.md
```

## Notes

- File uploads are intentionally disabled — videos are too large. The tool works on file paths, which you can drag in from Finder or pick via the native macOS file picker.
- `log stream` will likely prompt for permission on first capture; macOS may ask for Developer Tools or similar entitlements.
- The TV.app file detection (the "I just played something, what was it?") works *retroactively* — you start capture, then play, then stop. There's no continuous mode by default.
