# Issue 8: ec+3 vs qc+3 Playback Paths

## Environment

- Date: 2026-05-22
- macOS: 26.5 (25F71)
- Mac model: Mac15,6
- TV.app: 1.6.5
- Primary viewing route: MacBook Pro Speakers, 2 channels, 48000 Hz, built-in transport
- Additional routes tested: JBL Tune 720BT wired/headphone route and JBL Tune 720BT Bluetooth route
- External Apple spatial-headphone coverage: not completed; no AirPods / Beats / Apple head-tracked route was available

## Short Conclusion

The core finding is no longer about whether `ec+3` or `qc+3` is the better codec token. Current evidence still supports treating `ec+3` as the local/container or FigFilePlayer E-AC-3 / Dolby Atmos label, and `qc+3` as TV.app/CoreMedia's runtime label for Apple TV+ / HLS Dolby-family playback whose source variants advertise `ec-3`.

The more important finding is the app-level spatial renderer flag:

- Apple TV+ / HLS on MacBook Pro Speakers repeatedly reached `qc+3 Dolby Atmos ch=16` with `mediaFormatinfo ... is rendering spatial audio`.
- Local TV.app playback on the same MacBook Pro Speakers repeatedly reached `ec+3 Dolby Atmos ch=16`, but `mediaFormatinfo ... is not rendering spatial audio`.
- The local path still showed lower-level spatial/Atmos evidence: `Spatialization yes`, `SpatializationManager spatialization = 1`, `ACDDPAtmosDecoder mIsAtmos = 1`, OAR mode, and `MEMixerChannel ... mContentspatializable=1 mSpatializationStatus=2`.

Conservative interpretation: Apple TV+ / HLS appears to reach a final app-level spatial-rendering state on built-in MacBook speakers that the tested local TV.app file has not reached. This is evidence of a renderer-state difference, not evidence that the `qc+3` audio token is inherently higher quality than `ec+3`.

## Test Matrix

Captures were run with `dolby_tool.tvlog.LogCapture` while driving TV.app manually. HLS 5/6 were captured after playback was already running. Local 5 was also captured after playback was already running and therefore missed almost all audio/renderer initialization events. Local 6 was captured before starting the local file and is the useful local follow-up capture.

| Run | Source | Route | Runtime audio | Source / HLS audio | App spatial flag | Lower-level renderer evidence | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| HLS 1 | Apple TV+ / HLS | MacBook Pro Speakers | `qc+3 ch=16` | HLS `dvh1...,ec-3` | false then **true** | spatial power active; Atmos/OAR true; mixer `qc+3 ch=16` spatializable/status 2 | First built-in capture; shows transition into app-level spatial rendering |
| Local 1 | Local TV.app file | MacBook Pro Speakers | `ec+3 ch=16` | local E-AC-3 / Atmos | **false** | spatial power active; Atmos/OAR true; mixer `ec+3 ch=16` spatializable/status 2 | Local path enters Atmos/spatial stack but app flag is not rendering |
| HLS 2 | Apple TV+ / HLS, different stream | MacBook Pro Speakers | `qc+3 ch=16`; also one `ec+3 ch=16` event | HLS `dvh1...,ec-3` | **true** during capture, later false during transitions | spatial power toggled; Atmos/OAR true; mixer `qc+3` and `ec+3` spatializable states | Noisy capture with many startup/transition events; proves HLS can enter app-level rendering |
| Local 2 | Local TV.app file | MacBook Pro Speakers | `ec+3 ch=16` | local E-AC-3 / Atmos | **false** | spatial power active; Atmos/OAR true; mixer `ec+3 ch=16` spatializable/status 2 | Same local pattern repeated |
| HLS 3 | Apple TV+ / HLS, same stream as HLS 2 | JBL wired/headphone route | `qaac ch=2` | HLS selected `mp4a.40.2` stereo | false | route not capable of spatialization; mixer non-spatial AAC/QAAC | HLS dropped to stereo on this route |
| Local 3 | Local TV.app file | JBL wired/headphone route | `ec+3 ch=16` observed, spatialization no | local E-AC-3 / Atmos | false | route not capable of spatialization; mixer fell to `ec-3 ch=6` non-spatial | Local also not spatial on this route |
| Local 4 | Local TV.app file | JBL Bluetooth route | `ec-3 ch=6` | local E-AC-3 / Atmos | false | route neither built-in speakers nor headphones; non-spatial mixer | Bluetooth local route is not useful for MacBook-speaker spatial question |
| HLS 4 | Apple TV+ / HLS, same stream as HLS 1 | JBL Bluetooth route | `qaac ch=2` | HLS selected `mp4a.40.2` stereo | false | route neither built-in speakers nor headphones; non-spatial mixer | HLS dropped to stereo on Bluetooth |
| HLS 5 | Apple TV+ / HLS, same stream as HLS 2 | MacBook Pro Speakers | no direct `audio_format` event captured | HLS `dvh1...,ec-3` | **true** | only mediaFormatinfo/route hints captured | Stable-playback capture still saw `qc+3 Dolby Atmos ch=16` rendering spatial audio |
| Local 5 | Local TV.app file | MacBook Pro Speakers | not captured | not captured | not captured | only `dvh1` codec events | Capture started after playback was stable and missed audio/renderer setup; inconclusive |
| HLS 6 | Apple TV+ / HLS, same stream as HLS 1 | MacBook Pro Speakers | `qc+3 ch=16` | HLS `dvh1...,ec-3` | **true** | spatial power active; Atmos/OAR true; mixer `qc+3 ch=16` spatializable/status 2 | Stable-playback capture repeats HLS app-level rendering |
| Local 6 | Local TV.app file | MacBook Pro Speakers | `ec+3 ch=16` | local E-AC-3 / Atmos | **false** | spatial power active; Atmos/OAR true; mixer `ec+3 ch=16` spatializable/status 2 | Useful local follow-up; repeats local app-level non-rendering flag |

## Updated Answers

1. Does `qc+3` appear only for Apple TV+ / HLS streams?
   - In these captures, `qc+3 ch=16` appears on Apple TV+ / HLS built-in-speaker playback only.
   - The tested local file uses `ec+3 ch=16` on built-in speakers and does not expose `qc+3`.

2. Does `ec+3` ever appear for Apple TV+ / HLS playback?
   - The Apple TV+ / HLS manifest or variant layer advertises `ec-3` Atmos audio groups.
   - HLS 2 also produced one runtime `ec+3 ch=16` event, but the main HLS runtime path remains `qc+3 ch=16`.
   - CoreAudio decoder subtype hints can show `ec+3` even when the TV.app runtime audio label is `qc+3`.

3. Do `ec+3 ch=16` and `qc+3 ch=16` show the same spatialization / Atmos / route metadata?
   - On MacBook Pro Speakers, both are 16-channel Dolby-family paths and both can show `Spatialization yes`, Atmos decoder activity, OAR mode, and mixer content-spatializable status.
   - The clearest difference is app-level `mediaFormatinfo`: Apple HLS `qc+3` repeatedly reaches `rendering_spatial_audio = true`, while local `ec+3` repeatedly reports `rendering_spatial_audio = false`.

4. Does the selected output device change the reported token/path?
   - Yes. JBL wired/headphone and JBL Bluetooth routes changed behavior significantly.
   - Apple HLS fell back to stereo `mp4a.40.2` / `qaac ch=2` on the tested JBL routes.
   - The local file fell to non-spatial `ec-3 ch=6` / non-spatial mixer evidence on Bluetooth, and showed non-spatial behavior on the wired/headphone route.

5. Is there evidence that `ec+3` is higher quality than `qc+3`?
   - No. The token name alone is still not evidence of higher quality.
   - `qc+3` appears to be the HLS/CoreMedia runtime label for an Apple Dolby-family path whose source variants advertise `ec-3`.
   - The meaningful difference observed so far is final app-level spatial rendering state on built-in speakers, not codec-token quality.

6. Is `qc+3` likely an Apple-private/CoreMedia runtime label?
   - Yes. Current evidence best supports labeling `qc+3` as an Apple/CoreMedia Dolby-family runtime path for TV.app HLS playback.
   - The UI should not imply that `qc+3 ch=16` is automatically worse than `ec+3 ch=16`.

7. Does Apple TV+ appear to get extra hidden spatial/audio functionality over local TV.app files?
   - Plausibly yes on built-in MacBook speakers, but worded carefully: Apple HLS repeatedly reaches the app-level `mediaFormatinfo ... rendering spatial audio = true` state while the tested local file repeatedly remains `false`.
   - This does not mean the local file is plain stereo. The local file still enters lower-level Dolby/Atmos/CoreAudio spatial machinery.
   - The best current statement is: Apple-native HLS appears to get a different or more complete app-level spatial-rendering state than this local file on MacBook Pro Speakers.

## Interpretation

- MacBook speakers are not receiving a real 16-speaker output. They are a 2-channel built-in route receiving an Apple-rendered / virtualized output derived from a Dolby-family decode path.
- `ec+3` vs `qc+3` should be treated as a source/runtime labeling distinction, not a simple quality ranking.
- The app-level `mediaFormatinfo` spatial-rendering flag is separate from lower-level spatial machinery. Local playback can show Atmos decode, OAR mode, `SpatializationManager` active, and mixer spatializable status while still reporting `mediaFormatinfo ... is not rendering spatial audio`.
- JBL wired/Bluetooth tests confirm that output route strongly affects selected audio. They did not show an Apple-native spatial advantage because both Apple HLS and local playback were non-spatial or stereo/downmixed on those routes.
- The capture timing matters. Starting capture after local playback is already stable can miss initialization events, as seen in Local 5.

## UI / Parser Recommendation

- Keep labeling `ec+3` as standard Dolby Digital Plus / E-AC-3.
- Keep labeling `qc+3` as Apple/CoreMedia Dolby-family runtime audio, not a warning state by default.
- Keep labeling `qaac` and `aacp` as AAC-like stereo fallback/alternate observations when they appear with 2 channels.
- Do not collapse renderer evidence into the `ec+3`/`qc+3` audio pill. The renderer question is separate from the codec token.
- Add or improve a "Spatial renderer evidence" section that distinguishes:
  - source/HLS audio label, e.g. `ec-3`, `mp4a.40.2`
  - runtime audio label, e.g. `qc+3`, `ec+3`, `qaac`
  - app-level spatial rendering from `mediaFormatinfo`
  - lower-level `SpatializationManager` state
  - Atmos decoder state / OAR mode
  - mixer spatializable/status hints
  - output-route capability
  - spatial-rendering change count
- Summarize app-level spatial rendering with both:
  - `ever true during capture`
  - `last observed state`
- Add a note when app-level rendering is false but lower-level Atmos/spatial evidence is active, for example: `Atmos decode/spatial machinery active, but app-level spatial rendering flag is false`.
- Add a capture-quality note when a run has video codec events but no audio/renderer events, suggesting the capture started too late to catch initialization.

## Follow-Up Work

- Create a UI/tooling issue for improved display of app-level spatial rendering vs lower-level spatial evidence.
- Create a separate investigation issue for whether local TV.app files can be made to activate the same app-level spatial-rendering state as Apple HLS.
- For future manual tests, capture local-file runs before starting playback, or provide a dedicated tool action that starts capture and then launches/plays the file.
- If possible later, test an Apple Spatial Audio headphone route. The current JBL routes are useful controls but do not answer AirPods/head-tracked behavior.
- Do not claim `ec+3` is better than `qc+3` unless future captures provide concrete bitrate, layout, sample-rate, substream, or renderer-quality evidence.
