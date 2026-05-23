# Dolby spatial-on-local: current model (summary)

Last updated: 2026-05-23 (post N2 probe). Supersedes all earlier ISSUE_*
reports in this folder.

## Bottom line

Local Atmos can render `is rendering spatial audio = true` on macOS. The
limitation is **TV.app behavior**, not macOS, not hardware, not the file.

### Open question raised on 2026-05-23 (N2 probe)

A fresh TV.app local capture taken on this date shows the **system layer
reporting spatial = on**:

- `AVCFPlayerItemSetAllowedAudioSpatializationFormats: 0x7` (full mask, no
  narrowing observed in the log surface)
- `MEMixerChannel`: `mContentspatializable=1, mSpatializationStatus=2` for
  16ch `ec+3` (accepted)
- `SpatializationManager`: `spatialization = 1` for TV.app
- `spatialAudioSources = ['mlti']` (recognized Atmos source token)
- 7.1.4 Atmos decoder forced; `AUSpatialMixerV2` active

Only the app-level `mediaFormatinfo ... is not rendering spatial audio`
line still resolves false. This **contradicts** the older dtrace finding
that the AVF intersection resolves to 0 for local items. Either the gate
behavior has shifted since the original trace, or the AVF narrowing still
happens but is not visible in the `log stream` surface. A fresh dtrace
session (requires Recovery + `csrutil enable --without debug --without
dtrace`) plus an audible A/B between TV.app local and QuickTime+HLS+local
are the two needed disambiguations. See
`06_next_steps_and_edge_cases.md`.

- **SpatialProbe** (a ~100-line Swift AVPlayer harness) plays the same local
  `Blood and Bone.mp4` TV.app fails on, on the same MBP M-series built-in
  speakers, and the SpatializationManager logs `spatialization = 1` with
  runtime `ec+3` 16ch.
- **QuickTime + local HLS** (file repackaged as HLS, served from a
  Range-capable localhost server) engages `FigStreamPlayer`, decodes `ec+3`
  16ch, forces a 7.1.4 Atmos decoder, and configures `AUSpatialMixerV2` with
  `Atmos_7_1_4`.
- **TV.app + local file** stays on `FigFilePlayer`. The earlier dtrace
  pass showed the AVF allow-mask intersection resolving to 0 via
  `mpc_updateAVAudioSpatializationFormatsForPlayerAudioFormat:spatialPreference:`.
  The 2026-05-23 log-surface re-capture no longer reproduces that
  symptom at the visible-log layer (see Open question above). Either
  way, `is rendering spatial audio = false` in `mediaFormatinfo`.
- **TV.app + Apple TV+ HLS online** is the only TV.app path observed
  reaching the true state, because the HLS-only
  `_updateAllowedAudioSpatializationFormatsFromFigItem` re-adds Multichannel
  to the allow mask via FigItem manifest metadata.

## What TV.app's failure is and isn't

It is **not**:
- a codec issue (`ec+3` vs `qc+3` is a runtime token, not a quality ranking)
- a container/remux issue (mp4 faststart, m4v, mov all produce the same
  app-spatial-false result on TV.app)
- a hardware/route issue (same hardware/route works under SpatialProbe and
  QuickTime+HLS)
- entitlement-gated (TV.app has no spatial-audio-specific entitlement;
  `codesign -d --entitlements -` shows the public AVF entitlements only)

It **is**:
- a `spatialPreference` value TV.app picks for `FigFilePlayer`-backed
  items in `mpc_updateAVAudioSpatializationFormatsForPlayerAudioFormat:` that
  strips Multichannel (`0x2`) from the allow mask on a 2ch route, leaving
  `0x5`.
- compounded by downstream SpatialMgr per-app/per-route state and
  MEMixerChannel content eligibility (see `01_gate_model.md`).

## What works for the user's actual goal today

For local Atmos files, ranked by practicality:

1. **QuickTime + locally served HLS** (`dolby-tool hls-package-capture`).
   Apple-native, reproducible, audible on built-in speakers.
2. **SpatialProbe** (`harness/Sources/SpatialProbe/main.swift`). Diagnostic
   only; not a daily player.
3. **TV.app**: only Apple TV+ HLS online, on a route that registers as
   spatial-capable. No known TV.app local-file lever.

## Companion reports

| File | Purpose |
|---|---|
| `01_gate_model.md` | The multi-layer gate, from AVF down to MEMixerChannel |
| `02_tv_app_specifics.md` | Why TV.app narrows the allow mask; entitlement and SIP/hook feasibility |
| `03_evidence_matrix.md` | All captured variants in one table |
| `04_paths_explored.md` | Every path tried, what worked, what didn't |
| `05_tooling.md` | `dolby-tool` commands and the SpatialProbe harness |
| `06_next_steps_and_edge_cases.md` | Open levers and untested edge cases |
