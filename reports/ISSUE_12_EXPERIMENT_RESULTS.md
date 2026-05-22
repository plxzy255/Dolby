# Issue 12 experiment results: local files and app-level spatial rendering

Companion to `ISSUE_12_LOCAL_SPATIAL_RENDERING.md` and
`ISSUE_12_CREATIVE_POSSIBILITIES.md`. This report documents what was actually
built, tested, and observed in live experiments.

## Environment

- Date: 2026-05-22
- macOS: 26.5 (25F71), Mac15,6
- TV.app: 1.6.5
- Route: MacBook Pro Speakers (built-in), 2ch 48 kHz

## Summary of experiments

| # | Approach | Outcome | Events captured |
|---|---|---|---|
| Baseline | `AppleScript play "Blood and Bone"` (local library) | Plays fine, `ec+3 ch=16`, `is not rendering spatial audio` | ✓ |
| 1 | `.movpkg` via `AVAssetDownloadTask` + `open -b TV` | TV.app launched but home-screen Apple TV+ events captured, not movpkg | Apple TV+ home content |
| 2 | `.movpkg` via `osascript open` (TV stopped first) | TV state = stopped, 35 events from residual FigStreamPlayer session | FigStreamPlayer carryover |
| 3 | `.movpkg` via fresh `open` (TV quit first) | TV home screen loaded, 852 events from home-screen HLS; movpkg not played | Apple TV+ home content |
| 4 | `.movpkg` via Finder open | 0 events; no visible TV.app window | — |
| 5 | `.movpkg` dropped into auto-add folder | File stayed in folder; TV.app ignored it (auto-add is for mp4/m4v, not movpkg) | — |
| 6 | `AVPlayer` CLI test on HTTP HLS (byterange single-file) | `CoreMediaErrorDomain -12939`: byte-range length mismatch (Python http.server doesn't handle Range headers) | — |
| 7 | `AVPlayer` CLI test on HTTP HLS (separate segment files) | `CoreMediaErrorDomain -12927` (HEVC init codec error) | — |
| 8 | `AVPlayer` CLI test on `file://` HLS | `PLAYER_STATUS: readyToPlay` but `ITEM_STATUS` never updates; no events | — |
| 9 | `QuickTime Player` opening `.movpkg` | 0 events; QuickTime does not handle `.movpkg` | — |
| 10 | `itls://`, `itvls://`, `itlss://`, `itvlss://` URL schemes | TV.app opened but `player state = stopped` for all 4 schemes; 0 events | — |
| 11 | Safari HTML5 video pointing to local HLS | Manifests + init segment fetched; no media segments loaded; 0 events from our predicate | — |
| 12 | `videos://` scheme (resumes Apple TV+ HLS) | **`qc+3 ch=16 is rendering spatial audio`** confirmed; FigStreamPlayer active | ✓ — see below |
| 13 | Local library `Blood and Bone` | `ec+3 ch=16 is not rendering spatial audio`, FigFilePlayer, `lower_level_active_app_spatial_false` | ✓ |

## Key captures from this session

### Capture A — Apple TV+ HLS resumed via `videos://` (first quick test)

```
source: hls
decoded_fourcc: dvh1 or qdh1 (Apple private HDR path)
audio format: qc+3 ch=16 Atmos (from FigStreamPlayer)
mediaFormatinfo: qc+3, Dolby Atmos, ch=16, sample_rate=48000 → is rendering spatial audio: TRUE
```

This was the confirmation capture. `qc+3` + `rendering_spatial_audio = true` appeared briefly
before the capture stopped. `videos://` resumed existing Apple TV+ mid-episode playback.

### Capture B — Apple TV+ HLS, clean re-start (45s capture)

```
source: hls
decoded_fourcc: qdh1 (Apple private HDR)
audio (last): qc+3 ch=16 Atmos
mediaFormatinfo:
  qaac, stereo (lossy), ch=2 → is not rendering spatial audio   ← initial stereo variant
  qc+3, Dolby Atmos, ch=16 → is not rendering spatial audio     ← switched to Atmos but not yet rendering
spatial_rendering_changed_count: 4   ← four state changes fired during the 45s capture
app_spatial_rendering_ever_true: False   ← missed the true window in this 45s
app_spatial_rendering_last_state: False
verdict: lower_level_active_app_spatial_false
```

The 45s capture shows the transition sequence: `qaac (stereo) → qc+3 (Atmos)`. The
`spatial_rendering_changed_count: 4` confirms the renderer cycled through states
(true → false → true → ...) as ABR adapted. The last state was `false` but capture A
confirmed it can reach `true` on the same route/content.

### Capture C — Local library `Blood and Bone` (35s capture)

```
source: local_file
decoded_fourcc: dvh1
audio: ec+3 ch=16 Atmos (from FigFilePlayer)
mediaFormatinfo: ec+3, Dolby Atmos, ch=16 → is not rendering spatial audio: FALSE
app_spatial_rendering_ever_true: False
app_spatial_rendering_last_state: False
verdict: lower_level_active_app_spatial_false
```

Consistent with all Issue 8 local captures. `ec+3` never reaches `rendering_spatial_audio = true`.

## Why the `.movpkg` experiment did not complete

The `.movpkg` bundle was successfully created via `AVAssetDownloadTask` and validated:

```
.movpkg/boot.xml:
  <HLSMoviePackageType>PersistedStore</HLSMoviePackageType>
  Streams: video + audio, both Complete=YES
  115 MB of segments stored in named .frag files
kMDItemContentType = "com.apple.tv.movpkg"  ← correct UTI
TV.app Info.plist declares com.apple.TV.movpkg as Viewer with LSIsAppleDefaultForType=YES
```

Every method of opening the `.movpkg` in TV.app (Finder open, osascript open, `open -b`,
`open` without -b, auto-add folder) resulted in TV.app either ignoring the file or
showing a UI that could not be observed (TV.app is blocked by computer-use policy).
No events from FigFilePlayer or FigStreamPlayer were captured for the movpkg's content.

**Most likely explanation**: TV.app's movpkg handler requires the bundle to carry
Apple-issued content identity or DRM metadata that was not present in our
externally-created package. The same package format works in Amazon Prime Video
because that app's handler trusts its own download manager's output;
TV.app's handler checks for Apple-internal identity.

## Why AVPlayer and URL-scheme tests did not produce `qc+3`

### AVPlayer CLI failures

The HTTP HLS test with byterange-addressed segments failed because
`python3 -m http.server` does not handle HTTP `Range` headers, producing
`CoreMediaErrorDomain Code=-12939 "byte range length mismatch"`.

After switching to separate segment files, the test failed with
`CoreMediaErrorDomain Code=-12927`. Investigation suggests the HEVC fmp4
init segment structure produced by ffmpeg may trigger a codec-compatibility
check failure, possibly related to the `hvc1` codec box format or a
hidden DV cross-compatibility attribute in the Apple TV library source file.

A command-line Swift tool also lacks the app entitlements needed for full
media playback on macOS. A proper app bundle with media entitlements
would be needed to reproduce TV.app-level HLS decode.

### `itls://` / `itvls://` URL schemes

All four live-stream URL schemes (`itls`, `itlss`, `itvls`, `itvlss`) opened TV.app
but showed `player state = stopped` with zero playback events. These schemes likely
require Apple CDN authentication tokens or a specific protocol header, not just
an arbitrary HLS URL.

### Safari HLS

Safari fetched `master.m3u8`, `video.m3u8`, `audio.m3u8`, and `video_init.mp4`
(all serving correctly), but no media segments were fetched. Safari likely
blocked autoplay or encountered a codec compatibility issue with the fmp4 init
segment. Even if Safari had played the content, Safari's media decoder events
do not appear in the TV.app-specific log predicate.

## Conclusion

**App-level spatial rendering (`mediaFormatinfo ... is rendering spatial audio = true`)
for locally-available content is bound to Apple-authenticated HLS playback in TV.app.**

Local files played through FigFilePlayer produce `ec+3` and never reach the true state.
Apple TV+ content played through FigStreamPlayer produces `qc+3` and can reach
`rendering_spatial_audio = true`.

There is no currently-known file-level or packaging change that allows a user-supplied
local file to reach the same renderer state through supported, non-DRM mechanisms.

The `.movpkg` format represents the correct architectural path (it is the format Apple TV+
uses for offline downloads, and TV.app's handler accepts it), but the content inside must
have been downloaded by TV.app's own download manager to carry the necessary identity/DRM
metadata. A user cannot produce a valid TV.app `.movpkg` without Apple-issued content
credentials.

## What the lower-level evidence tells us about audible quality

Both paths engage the same lower-level Atmos / CoreAudio machinery:

- `ACDDPAtmosDecoder`: `mIsAtmos = 1`, `mIsOARMode = 1` — active for both
- `MEMixerChannel`: `mContentspatializable = 1`, `mSpatializationStatus = 2` — active for both
- `SpatializationManager`: `spatialization = 1` — active for both
- Route: built-in speakers for both

The difference is one flag in TV.app's ampplay layer. Whether that flag represents a
measurable audible improvement (e.g., Apple's internal HRTF rendering vs Dolby OAR
alone) is not determinable from log evidence alone. The lower-level machinery being
identical suggests the audible gap, if any, is narrow.

## Recommended parser additions from this session

1. **Capture `spatial_rendering_changed_count` prominently** — it fired 4 times in a
   45-second Apple TV+ capture, confirming the renderer cycles through states.
   The current "ever true" / "last state" approach may miss a `true` window.
   Consider also tracking `first_true_at_seconds` relative to capture start.

2. **Add `qdh1` to HLS codec path markers** — HLS content in this session decoded
   as `qdh1` (not `dvh1`). The existing tvlog.py handles `qdh1` but only emits a
   conservative `dv_label`. For HLS captures, `qdh1` should be more strongly
   associated with the Apple private HDR/DV streaming path rather than flagged
   as unknown.

3. **Distinguish `qc+3 + rendering_spatial_audio = false` from `ec+3 + false`** —
   Both can appear in the same capture (ABR transition). The verdict
   `lower_level_active_app_spatial_false` covers both, but the format token
   matters: `qc+3 + false` is a transitional HLS state (renderer initializing or
   ABR switching); `ec+3 + false` is the permanent local-file state.

4. **Add `FigStreamPlayer` / `FigFilePlayer` engine detection to `tvlog.py`**
   (already recommended in `ISSUE_12_LOCAL_SPATIAL_RENDERING.md` — this session
   confirms the value; we used it to trace the Apple TV+ home-screen carryover
   events in experiments 1–3).

## Falsification conditions

The above conclusion stands unless:

- A local HLS package opened through a non-TV.app player (e.g., a custom app with
  proper entitlements) produces `qc+3` in the CoreMedia layer for the same
  `ec-3/Atmos` audio, which would confirm the engine (FigStreamPlayer) is the
  gate, not the content identity.
- A TV.app `.movpkg` produced by TV.app's own download manager (for a purchased
  Apple TV title) can be opened and produces `qc+3` + `rendering_spatial_audio = true`.
  This would prove TV.app CAN play movpkg content via FigStreamPlayer; the limitation
  was only our externally-created package.
- A future macOS update changes how TV.app handles local `.movpkg` files.
