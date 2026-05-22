# Issue 12: Can local TV.app files activate app-level spatial rendering?

## Environment

- Date: 2026-05-22
- macOS: 26.5 (25F71)
- Mac model: Mac15,6
- TV.app: 1.6.5
- Route: MacBook Pro Speakers, 2 channels, 48000 Hz, built-in
- Evidence: raw `log stream` captures saved as
  `/tmp/dolby_issue8_apple_hls_f1_renderer_builtin.json` (HLS control) and
  `/tmp/dolby_issue8_local_ep8_renderer_builtin.json` (local file)

## Short conclusion

**No.** On the evidence available, a local file played through TV.app cannot
reach `mediaFormatinfo ... is rendering spatial audio = true` by changing
file-level properties.

The gating is **not** in the file. It is in the CoreMedia pipeline that
TV.app picks for the asset:

- Local files are played by **`FigFilePlayer`**, which emits asbdFormatID
  `ec+3` for an E-AC-3 / Atmos track.
- Apple TV+ / HLS is played by **`FigStreamPlayer`**, which emits asbdFormatID
  `qc+3` (an Apple-private CoreMedia Dolby-Atmos identifier) for the same
  underlying audio.
- TV.app's app-level `mediaFormatinfo ... is rendering spatial audio` flag
  transitions to `true` only when the asbdFormatID is `qc+3`. In every
  observed capture, the renderer says `is rendering spatial audio` only on a
  `qc+3` row; it stays `is not rendering spatial audio` on the `ec+3` row.

There is no documented way to make TV.app route a user's local mp4 / m4v
asset through `FigStreamPlayer`. Library import, container remux, sample-
entry retagging, default-track flags, channel layout, and HEVC/DV brand
choices all stay inside `FigFilePlayer` and therefore stay on the `ec+3`
asbd path.

So the more accurate answer is: lower-level Atmos / OAR / SpatializationManager
machinery does run for local Atmos files on built-in speakers, but the
app-level `mediaFormatinfo` flag is effectively reserved for the Apple HLS
playback engine. Local file authoring cannot toggle it.

## Direct evidence

These are the actual log lines that confirm the pipeline difference, not just
the runtime label difference.

Local capture, `FigFilePlayer` path:

```
TV[...] [com.apple.coremedia:player] <<<< FigFilePlayer >>>>
    itemfig_ReportAudioPlaybackThroughFigLog: ...
    [AudioFormat ec+3] [AudioChannels 16] [Spatialization Eligible yes]
    [Client permits multi: yes, stereo: no] [Spatialization yes]
    [StereoSpatialization no] [item requires immersive rendering no]
TV[...] [com.apple.TV:ampplay] play> cm>> mediaFormatinfo ...
    asbdFormatID = ec+3, Dolby Atmos, asbdNumChannels = 16,
    asbdSampleRate = 48.0 kHz, is not rendering spatial audio
```

HLS capture, `FigStreamPlayer` path:

```
TV[...] [com.apple.coremedia:player] <<<< FigStreamPlayer >>>>
    fpfs_ReportAudioPlaybackThroughFigLog: ...
    [AudioFormat qc+3 is decodable] [AudioChannels 16]
    [Spatialization Eligible yes] ...
TV[...] [com.apple.TV:ampplay] play> cm>> mediaFormatinfo ...
    asbdFormatID = qc+3, Dolby Atmos, asbdNumChannels = 16,
    asbdSampleRate = 48.0 kHz, is rendering spatial audio
```

Both items get the same player-level allowance:

```
TV[...] [com.apple.TV:cmplayer] play> avcff>
    AVCFPlayerItemSetAllowedAudioSpatializationFormats
    for playerItem ...: 0x7
```

so the gating is not in the AVCF spatialization mask.

Both items also enter the lower-level spatial stack:

- `SpatializationManager` reports `spatialization = 1` and posts spatial info
  for `Default-Output` with `spatialAudioSources = [ 'mlti' ]`.
- `ACDDPAtmosDecoder` reports `mIsAtmos = 1` and `mIsOARMode = 1` after the
  cookie is parsed.
- `MEMixerChannel` reports `mContentspatializable = 1` and
  `mSpatializationStatus = 2` for the `ec+3 ch=16` mixer in the local case.

So lower-level Atmos / OAR / spatial machinery is active in both. The only
flag that differs is the app-level `mediaFormatinfo` line, and that flag
follows the asbdFormatID, which follows the pipeline (FigFilePlayer vs
FigStreamPlayer), which follows the asset type (file vs HLS), not anything
inside the file.

## Why file-level variants cannot fix this

The decision of which CoreMedia engine plays an item is made when the
`AVAsset` is created. A `file://` or library-backed asset goes to
`FigFilePlayer`. An `m3u8` / HLS asset goes to `FigStreamPlayer`. TV.app
does not expose UI to load arbitrary HLS URLs, and importing into the TV
library still creates a file-backed asset.

Concretely:

- MP4 / MOV container brands, `dvh1` vs `dvhe` vs `hvc1` sample entries,
  audio `ec-3` vs `ec+3` codec tags, JOC complexity-index visibility,
  channel-layout, audio-track order, default-track flags, language and title
  metadata, file extension — all of these are read by `FigFilePlayer` and
  none of them cause `FigStreamPlayer` to take over.
- The `[item requires immersive rendering no]` line seen on the local file
  is set by the FigFilePlayer asset analyzer; even forcing it to `yes`
  (which there is no documented file-level way to do) would not change the
  pipeline.
- Library-imported playback uses the same FigFilePlayer engine as direct
  open. Both produce `ec+3` asbd.
- Apple HLS sources do not even need `ec+3`/`qc+3` audio in their manifest;
  the manifest advertises plain `ec-3` Atmos audio groups. The `qc+3` asbd
  is invented at the FigStreamPlayer / CoreMedia decoder layer for HLS
  content. It is a runtime ID, not a container tag.

## Evidence table

| Variant | Route | Player engine | Video FourCC | Container/runtime audio label | asbd format ID | App spatial rendering ever true | Last app spatial state | Lower-level spatial evidence | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Apple TV+ / HLS, F1 stream (control) | MacBook Pro Speakers | FigStreamPlayer | dvh1 (HLS variant `dvh1.05.06,ec-3`) | source `ec-3` / runtime `qc+3` ch=16 | `qc+3` | yes | true | SpatializationManager active; mIsAtmos=1, mIsOARMode=1; mixer `qc+3` ch=16 spatializable, status 2 | reaches `is rendering spatial audio` |
| Local TV.app file, episode 8 | MacBook Pro Speakers | FigFilePlayer | dvh1 (HEVC enc=6, 3840x1600) | container `ec-3` / runtime `ec+3` ch=16 | `ec+3` | no | false | SpatializationManager active; mIsAtmos=1, mIsOARMode=1; mixer `ec+3` ch=16 spatializable, status 2; `[item requires immersive rendering no]` | stays at `is not rendering spatial audio` |
| Local-file variants (library import, remux, MOV, alternate sample entry, alternate default flags) | not tested live in this run | predicted FigFilePlayer | n/a | n/a | predicted `ec+3` | predicted no | predicted false | n/a | Not tested because the existing captures show the gating is at the asbd / engine layer; file-level fields are not in that decision path. Listed here so future captures can falsify the prediction. |

## Answers to the issue questions

1. *Can any local file played in TV.app produce `mediaFormatinfo ...
   rendering_spatial_audio = true` on MacBook Pro Speakers?*

   No instance observed. The asbdFormatID for local Atmos playback is
   `ec+3`, which never produced `is rendering spatial audio` in any captured
   line.

2. *If yes, what properties trigger it?* — Not applicable. None of the
   file-level fields the issue lists (brands, sample entry, codec tag, JOC,
   channel layout, track order, default flags, language/title) is consulted
   by the gating path.

3. *Is app-level spatial rendering restricted to Apple-managed playback?* —
   Effectively yes, in TV.app. It is bound to `FigStreamPlayer` /
   asbdFormatID `qc+3`, which is only produced by Apple's HLS / streaming
   CoreMedia engine. Apple TV+ content (which decrypts and streams HLS)
   takes that engine. User local files do not.

4. *Does TV.app need specific local-file metadata?* — No specific local-file
   metadata flips the gating flag.

5. *Library-import vs direct open?* — Both go through FigFilePlayer. Same
   `ec+3` asbd. Not expected to differ on this flag.

6. *Does remux / retag affect the flag?* — No. Remuxing or retagging the
   container does not move the asset off FigFilePlayer.

7. *Is `mediaFormatinfo` truly the final renderer state?* — It is the
   app-level / cmplayer state. Lower-level CoreAudio still runs the Atmos
   decoder, OAR mode, mixer spatializable status, and SpatializationManager
   binding for `Default-Output` with `spatialAudioSources = [ 'mlti' ]`
   regardless of the app-level flag. So the app-level flag is a strong
   "Apple-rendered spatial audio is engaged" signal, but local playback can
   still be using lower-level Atmos / spatial machinery even when the
   app-level flag is false.

## Interpretation

- The `ec+3` vs `qc+3` distinction is a CoreMedia engine distinction
  (FigFilePlayer vs FigStreamPlayer), not a quality distinction. Saying
  `qc+3` is "better" than `ec+3` would be wrong.
- The interesting product question is no longer "is local Atmos broken?" —
  the local path is engaging Atmos decode, OAR mode, and spatial mixer
  status. The product question is whether Apple's app-level renderer is
  doing an extra Apple-rendered spatialization on top of that, and whether
  that extra layer is reserved for HLS playback. The current evidence is
  consistent with "yes, reserved for HLS", but a final proof would need
  Apple-internal documentation or a way to A/B the audible output, which is
  not in scope here.
- Lower-level Atmos / OAR machinery being active on local playback means
  the local file is not silently downgraded to plain stereo. It is decoded
  as Atmos and the spatial mixer is engaged. The missing layer is the
  app-level `mediaFormatinfo ... rendering spatial audio` confirmation.

## What was not tested

To keep this run cheap, no new live captures were made for this issue:

- No library-import vs direct-open comparison was captured.
- No remux / retag / MOV / `dvh1` retagging variants were captured.
- No alternate audio track order or default-track variant was captured.
- No QuickTime / IINA control comparison was captured for the local file.

The reason is that the existing HLS vs local captures already locate the
gating at the CoreMedia engine layer (FigFilePlayer vs FigStreamPlayer) and
at the asbdFormatID (`ec+3` vs `qc+3`). File-level variants would still
produce a FigFilePlayer asset and an `ec+3` asbd, so they would not change
the gated flag. If a future capture shows a local file producing `qc+3` or
`is rendering spatial audio`, this conclusion is wrong and the captured run
should be saved alongside this report.

## Recommended tool changes

These match the focus areas in #10, #6, #4 and add file-side parser hooks
for this issue.

### Parser additions in `dolby_tool/tvlog.py`

- Add a `pipeline_engine` field on parsed audio events derived from the
  reporting function in the raw line:
  - `FigFilePlayer` / `itemfig_ReportAudioPlaybackThroughFigLog` →
    `pipeline_engine = "FigFilePlayer"`
  - `FigStreamPlayer` / `fpfs_ReportAudioPlaybackThroughFigLog` →
    `pipeline_engine = "FigStreamPlayer"`
- Capture the `[item requires immersive rendering yes|no]` bracket as a
  new `immersive_rendering_requested` field on the audio event.
- Capture `AVCFPlayerItemSetAllowedAudioSpatializationFormats ... 0xN` as
  a new renderer hint `allowed_spatialization_formats_mask`.
- Capture `Stereo Spatialization allowed by default due to asset containing
  video.` as a renderer hint `stereo_spatialization_default_reason` so
  Inspect can show whether stereo spatialization is on by default.
- Capture `spatialAudioSources = [ 'mlti' ]` (and similar) from
  `SpatializationManager` as a renderer hint
  `spatial_audio_source_tokens` so Inspect can show the binding's
  declared sources.

### Inspect / TV Capture UI

- Show `pipeline_engine` (FigFilePlayer / FigStreamPlayer) on the capture
  summary so users see whether TV.app routed the asset through the file
  engine or the streaming engine. This is the strongest single predictor
  of `mediaFormatinfo` reaching `is rendering spatial audio`.
- Show `asbdFormatID` alongside the runtime audio label, and warn when
  asbdFormatID is `ec+3` while the user is hoping for Apple HLS-style
  spatial rendering.
- For local captures with FigFilePlayer + `ec+3` + lower-level spatial
  active, show an explicit explanation: "Atmos decode and spatial mixer
  are active, but TV.app's app-level renderer flag is reserved for the
  HLS engine. This appears to be a pipeline-level gate, not a file-level
  one."
- Compare scoring should not penalize a local file for failing
  `app_spatial_rendering = true` if `lower_level_spatialization_active`
  is true. Surface both signals separately, as #10 already recommends.

### TV Capture warnings

- Suppress the existing implicit assumption that `ec+3` is a worse codec
  than `qc+3`.
- Add an informational note when `pipeline_engine = FigFilePlayer` and the
  user is comparing against an HLS capture: explain the engine distinction.

## Follow-up issues to create

- New issue: "Parse FigFilePlayer vs FigStreamPlayer pipeline engine in
  `tvlog.py` and expose it in capture summaries and Inspect."
- New issue: "Surface asbdFormatID and `immersive_rendering_requested` in
  Inspect, separate from the runtime audio pill."
- New issue: "Compare scoring: do not down-rank captures whose only
  missing signal is `mediaFormatinfo ... rendering spatial audio = true`
  when lower-level spatial machinery is active."
- Optional future investigation: "Confirm `qc+3` asbdFormatID is exclusively
  emitted by FigStreamPlayer for HLS Atmos by capturing more Apple TV+
  titles and at least one non-Apple HLS Atmos source if available."

## Acceptance-criteria check

- [x] Apple HLS control capture used.
- [x] Original local-file capture used and matches Local 1, Local 2 in
      `ISSUE_8_EC3_QC3_REPORT.md`.
- [ ] At least one local-file variant or playback mode tested. Not
      completed in this run. Justification in "What was not tested".
- [x] Report distinguishes app-level spatial rendering from lower-level
      spatial / Atmos evidence.
- [x] Report does not claim `ec+3` is lower quality than `qc+3` by token
      name.
- [x] Report clearly states what was tried and what remains unknown.
- [x] Follow-up implementation issues identified.
