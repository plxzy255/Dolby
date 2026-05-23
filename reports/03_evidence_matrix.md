# Evidence matrix

All captures on Mac15,6 / macOS 26.5 (25F71) / TV.app 1.6.5, between
2026-05-22 and 2026-05-23. App-spatial = `mediaFormatinfo ... is rendering
spatial audio` flag from `com.apple.TV:ampplay`. "n/a" means the process
does not emit that line.

| Run | Player | Source | Route | Engine | Source/runtime audio | Allow mask (final) | App-spatial | Lower-level Atmos/OAR/mixer | Notes |
|---|---|---|---|---|---|---|---|---|---|
| HLS 1 | TV.app | Apple TV+ HLS | MBP speakers | FigStreamPlayer | `ec-3` / `qc+3 ch=16` | 0x7 (FigItem re-add) | **true** | active | reaches true after transition |
| HLS 2 | TV.app | Apple TV+ HLS, alt stream | MBP speakers | FigStreamPlayer | `ec-3` / `qc+3 ch=16` (+1 `ec+3`) | 0x7 | **true** | active | noisy startup; proven true |
| HLS 5 | TV.app | Apple TV+ HLS (stable) | MBP speakers | FigStreamPlayer | `ec-3` / not captured | n/a | **true** | active | confirms repeatability |
| HLS 6 | TV.app | Apple TV+ HLS (stable) | MBP speakers | FigStreamPlayer | `ec-3` / `qc+3 ch=16` | 0x7 | **true** | active | confirms repeatability |
| Desert Lands online | TV.app | Apple TV+ HLS (Prehistoric Planet) | MBP speakers | FigStreamPlayer | `audio-atmos_vod-ap-aoc` / `qc+3 ch=16` | 0x7 | **true** | active | not-downloaded title; online path works |
| HLS 3 | TV.app | Apple TV+ HLS | JBL wired | FigStreamPlayer | `mp4a.40.2` / `qaac ch=2` | n/a | false | non-spatial mixer | ABR fell to stereo |
| HLS 4 | TV.app | Apple TV+ HLS | JBL Bluetooth | FigStreamPlayer | `mp4a.40.2` / `qaac ch=2` | n/a | false | non-spatial mixer | ABR fell to stereo |
| Local 1/2/6 | TV.app | Local Blood and Bone.mp4 | MBP speakers | FigFilePlayer | EAC-3 / `ec+3 ch=16` | 0x5 (Multichannel stripped) | false | active (mixer spatializable) | The canonical TV.app-local failure |
| Local 3 | TV.app | Local Blood and Bone.mp4 | JBL wired | FigFilePlayer | EAC-3 / `ec+3` then `ec-3 ch=6` | n/a | false | non-spatial mixer | Route not capable |
| Local 4 | TV.app | Local Blood and Bone.mp4 | JBL Bluetooth | FigFilePlayer | EAC-3 / `ec-3 ch=6` | n/a | false | non-spatial mixer | Route not capable |
| MP4 faststart | TV.app | Local remux | MBP speakers | FigFilePlayer | `dvh1` / `ec+3 ch=16` | 0x5 | false | active | Container variant did not change gate |
| M4V remux | TV.app | Local remux | MBP speakers | FigFilePlayer | `dvh1` / `ec+3 ch=16` | 0x5 | false | active | Same |
| MOV remux | TV.app | Local remux | MBP speakers | FigFilePlayer | `hev1` / `ec+3 ch=16` | 0x5 | false | active | Same; MOV exposed `hev1` instead of `dvh1` |
| Grass Lands offline | TV.app | Apple TV+ `.movpkg` (downloaded) | MBP speakers | FigStreamPlayer | `audio-stereo-160_download-ap-aoc` / `qaac ch=2` | 0x2 (multi-only) | false | non-spatial | Atmos advertised in manifest, `Complete=NO`, package selected stereo group |
| Ted Lasso offline | TV.app | Apple TV+ `.movpkg` (downloaded) | MBP speakers | FigStreamPlayer | `audio-stereo-128_download-ap-aoc` / `qaac ch=2` | n/a | false | transient `ec+3` 16ch evidence then stereo | No top-level main Atmos `Complete=YES` |
| External `.movpkg` (built via AVAssetDownloadTask) | TV.app | Externally built HLS package | MBP speakers | none | none | n/a | n/a | none captured | TV.app ignored the package across Finder / `open` / `open -b` / auto-add folder |
| `itls`/`itlss`/`itvls`/`itvlss` URL | TV.app | Local HLS server | MBP speakers | none | none | n/a | n/a | none captured | TV.app launched, player state = stopped |
| QuickTime local file | QuickTime | Local Blood and Bone.mp4 | MBP speakers | FigFilePlayer | EAC-3 / `ec+3 ch=16` | (process-local) | n/a | active; AudioQueue spatialization enabled; AUSpatialMixerV2 algo=7 | Stronger lower-level signals than TV.app local |
| QuickTime + local HLS | QuickTime | Local file repackaged as HLS via `hls-package` | MBP speakers | **FigStreamPlayer** | HLS `ec-3` Atmos group / `ec+3 ch=16` | (process-local) | n/a | active; Atmos decoder; forced 7.1.4; AUSpatialMixerV2 `Atmos_7_1_4` | Strongest local Apple-native path |
| Safari local HLS | Safari | Local HLS server | MBP speakers | none captured | none | n/a | n/a | none | Failed-page tabs; cold-load failure, not a spatialization result |
| SpatialProbe Run A | SpatialProbe | Local Blood and Bone.mp4 | Wired headset | FigFilePlayer | EAC-3 / `ec-3 ch=6` | 0x3 (set) | n/a | mixer rejects 6ch ec-3; SpatialMgr says route not capable | Route layer failure |
| **SpatialProbe Run B** | SpatialProbe | Local Blood and Bone.mp4 | **MBP speakers** | FigFilePlayer | EAC-3 / **`ec+3 ch=16`** | **0x3 (set)** | n/a | **spatialization = 1**; AudioQueue enabled; AUSpatialMixerV2; mixer spatializable | **Decisive: local Atmos can spatialize on macOS** |

## Reading the table

- **TV.app HLS online (any Atmos title) on MBP speakers → spatial true.**
  Path the user can reach today without engineering work.
- **TV.app HLS offline (downloaded `.movpkg`) → not yet observed true** on
  this account; 2/2 inspected titles have incomplete top-level main Atmos.
- **TV.app local on any container variant → false.** File-level changes
  do not move the gate.
- **TV.app accepts only Apple-managed `.movpkg`**. Externally-built
  packages are not opened.
- **QuickTime + local HLS (our `hls-package` flow)** is the strongest
  user-accessible path for local Atmos.
- **SpatialProbe Run B** is the proof that the limitation is in TV.app's
  product code, not in macOS or the file.

## N2 defaults-probe re-baseline (2026-05-23)

Eight TV.app local-file captures on MBP speakers, file
`/Users/psp/Movies/TV/Media.localized/TV Shows/The Boys/Season 5/08 Blood and Bone.mp4`,
35s each, captures in `captures/n2_defaults/`. Setup quits TV.app between
runs, deletes prior defaults keys, writes the candidate, re-launches with
the file.

| Run | `defaults write` applied | mediaFormatinfo | allow mask (logged) | mixer | SpatialMgr | source |
|---|---|---|---|---|---|---|
| baseline | (none) | false | 0x7 | spat=1, status=2, 16ch ec+3 | 1 | `['mlti']` |
| atmos_play_1 | `preferredDolbyAtmosPlaySetting -int 1` | false | 0x7 | same | 1 | `['mlti']` |
| atmos_play_2 | `preferredDolbyAtmosPlaySetting -int 2` | false | 0x7 | same | 1 | `['mlti']` |
| atmos_play_3 | `preferredDolbyAtmosPlaySetting -int 3` | false | 0x7 | same | 1 | `['mlti']` |
| mc_strategy_1 | `multichannelAudioStrategy -int 1` | false | 0x7 | same | 1 | `['mlti']` |
| mc_strategy_2 | `multichannelAudioStrategy -int 2` | false | 0x7 | same | 1 | `['mlti']` |
| dl_atmos | `downloadDolbyAtmos -bool YES` | false | 0x7 | same | 1 | `['mlti']` |
| dl_multi | `downloadMultichannel -bool YES` | false | 0x7 | same | 1 | `['mlti']` |

Two findings from this sweep:

1. **All four candidate keys are no-ops** for the local-file spatial path.
   Either they aren't read by `mpc_updateAVAudioSpatializationFormatsForPlayerAudioFormat:`
   or they exist only for download policy.
2. **Baseline contradicts the older gate model.** Today's TV.app local
   capture has the system layer reporting spatial=on (mixer accepts,
   SpatialMgr says yes, source `'mlti'`) while the older dtrace data
   had the AVF intersection resolving to 0. See `01_gate_model.md`
   caveat and `06_next_steps_and_edge_cases.md` priority 0.

## What's missing from the matrix

- No AirPods / Beats route on any path (only built-in + JBL).
- No Music.app comparison for an Atmos `.m4a`.
- No Apple TV+ Atmos title with `Complete=YES` top-level main Atmos
  observed yet — needs to scan a wider library.
- Safari is "no result" because of a cold-load failure, not a
  spatialization decision. A proper retry with HTTPS + user-gesture
  autoplay has not been done.
- SpatialProbe was tested only on wired headset and MBP speakers — no
  AirPods, no HDMI/AVR.

See `06_next_steps_and_edge_cases.md` for follow-ups.
