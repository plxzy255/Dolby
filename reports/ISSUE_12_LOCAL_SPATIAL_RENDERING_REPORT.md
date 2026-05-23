# Issue 12: Can local TV.app files activate app-level spatial rendering?

## Environment

- Date: 2026-05-22
- macOS: 26.5 (25F71)
- Mac model: Mac15,6
- TV.app: 1.6.5
- Primary route: MacBook Pro Speakers, 2 channels, 48000 Hz, built-in
- Evidence reviewed:
  - Apple HLS control captures from Issue #8
  - local TV.app captures from Issue #8 and follow-up direct-open/library-style runs
  - QuickTime Player local-file control log: `quicktime-local-interesting.txt`

## Short conclusion

No TV.app local-file capture observed so far has reached:

```text
mediaFormatinfo ... is rendering spatial audio = true
```

The TV.app evidence still supports this working model:

- Apple TV+ / HLS can use **FigStreamPlayer**, expose runtime/asbd audio as `qc+3`, and reach app-level `mediaFormatinfo ... is rendering spatial audio`.
- TV.app local-file playback uses **FigFilePlayer**, exposes runtime/asbd audio as `ec+3`, and remains at app-level `mediaFormatinfo ... is not rendering spatial audio`.
- The tested local file still reaches Atmos/OAR/lower-level spatial machinery; it is not plain stereo and is not simply failing Atmos decode.

The new QuickTime Player control does **not** falsify the FigFilePlayer/ec+3 model. QuickTime also uses **FigFilePlayer** and `ec+3`, not FigStreamPlayer or `qc+3`. However, QuickTime logs show stronger explicit lower-level CoreAudio spatialization than TV.app local summaries, including `AudioQueue ... spatialization enabled, client-controlled` and `AUSpatialMixerV2 ... spatialization algorithm = 7`.

A later QuickTime Player local-HLS control does change the non-TV.app ranking:
when the same local Atmos source was repackaged as HLS and served over a
Range-capable localhost server, QuickTime used **FigStreamPlayer**, selected
an Atmos HLS audio group, decoded `ec+3` 16ch, forced a 7.1.4 Atmos decoder,
and initialized `AUSpatialMixerV2` with `Atmos_7_1_4`. This is not TV.app
local playback, but it is a stronger Apple-native local alternative than the
plain QuickTime local-file path.

That means the safest current conclusion is:

> Local files can engage Apple/CoreAudio Atmos and spatialization machinery, especially in QuickTime Player, but the specific TV.app app-level `mediaFormatinfo ... is rendering spatial audio` flag has only been observed on the HLS/qc+3 path so far.

This should still be treated as a strong working hypothesis, not a final impossibility proof. Local HLS packaging, MOV/M4V remuxes, and other file-authoring variants remain useful falsification tests.

## Direct evidence

### TV.app local capture, FigFilePlayer path

```text
TV[...] [com.apple.coremedia:player] <<<< FigFilePlayer >>>>
    itemfig_ReportAudioPlaybackThroughFigLog: ...
    [AudioFormat ec+3] [AudioChannels 16] [Spatialization Eligible yes]
    [Client permits multi: yes, stereo: no] [Spatialization yes]
    [StereoSpatialization no] [item requires immersive rendering no]
TV[...] [com.apple.TV:ampplay] play> cm>> mediaFormatinfo ...
    asbdFormatID = ec+3, Dolby Atmos, asbdNumChannels = 16,
    asbdSampleRate = 48.0 kHz, is not rendering spatial audio
```

### Apple HLS capture, FigStreamPlayer path

```text
TV[...] [com.apple.coremedia:player] <<<< FigStreamPlayer >>>>
    fpfs_ReportAudioPlaybackThroughFigLog: ...
    [AudioFormat qc+3 is decodable] [AudioChannels 16]
    [Spatialization Eligible yes] ...
TV[...] [com.apple.TV:ampplay] play> cm>> mediaFormatinfo ...
    asbdFormatID = qc+3, Dolby Atmos, asbdNumChannels = 16,
    asbdSampleRate = 48.0 kHz, is rendering spatial audio
```

### QuickTime Player local-file control

QuickTime did not switch the local file to FigStreamPlayer or `qc+3`. It stayed on FigFilePlayer / `ec+3`:

```text
QuickTime Player[...] [com.apple.coremedia:player] <<<< FigFilePlayer >>>>
    FigPlayerFileCreateWithOptions: returning player(...)
QuickTime Player[...] [com.apple.coremedia:] <<<< FAQ >>>>
    Creating AudioQueue with format:'ec+3', framesPerPacket:1536, sampleRate:48000
QuickTime Player[...] AudioQueueNewOutput 16 ch, 48000 Hz, ec+3
```

But it also showed substantial lower-level spatial processing:

```text
ACDDPAtmosDecoder.cpp ... subType = 'ec+3'
ACDDPAtmosDecoder.cpp ... mIsAtmos = 1, mIsOARMode = 1
AudioQueueObject.cpp ... SetProperty: ... spatialization enabled, client-controlled.
AUSpatialMixerV2 ... spatialization algorithm = 7
subaq_buildCAAudioQueue ... Created new AudioQueue ... [LayoutTag: ... Channels: 16, ... Spatialization]
```

The QuickTime log does not contain a TV.app-style `mediaFormatinfo ... is rendering spatial audio` confirmation, but it does show that Apple local-file playback can enable CoreAudio spatialization components without using `qc+3`.

## Working hypothesis

The current hypothesis is now slightly refined:

```text
Apple HLS asset, best observed path
  -> FigStreamPlayer
  -> HLS source advertises ec-3 Atmos
  -> runtime/asbd label qc+3
  -> TV.app mediaFormatinfo rendering_spatial_audio = true

TV.app local file asset
  -> FigFilePlayer
  -> local/container E-AC-3 / Atmos
  -> runtime/asbd label ec+3
  -> TV.app mediaFormatinfo rendering_spatial_audio = false
  -> lower-level Atmos/OAR/spatial machinery still active

QuickTime local file asset
  -> FigFilePlayer
  -> local/container E-AC-3 / Atmos
  -> runtime/asbd label ec+3
  -> Atmos/OAR active
  -> AudioQueue/AUSpatialMixer spatialization active
  -> no observed qc+3 or TV.app mediaFormatinfo app-level flag

QuickTime local HLS asset
  -> FigStreamPlayer
  -> HLS source advertises ec-3 Atmos
  -> runtime/CoreAudio input label ec+3 16ch
  -> Atmos/OAR active
  -> AudioQueue forces 7.1.4 Atmos decoder
  -> AUSpatialMixerV2 uses Atmos_7_1_4 input layout
  -> no TV.app mediaFormatinfo app-level flag because this is not TV.app
```

Important nuance: not every HLS capture necessarily reaches `qc+3` / app-level rendering true. A prior HLS-like run showed FigStreamPlayer with runtime `ec+3` and app-level spatial rendering false. That suggests the strongest predictor is probably the runtime/asbd path (`qc+3` vs `ec+3`), not simply `HLS` vs `local`.

File-level variants are not expected to change TV.app behavior unless they make TV.app choose a different playback engine or expose a different asbdFormatID. That remains unproven until at least one local-HLS or remux/MOV/M4V variant test is run.

## Evidence table

| Variant | Route | Player engine | Source/runtime audio label | asbd / runtime format | App spatial rendering ever true | Lower-level spatial evidence | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Apple TV+ / HLS, best observed path | MacBook Pro Speakers | FigStreamPlayer | source `ec-3` / runtime `qc+3 ch=16` | `qc+3` | yes | SpatializationManager active; mIsAtmos=1, mIsOARMode=1; mixer `qc+3 ch=16` spatializable/status 2 | Reaches `mediaFormatinfo ... is rendering spatial audio` |
| HLS/streaming run with runtime `ec+3` | MacBook Pro Speakers | FigStreamPlayer | source `ec-3` / runtime `ec+3 ch=16` | `ec+3` | no | Lower-level Atmos/spatial evidence active | Shows HLS alone may not be enough; runtime/asbd token matters |
| TV.app local file, direct-open/library-style runs | MacBook Pro Speakers | FigFilePlayer | local E-AC-3 / runtime `ec+3 ch=16` | `ec+3` | no | SpatializationManager active; mIsAtmos=1, mIsOARMode=1; mixer `ec+3 ch=16` spatializable/status 2; `[item requires immersive rendering no]` | Stays at `mediaFormatinfo ... is not rendering spatial audio` |
| QuickTime Player local file control | MacBook Pro Speakers | FigFilePlayer | local E-AC-3 / runtime `ec+3 ch=16` | `ec+3` | n/a, no TV.app mediaFormatinfo line observed | mIsAtmos=1; mIsOARMode=1; AudioQueue spatialization enabled; AUSpatialMixerV2 algorithm 7; 16ch ec+3 AudioQueue | Does not unlock FigStreamPlayer/qc+3, but proves strong lower-level Apple spatial path for local playback |
| Local HLS packaging opened in QuickTime | MacBook Pro Speakers | FigStreamPlayer | HLS `ec-3` Atmos group / CoreAudio `ec+3 ch=16` input | `ec+3` | n/a, no TV.app mediaFormatinfo line observed | mIsAtmos=1; mIsOARMode=1; AudioQueue forced 7.1.4 Atmos decoder; AUSpatialMixerV2 `Atmos_7_1_4`; active byterange HLS playback | Strongest Apple-native local alternative so far, but not TV.app |
| Local HLS packaging opened in TV.app URL schemes | MacBook Pro Speakers | none observed | none | none | no events | none | `http`, `itls`, `itlss`, `itvls`, `itvlss` produced no localhost fetches or playback events |
| MOV/M4V/remux variants | MacBook Pro Speakers | FigFilePlayer | local E-AC-3 / runtime `ec+3 ch=16` | `ec+3` | no | mIsAtmos=1; mIsOARMode=1; AudioQueue forced 7.1.4 Atmos decoder; AUSpatialMixerV2 `Atmos_7_1_4`; lower-level spatial active | MP4 faststart, M4V, and MOV remux clips all stayed app-spatial false |

## Answers to the issue questions

1. **Can any local file played in TV.app produce `mediaFormatinfo ... rendering_spatial_audio = true` on MacBook Pro Speakers?**

   No observed TV.app local-file capture has done so. The tested local playback uses FigFilePlayer and `ec+3`, and every captured TV.app `mediaFormatinfo` line for that path reports `is not rendering spatial audio`.

2. **If yes, what properties trigger it?**

   Not answered. No local TV.app variant has triggered the app-level flag. Current evidence points to playback engine/asbd path rather than ordinary MP4 metadata.

3. **Is app-level spatial rendering restricted to Apple-managed playback?**

   Current evidence is consistent with this for TV.app's app-level `mediaFormatinfo` flag, but it is not final proof. The QuickTime control shows Apple local-file playback can still enable lower-level spatialization without the TV.app HLS/qc+3 flag.

4. **Does TV.app need specific local-file metadata?**

   No tested local-file metadata has flipped the flag. The plausible gating layer remains player engine/asbdFormatID. Remux/MOV/M4V variants remain untested.

5. **Library import vs direct open?**

   User's normal playback is library-style TV.app local playback, and direct-open/local TV.app captures show the same FigFilePlayer/ec+3/app-false pattern. No evidence so far that the library import path changes the app-level flag.

6. **Does remux / retag affect the flag?**

   Not yet tested live. The working prediction is no unless the remux/retag somehow changes TV.app's playback engine or runtime/asbd label.

7. **Is `mediaFormatinfo` truly the final renderer state?**

   It is a TV.app app-level / cmplayer state, not the entire CoreAudio truth. Local playback can have active Atmos decode, OAR mode, AudioQueue spatialization, AUSpatialMixer, mixer spatializable status, and SpatializationManager binding even when TV.app's `mediaFormatinfo` app-level flag is false or absent. The app-level flag should be treated as an important Apple TV.app renderer signal, not the only possible spatialization signal.

## Interpretation

- The `ec+3` vs `qc+3` distinction appears to be a CoreMedia engine/runtime distinction, not a simple codec-quality ranking.
- Saying `qc+3` is a higher-quality codec than `ec+3` would be misleading.
- The tested local file is not silently downgraded to plain stereo. Both TV.app local and QuickTime local show substantial Atmos/CoreAudio spatial evidence.
- QuickTime local playback may be more visibly spatialized at the CoreAudio level than the TV.app local summaries, but it still does not show FigStreamPlayer/qc+3.
- The missing TV.app-local signal remains the app-level `mediaFormatinfo ... is rendering spatial audio` confirmation.
- The current evidence is consistent with the TV.app HLS/qc+3 path having an extra app-level renderer state on built-in speakers. A final proof would require a successful local variant test that flips the flag, an audible/digital A/B method, or Apple-internal documentation.

## What was tested after the first report

- Multiple local TV.app direct-open/library-style runs on MacBook Pro Speakers:
  - all stayed `local_file` / `dvh1` / `ec+3 ch=16`
  - all kept `app_spatial_rendering_ever_true = false`
  - all kept lower-level Atmos/spatial evidence active
- QuickTime Player local-file control:
  - stayed FigFilePlayer / `ec+3`
  - did not show FigStreamPlayer or `qc+3`
  - showed `mIsAtmos = 1`, `mIsOARMode = 1`, `AudioQueue ... spatialization enabled`, and `AUSpatialMixerV2 ... spatialization algorithm = 7`
- QuickTime Player local-HLS control:
  - used FigStreamPlayer against `http://127.0.0.1:8765/master.m3u8`
  - selected `[AudioGroup atmos] [dvh1.05.06,ec-3]`
  - created an `ec+3` 16ch AudioQueue and forced a 7.1.4 Atmos decoder
  - initialized `AUSpatialMixerV2` with `Atmos_7_1_4`
  - reproduced end-to-end with merged tooling via `hls-prepare` ->
    `hls-serve` -> QuickTime -> `tvlog-capture --profile local-player`;
    the fresh capture reports `source=hls`, `pipeline_engine=FigStreamPlayer`,
    selected AudioGroup `atmos`, codec `ec-3`, current/best audio
    `ec+3 ch=16 48000 Hz spatialization=yes`, Atmos decoder active, OAR
    active, forced 7.1.4 Atmos, and AUSpatialMixer layouts
    `Atmos_7_1_4`, `Stereo`
- TV.app arbitrary local-HLS launch controls:
  - `http`, `itls`, `itlss`, `itvls`, and `itvlss` did not fetch from the
    localhost server and produced no playback events
- Safari local-HLS launch controls:
  - direct `master.m3u8` navigation and a minimal same-origin HTML
    `<video src="master.m3u8">` page created Safari failed-page tabs
  - `tvlog-capture --profile local-player` recorded 0 playback events
  - this is a launch/load failure, not evidence about Safari Atmos decode
    or spatialization behavior
- TV.app remux/container controls:
  - created 180s lossless clips from the same `Blood and Bone.mp4` source
    as MP4 faststart, M4V, and MOV
  - MP4 and M4V preserved `dvh1`; MOV remux exposed `hev1`
  - all three played as `local_file` / FigFilePlayer with `ec+3 ch=16`
  - all three kept lower-level Atmos/spatial evidence active but
    `app_spatial_rendering_ever_true = false`
- Direct local-file-to-HLS packaging control:
  - added `dolby-tool hls-package <input> <folder>` to stream-copy a
    normal local file into fMP4 HLS without requiring a pre-existing
    persisted-HLS `.movpkg`
  - default output uses a separate HLS audio group, closer to the
    Apple-managed HLS shape than a plain local MP4/M4V file
  - QuickTime rejected FFmpeg's bare split fMP4 master playlist with
    `CoreMediaErrorDomain error -12927`; the command now auto-adds the
    HLS tags that made QuickTime accept it: `CODECS`, `VIDEO-RANGE`,
    `FRAME-RATE`, and Atmos `CHANNELS="6/JOC"` when detected
  - clean capture of the auto-patched CLI output produced `source=hls`,
    FigStreamPlayer, AudioGroup `group_audio` classified as Atmos,
    `ec-3` source audio, runtime `ec+3 ch=16`, Atmos decoder active,
    OAR active, forced 7.1.4 Atmos, and `AUSpatialMixerV2`
    `Atmos_7_1_4` / `Stereo` layouts
  - intended workflow is `hls-package` -> `hls-serve --open quicktime` ->
    `tvlog-capture --profile local-player`
  - added `dolby-tool hls-package-capture <input> <folder>` to run the
    same workflow in the correct order: package, start the Range-capable
    server, start local-player capture, then open QuickTime. This avoids
    late captures that miss AudioQueue / Atmos decoder initialization.
  - wrapper validation:
    `captures/alt_paths/20260523_quicktime_hls_package_wrapper.json`
    reproduced FigStreamPlayer, Atmos HLS group, runtime `ec+3 ch=16`,
    lower-level spatialization, Atmos decoder, OAR, forced 7.1.4 Atmos,
    SpatialMgr source `mlti`, and AUSpatialMixer layouts
    `Atmos_7_1_4` / `Stereo`

## What remains to test

- Controlled listening A/B between TV.app local file, QuickTime local file, and
  QuickTime local HTTP HLS.
- Optional Safari follow-up only if the local HTTP page-load failure is
  solved first.
- Optional: Apple-managed downloaded/offline TV.app item, if available.
- Optional: non-Apple HLS Atmos source, if available.

## Recommended tool changes

These match the focus areas in #10, #6, #4 and add parser hooks from the QuickTime control.

### Parser additions in `dolby_tool/tvlog.py`

- Add a `pipeline_engine` field on parsed audio/player events derived from raw-line markers:
  - `FigFilePlayer` / `itemfig_ReportAudioPlaybackThroughFigLog` -> `pipeline_engine = "FigFilePlayer"`
  - `FigStreamPlayer` / `fpfs_ReportAudioPlaybackThroughFigLog` -> `pipeline_engine = "FigStreamPlayer"`
- Capture `[item requires immersive rendering yes|no]` as `immersive_rendering_requested`.
- Capture `AVCFPlayerItemSetAllowedAudioSpatializationFormats ... 0xN` as renderer hint `allowed_spatialization_formats_mask`.
- Capture `Stereo Spatialization allowed by default due to asset containing video.` as renderer hint `stereo_spatialization_default_reason`.
- Capture `spatialAudioSources = [ 'mlti' ]` and similar from `SpatializationManager` as `spatial_audio_source_tokens`.
- Consider a future QuickTime/Safari capture mode that includes process-specific evidence outside TV.app:
  - `AudioQueueObject ... spatialization enabled`
  - `CheckSpatialization ... mAutomaticSpatialization / mSpatializationEnabled`
  - `AUSpatialMixerV2 ... spatialization algorithm`
  - `AUSpatialMixerV2 ... Setting audio channel layout Atmos_7_1_4`
  - `AudioQueueObject ... Forcing 7.1.4 decoder for Atmos`
  - `Created new AudioQueue ... Spatialization`

### Inspect / TV Capture UI

- Show `pipeline_engine` (FigFilePlayer / FigStreamPlayer) on the capture summary.
- Show `asbdFormatID` alongside the runtime audio label.
- For local captures with FigFilePlayer + `ec+3` + lower-level spatial active, explain: `Atmos decode and spatial mixer are active, but TV.app's app-level spatial-rendering flag is false. Current evidence suggests this is a playback-engine/asbd distinction, not a codec-quality issue.`
- Do not penalize a local file in Compare only because `app_spatial_rendering = true` is missing when lower-level spatialization evidence is active. Surface both signals separately.
- If a future QuickTime/Safari capture mode is added, do not reuse the TV.app `mediaFormatinfo` verdict directly; QuickTime exposes different but still useful CoreAudio spatialization signals.

### TV Capture warnings

- Suppress any implicit assumption that `ec+3` is a worse codec than `qc+3`.
- Add an informational note when `pipeline_engine = FigFilePlayer` and the user is comparing against an HLS capture.
- Add a note that QuickTime local-file playback can show lower-level spatialization even without the TV.app HLS/qc+3 app-level flag.

## Follow-up issues to create or update

- Parse FigFilePlayer vs FigStreamPlayer pipeline engine in `tvlog.py` and expose it in capture summaries.
- Prefer the source-consistent engine in summaries when stale/surrogate
  player noise logs both FigFilePlayer and FigStreamPlayer.
- Surface asbdFormatID and `immersive_rendering_requested` in Inspect / TV Capture, separate from the runtime audio pill.
- Compare scoring: do not down-rank captures whose only missing signal is `mediaFormatinfo ... rendering spatial audio = true` when lower-level spatial machinery is active.
- Added: `dolby-tool tvlog-parse` for saved raw logs and
  `dolby-tool tvlog-capture --profile local-player` for QuickTime/Safari
  control captures.
- Added: `dolby-tool hls-package <local media file> <folder>` to
  stream-copy a normal local file into fMP4 HLS with a separate HLS audio
  group by default. This makes the strongest observed non-custom path
  reproducible without first authoring or obtaining a `.movpkg`.
  The command patches the generated master playlist with Apple-player
  compatibility tags; without those tags, the first live QuickTime test
  failed before media segment playback.
- Added: `dolby-tool hls-package-capture <local media file> <folder>` to
  package, serve, open QuickTime, and capture with the correct startup
  ordering in one command.
- Added: `dolby-tool hls-prepare <local.movpkg> <folder>` to flatten simple
  persisted-HLS packages into the served folder layout.
- Added: `dolby-tool hls-serve <folder> --open quicktime` for a
  Range-capable localhost server that matches the successful local-HLS
  playback setup.
- Added: `dolby-tool movpkg-scan <TV media root>` to batch-scan top-level
  downloaded TV.app packages and skip interstitial child `.movpkg`
  packages. Current local scan finds only `Grass Lands` and `The Hope
  That Kills You`, and both lack complete top-level main Atmos.
- Optional future investigation: confirm whether `qc+3` asbdFormatID is exclusively emitted by FigStreamPlayer for HLS Atmos by capturing more Apple TV+ titles and at least one non-Apple HLS Atmos source if available.

## Acceptance-criteria check

- [x] Apple HLS control capture used.
- [x] Original local-file capture used and consistent with Local 1 / Local 2 in `ISSUE_8_EC3_QC3_REPORT.md`.
- [x] Additional TV.app local direct-open/library-style captures observed; still FigFilePlayer/ec+3/app-false.
- [x] QuickTime Player local-file control captured; still FigFilePlayer/ec+3 but with stronger lower-level CoreAudio spatialization evidence.
- [x] QuickTime Player local-HLS control captured; FigStreamPlayer with Atmos/CoreAudio spatial mixer evidence.
- [x] QuickTime Player local-HLS path reproduced with merged `hls-prepare`, `hls-serve`, and `tvlog-capture --profile local-player` tooling.
- [x] Direct local-file-to-HLS packaging path added via `hls-package` so
  QuickTime local HTTP HLS can be produced from ordinary local files.
- [x] Direct local-file-to-HLS packaging path live-tested in QuickTime;
  auto-patched output reaches FigStreamPlayer and lower-level Atmos /
  spatial mixer evidence.
- [x] Direct local-file-to-HLS capture workflow wrapped in a single command
  so future runs start log capture before QuickTime playback.
- [x] Safari local-HLS launch attempted; current result is failed-page tabs and 0 playback events, so Safari remains unproven rather than a working path.
- [x] Local-file MP4 faststart, M4V, and MOV remux variants tested; all stayed FigFilePlayer/ec+3/app-false.
- [x] Local HLS packaging test completed for QuickTime; TV.app URL-scheme launch did not work.
- [x] Report distinguishes app-level spatial rendering from lower-level spatial / Atmos evidence.
- [x] Report does not claim `ec+3` is lower quality than `qc+3` by token name.
- [x] Report clearly states what was tried and what remains unknown.
- [x] Follow-up implementation issues identified.
