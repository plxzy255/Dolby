# Paths explored

Grouped by category. Each path lists the goal, the result, and what it
falsifies/confirms. Captures are in `/Users/psp/Development/Dolby/captures/`.

## A. Apple-managed `.movpkg`

### A1. Streaming Apple TV+ HLS (online)
- **Result:** works. `Desert Lands` (Prehistoric Planet) on the same
  account/route as the failing local file produced `qc+3 ch=16` and
  `is rendering spatial audio = true`.
- **Confirms:** TV.app's spatial path is reachable on this hardware/account
  when the asset is online HLS.

### A2. Downloaded `.movpkg` playback (offline)
- Tested: Prehistoric Planet `Grass Lands`, Ted Lasso `The Hope That Kills You`.
- **Result:** both packages have complete top-level main video and
  complete stereo audio. Neither had a `Complete=YES` top-level main
  Atmos. `Grass Lands` manifest advertised
  `audio-atmos_download-ap-aoc.tv.apple.com` but
  `Complete=NO, MediaBytesStored=0`. Playback resolved to the stereo
  group.
- **Falsifies:** "Highest Quality download settings download Atmos audio
  for any Apple TV+ Atmos title." Either this account/region/title combo
  does not persist Atmos locally, or only some titles do.
- **`dolby-tool movpkg` and `movpkg-scan`** automate this inventory check.

### A3. Externally built `.movpkg` via `AVAssetDownloadTask`
- Built a valid persisted-HLS `.movpkg` from a local source, validated
  `boot.xml`, `HLSMoviePackageType=PersistedStore`, segments,
  `kMDItemContentType=com.apple.tv.movpkg`.
- Tried opening via Finder double-click, `open`, `open -b com.apple.TV`,
  `osascript`, TV.app auto-add folder.
- **Result:** 0 events captured; TV.app shows no playback.
- **Falsifies:** "TV.app accepts any structurally-valid `.movpkg`."
  TV.app's handler requires Apple-issued content identity / library
  membership that an external package does not carry.

## B. Local HLS in non-TV.app players

### B1. QuickTime + locally-served HLS (the working path)
- `dolby-tool hls-package <local file> <folder>` stream-copies fMP4 HLS;
  `dolby-tool hls-serve <folder> --open quicktime` opens it via a
  Range-capable localhost server.
- **Result:** QuickTime engages `FigStreamPlayer`, selects the Atmos HLS
  group, decodes `ec+3` 16ch, forces a 7.1.4 Atmos decoder, configures
  `AUSpatialMixerV2` with `Atmos_7_1_4`.
- **Confirms:** locally-sourced HLS Atmos works under a non-TV.app Apple
  process. The HLS engine and the SpatialMgr layer both accept it.
- Caveat: Python `http.server` does not handle Range; needed a
  Range-capable server. FFmpeg's bare split fMP4 master failed with
  `-12927` until `hls-package` started adding `CODECS`, `VIDEO-RANGE`,
  `FRAME-RATE`, and `CHANNELS="6/JOC"` tags.

### B2. Safari + locally-served HLS
- Direct `master.m3u8` navigation and a same-origin `<video src=...>` page.
- **Result:** Safari created failed-page tabs and made no media segment
  requests. 0 playback events.
- **State:** unproven — this is a launch / page-load failure, not a
  spatialization result. Retry with HTTPS and a user-gesture autoplay
  page has not been done.

### B3. TV.app live-stream URL schemes (`itls://`, `itlss://`, `itvls://`, `itvlss://`)
- Tried against `http://127.0.0.1:8765/master.m3u8`.
- **Result:** TV.app opens, player state = stopped, 0 events, no
  localhost fetches.
- **Falsifies for plain HLS URLs:** these schemes likely need provider
  authentication tokens or a specific protocol header.

### B4. `open -b com.apple.TV http://localhost/master.m3u8`
- **Result:** TV.app does not advertise ownership of generic
  `http`/`https` HLS. No playback events, no localhost fetches.

## C. TV.app local-file variants

### C1. Container remuxes
- MP4 faststart, M4V, MOV (180s lossless clips from the same `Blood and
  Bone.mp4` source).
- **Result:** all play as `local_file` / FigFilePlayer with `ec+3 ch=16`,
  active lower-level Atmos, `app_spatial_rendering_ever_true = false`.
  MP4/M4V kept `dvh1`; MOV exposed `hev1`.
- **Falsifies:** "the gate is the container brand or the video sample
  entry." None of MP4 brand, M4V, MOV, `dvh1` vs `hev1` flips the flag.

### C2. Library import vs direct open
- Direct-open captures and library-style runs both go through the same
  FigFilePlayer + `ec+3` + app-false pattern.
- **Falsifies:** "library import changes the renderer."

### C3. Audio re-tag / channel layout / default-track flags
- Not tested in isolation, but the dtrace findings make this irrelevant:
  TV.app's `mpc_updateAVAudioSpatializationFormatsForPlayerAudioFormat:`
  call site does not consult these fields. Listed for completeness only.

## D. SpatialProbe (Swift AVPlayer harness)

`harness/Sources/SpatialProbe/main.swift`, ~100 lines. Loads
`AVURLAsset`, sets
`item.allowedAudioSpatializationFormats = .monoStereoAndMultichannel`
(0x3), plays. dtrace + log stream in parallel.

- **Run A (wired headset):** route reports `not capable of spatialization`,
  `maxSpatializableChannels = 0`, `spatialAudioSources = ['?src']`. JOC
  decoder stays in `ec-3` 6ch passthrough. Mixer rejects 6ch ec-3.
- **Run B (MBP built-in speakers):** route reports `built-in speakers`,
  `maxSpatializableChannels = 16`, `spatialAudioSources = ['mlti']`. JOC
  decoder switches to `ec+3` 16ch. Mixer accepts. SpatialMgr posts
  `spatialization = 1`.
- **Decisive:** Issue 12 is TV.app-specific, not macOS / hardware / file.

## E. dtrace gate probing

Single session, 25–30s per side. Probes on `pid$target` for:

- `FigPlayer{Stream,File}CreateWithOptions` (engine entry)
- `FPSupport_GetAudioFormatDescriptionSpatializationEligibility`
- `AVCFPlayerItemSetAllowedAudioSpatializationFormats` /
  `playerItem_SetAllowedAudioSpatializationFormats`
- `-[AVPlayerItem _updateAllowedAudioSpatializationFormatsFromFigItem]`
- `AudioQueueObject::{CheckSpatialization,AllowsSpatialization}`
- `ShouldRouteBypassSpatialization`
- `SpatializationManager::EnableInternalSpatializationAUs`
- `MEMixerChannel::ConfigureSpatializationUnit` / `...UnitFormat`

Aggregate divergence (30s captures):

| Function | local | hls |
|---|---|---|
| `FPSupport_GetAudioFormatDescriptionSpatializationEligibility` | 4 | 8 |
| `AudioQueueObject::CheckSpatialization` | 1 | 4 |
| `AudioQueueObject::ResetSpatializationCompression` | 4 | 8 |
| `MEMixerChannel::ConfigureSpatializerHost` | 6 | 8 |
| `MEMixerChannel::StoreSpatializationPreset` | 1 | 4 |
| `SpatializationManager::EnableInternalSpatializationAUs` | 1 | 4 |
| `ShouldRouteBypassSpatialization` | 17 | 29 |

HLS engages the AU pipeline 4x (matches the
`spatial_rendering_changed_count: 4` from earlier captures). Local
engages it 1x and never recurses.

## F. Routes tested

- MBP built-in speakers (M-series): spatial-capable in SpatialMgr
- JBL Tune 720BT wired: not capable
- JBL Tune 720BT Bluetooth: not capable
- **Untested:** AirPods (any generation), Beats, HDMI/AVR, USB-C DAC,
  external speakers via Aggregate Device, AirPlay receivers
