# Issue 12: Can local TV.app files activate app-level spatial rendering?

## Environment

- Date: 2026-05-22
- macOS: 26.5 (25F71)
- Mac model: Mac15,6
- TV.app: 1.6.5
- Route: MacBook Pro Speakers, 2 channels, 48000 Hz, built-in
- Evidence: raw `log stream` captures saved locally as:
  - `/tmp/dolby_issue8_apple_hls_f1_renderer_builtin.json` (Apple HLS control)
  - `/tmp/dolby_issue8_local_ep8_renderer_builtin.json` (local file)

## Short conclusion

No local-file capture observed so far has reached:

```text
mediaFormatinfo ... is rendering spatial audio = true
```

Current evidence strongly suggests the gate follows the TV.app/CoreMedia playback engine rather than ordinary file-level metadata:

- Apple TV+ / HLS uses **FigStreamPlayer**, exposes runtime/asbd audio as `qc+3`, and reaches app-level `mediaFormatinfo ... is rendering spatial audio`.
- Local files use **FigFilePlayer**, expose runtime/asbd audio as `ec+3`, and remain at app-level `mediaFormatinfo ... is not rendering spatial audio`.

However, this should be treated as a strong working hypothesis, not a final impossibility proof. Library import, MOV remux, alternate brands, alternate audio-track/default-flag variants, and other local-file authoring changes were not live-tested in this run. A future capture showing a local file producing `qc+3` or `mediaFormatinfo ... is rendering spatial audio` would falsify the current conclusion.

## Direct evidence

These log lines show the engine/asbd distinction.

Local capture, FigFilePlayer path:

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

HLS capture, FigStreamPlayer path:

```text
TV[...] [com.apple.coremedia:player] <<<< FigStreamPlayer >>>>
    fpfs_ReportAudioPlaybackThroughFigLog: ...
    [AudioFormat qc+3 is decodable] [AudioChannels 16]
    [Spatialization Eligible yes] ...
TV[...] [com.apple.TV:ampplay] play> cm>> mediaFormatinfo ...
    asbdFormatID = qc+3, Dolby Atmos, asbdNumChannels = 16,
    asbdSampleRate = 48.0 kHz, is rendering spatial audio
```

Both items get the same player-level allowance:

```text
TV[...] [com.apple.TV:cmplayer] play> avcff>
    AVCFPlayerItemSetAllowedAudioSpatializationFormats
    for playerItem ...: 0x7
```

So the gating does not appear to be the AVCF spatialization mask.

Both items also enter lower-level spatial / Atmos machinery:

- `SpatializationManager` reports `spatialization = 1` and posts spatial info for `Default-Output` with `spatialAudioSources = [ 'mlti' ]`.
- `ACDDPAtmosDecoder` reports `mIsAtmos = 1` and `mIsOARMode = 1` after the cookie is parsed.
- `MEMixerChannel` reports `mContentspatializable = 1` and `mSpatializationStatus = 2` for the `ec+3 ch=16` mixer in the local case.

Therefore, local playback is not plain stereo and is not simply missing Atmos decode. The observed difference is the app-level `mediaFormatinfo` spatial-rendering flag.

## Working hypothesis

The current hypothesis is:

```text
Apple HLS asset
  -> FigStreamPlayer
  -> HLS source advertises ec-3 Atmos
  -> runtime/asbd label qc+3
  -> mediaFormatinfo rendering_spatial_audio = true

Local file asset
  -> FigFilePlayer
  -> local/container E-AC-3 / Atmos
  -> runtime/asbd label ec+3
  -> mediaFormatinfo rendering_spatial_audio = false
```

File-level variants are not expected to change this unless they make TV.app choose a different playback engine or expose a different asbdFormatID. That remains unproven until at least one local-file variant test is run.

## Evidence table

| Variant | Route | Player engine | Video FourCC | Source/runtime audio label | asbd format ID | App spatial rendering ever true | Last app spatial state | Lower-level spatial evidence | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Apple TV+ / HLS, F1 stream (control) | MacBook Pro Speakers | FigStreamPlayer | HLS variant `dvh1.05.06,ec-3` | source `ec-3` / runtime `qc+3 ch=16` | `qc+3` | yes | true | SpatializationManager active; mIsAtmos=1, mIsOARMode=1; mixer `qc+3 ch=16` spatializable/status 2 | Reaches `is rendering spatial audio` |
| Local TV.app file, episode 8 | MacBook Pro Speakers | FigFilePlayer | `dvh1` / HEVC enc=6 / 3840x1600 | container/local E-AC-3 / runtime `ec+3 ch=16` | `ec+3` | no | false | SpatializationManager active; mIsAtmos=1, mIsOARMode=1; mixer `ec+3 ch=16` spatializable/status 2; `[item requires immersive rendering no]` | Stays at `is not rendering spatial audio` |
| Local-file variants: library import, remux, MOV, alternate brands, alternate sample entry, alternate default flags | not live-tested in this run | predicted FigFilePlayer | n/a | n/a | predicted `ec+3` | predicted no | predicted false | n/a | Prediction only. Needs future capture if we want to falsify the working hypothesis. |

## Answers to the issue questions

1. **Can any local file played in TV.app produce `mediaFormatinfo ... rendering_spatial_audio = true` on MacBook Pro Speakers?**

   No observed local-file capture has done so. The tested local Atmos playback used `FigFilePlayer` and asbd/runtime `ec+3`, and every captured `mediaFormatinfo` line for that path reported `is not rendering spatial audio`.

2. **If yes, what properties trigger it?**

   Not answered. No local variant has triggered the app-level flag. Current evidence points to playback engine/asbd path rather than ordinary file-level properties.

3. **Is app-level spatial rendering restricted to Apple-managed playback?**

   Current evidence is consistent with that interpretation for TV.app on built-in MacBook speakers: Apple HLS / FigStreamPlayer / `qc+3` reaches the app-level flag, while local file / FigFilePlayer / `ec+3` does not. This is not final proof of exclusivity.

4. **Does TV.app need specific local-file metadata?**

   No tested local-file metadata has been shown to flip the flag. The plausible gating layer is player engine/asbdFormatID. Metadata variants remain untested live.

5. **Library import vs direct open?**

   Not live-tested in this run. The working prediction is that both stay file-backed / FigFilePlayer and therefore remain `ec+3`, but this should be verified if the goal is to close the issue definitively.

6. **Does remux / retag affect the flag?**

   Not live-tested in this run. The working prediction is no unless the remux/retag somehow changes TV.app's playback engine or runtime/asbd label.

7. **Is `mediaFormatinfo` truly the final renderer state?**

   It is the app-level / cmplayer state. Lower-level CoreAudio still runs Atmos decode, OAR mode, mixer spatializable status, and SpatializationManager binding for local playback even when this app-level flag is false. So the app-level flag is a strong Apple-rendered spatial-audio signal, but local playback can still have active lower-level Atmos / spatial machinery.

## Interpretation

- The `ec+3` vs `qc+3` distinction appears to be a CoreMedia engine/runtime distinction, not a simple quality distinction.
- Saying `qc+3` is a higher-quality codec than `ec+3` would be misleading.
- The tested local file is not silently downgraded to plain stereo. It reaches Atmos decode, OAR mode, and spatial mixer status.
- The missing signal for local playback is the app-level `mediaFormatinfo ... is rendering spatial audio` confirmation.
- The current evidence is consistent with Apple HLS having an extra app-level renderer state on built-in speakers. A final proof would require either Apple documentation, an audible/digital A/B method, or a successful local variant test that flips the flag.

## What was not tested

No new live captures were made for local-file variants in this run:

- No library-import vs direct-open comparison was captured.
- No remux / retag / MOV / brand-variant capture was made.
- No alternate audio track order or default-track variant was captured.
- No QuickTime / IINA control comparison was captured.

These omissions matter. The current conclusion should be read as: **existing captures strongly suggest an engine/asbd gate**, not as: **file-level changes are impossible**.

## Recommended tool changes

These match the focus areas in #10, #6, #4 and add file-side parser hooks for this issue.

### Parser additions in `dolby_tool/tvlog.py`

- Add a `pipeline_engine` field on parsed audio events derived from the reporting function in the raw line:
  - `FigFilePlayer` / `itemfig_ReportAudioPlaybackThroughFigLog` -> `pipeline_engine = "FigFilePlayer"`
  - `FigStreamPlayer` / `fpfs_ReportAudioPlaybackThroughFigLog` -> `pipeline_engine = "FigStreamPlayer"`
- Capture `[item requires immersive rendering yes|no]` as `immersive_rendering_requested`.
- Capture `AVCFPlayerItemSetAllowedAudioSpatializationFormats ... 0xN` as renderer hint `allowed_spatialization_formats_mask`.
- Capture `Stereo Spatialization allowed by default due to asset containing video.` as renderer hint `stereo_spatialization_default_reason`.
- Capture `spatialAudioSources = [ 'mlti' ]` and similar from `SpatializationManager` as `spatial_audio_source_tokens`.

### Inspect / TV Capture UI

- Show `pipeline_engine` (FigFilePlayer / FigStreamPlayer) on the capture summary.
- Show `asbdFormatID` alongside the runtime audio label.
- For local captures with FigFilePlayer + `ec+3` + lower-level spatial active, show an explanation: `Atmos decode and spatial mixer are active, but TV.app's app-level spatial-rendering flag is false. Current evidence suggests this is a playback-engine/asbd distinction, not a codec-quality issue.`
- Do not penalize a local file in Compare only because `app_spatial_rendering = true` is missing when lower-level spatialization evidence is active. Surface both signals separately.

### TV Capture warnings

- Suppress any implicit assumption that `ec+3` is a worse codec than `qc+3`.
- Add an informational note when `pipeline_engine = FigFilePlayer` and the user is comparing against an HLS capture.

## Follow-up issues to create

- Parse FigFilePlayer vs FigStreamPlayer pipeline engine in `tvlog.py` and expose it in capture summaries.
- Surface asbdFormatID and `immersive_rendering_requested` in Inspect / TV Capture, separate from the runtime audio pill.
- Compare scoring: do not down-rank captures whose only missing signal is `mediaFormatinfo ... rendering spatial audio = true` when lower-level spatial machinery is active.
- Optional future investigation: confirm whether `qc+3` asbdFormatID is exclusively emitted by FigStreamPlayer for HLS Atmos by capturing more Apple TV+ titles and at least one non-Apple HLS Atmos source if available.

## Acceptance-criteria check

- [x] Apple HLS control capture used.
- [x] Original local-file capture used and consistent with Local 1 / Local 2 in `ISSUE_8_EC3_QC3_REPORT.md`.
- [ ] At least one local-file variant or playback mode tested. Not completed in this run.
- [x] Report distinguishes app-level spatial rendering from lower-level spatial / Atmos evidence.
- [x] Report does not claim `ec+3` is lower quality than `qc+3` by token name.
- [x] Report clearly states what was tried and what remains unknown.
- [x] Follow-up implementation issues identified.
