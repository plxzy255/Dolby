# Issue 12 follow-up: QuickTime vs TV.app for local Atmos playback

Companion to `ISSUE_12_LOCAL_SPATIAL_RENDERING_REPORT.md`.

This report addresses a narrower user question:

> Does QuickTime Player have all of TV.app local playback's spatial/Atmos evidence, plus additional Apple/CoreAudio spatialization signals? Could QuickTime be better for local files on MacBook speakers?

## Short answer

Possibly, but not proven by logs alone.

QuickTime Player does **not** reproduce the Apple TV+ / TV.app HLS path:

- no observed `FigStreamPlayer`
- no observed `qc+3` runtime/asbd path for the local file
- no TV.app `ampplay` `mediaFormatinfo ... is rendering spatial audio = true` line, because QuickTime is not TV.app

However, QuickTime local playback shows very strong Apple/CoreAudio spatial evidence:

- `FigFilePlayer`
- `ec+3` input
- `ACDDPAtmosDecoder mIsAtmos = 1`
- `mIsOARMode = 1`
- 16-channel `ec+3` AudioQueue creation
- `AudioQueue ... spatialization enabled, client-controlled`
- `AUSpatialMixerV2 ... spatialization algorithm = 7`
- `Created new AudioQueue ... [Channels: 16, ... Spatialization]`

This means QuickTime should not be treated as a downgrade or as a simple stereo downmix. It may be the strongest observed Apple-native local-file playback path so far, even though it does not unlock the Apple TV+ `qc+3` / TV.app app-level flag.

## Compared paths

| Path | Engine | Runtime/asbd label | App-level TV.app flag | Lower-level Atmos/OAR | AudioQueue / AUSpatialMixer evidence | Interpretation |
| --- | --- | --- | --- | --- | --- | --- |
| Apple TV+ HLS in TV.app | `FigStreamPlayer` | `qc+3 ch=16` | `true` observed | active | active/inferred | Known special TV.app HLS path |
| Local file in TV.app | `FigFilePlayer` | `ec+3 ch=16` | `false` observed | active | mixer/spatial evidence active | Good local path, but TV.app app-level spatial flag stays false |
| Local file in QuickTime | `FigFilePlayer` | `ec+3 ch=16` | not applicable / not emitted | active | explicit `AudioQueue` + `AUSpatialMixerV2` evidence | Potentially best Apple-native local-file path; needs listening/A-B verification |

## Interpretation

The earlier investigation correctly found that TV.app local playback does not reach the Apple TV+ HLS `qc+3` / app-level `rendering_spatial_audio = true` state.

The QuickTime control adds an important nuance:

> Missing the TV.app app-level flag does not mean local playback is not spatialized.

QuickTime local playback shows CoreAudio spatialization being explicitly enabled at the AudioQueue level and shows AUSpatialMixerV2 being configured. This may be closer to the actual audio-rendering layer than TV.app's `mediaFormatinfo` UI/app-level state.

Therefore, the practical playback question should be reframed:

- Apple TV+ HLS in TV.app is still the only observed path with the special `qc+3` / app-level spatial-rendering flag.
- For local files, QuickTime may use more visibly explicit Apple/CoreAudio spatial machinery than TV.app local playback.
- Whether QuickTime **sounds better** than TV.app local playback cannot be proven from logs alone. It needs a controlled listening A/B, or a digital/acoustic capture method.

## Answer to: "Does QuickTime have all the flags TV.app local has, plus more?"

Not exactly.

QuickTime does **not** have TV.app's `ampplay` `mediaFormatinfo` flag because that is TV.app-specific. It also does not move the local file to `FigStreamPlayer` or `qc+3`.

But QuickTime does show many of the same important lower-level signals as TV.app local playback:

- local `FigFilePlayer` engine
- `ec+3` / E-AC-3 Atmos-family path
- Atmos decoder active
- OAR mode active
- multichannel output formats
- spatialization enabled

And QuickTime adds or exposes more explicit CoreAudio evidence:

- `AudioQueue ... spatialization enabled, client-controlled`
- `AUSpatialMixerV2 ... spatialization algorithm = 7`
- AudioQueue creation with `[Spatialization]`

So the best current wording is:

> QuickTime local playback does not unlock Apple TV+ HLS's special TV.app flag, but it may expose and possibly use a stronger or more explicit Apple/CoreAudio spatial path than TV.app local playback. It is a plausible candidate for better local audio on MacBook speakers.

## Recommended practical test

Run a listening A/B on MacBook Pro Speakers:

1. Same local file, same scene.
2. Same output route: MacBook Pro Speakers.
3. Same system volume.
4. Disable EQ/enhancements elsewhere.
5. Compare:
   - TV.app local library playback
   - QuickTime Player local playback
   - optionally IINA/mpv as a non-Apple control
6. Listen for:
   - dialogue center stability
   - width
   - height illusion
   - reverb/room placement
   - bass/impact
   - whether effects seem to move outside the laptop body

Avoid judging from loudness alone. If QuickTime is louder, volume-match before deciding.

## Recommended tool/report changes

The tool should avoid reducing local playback to a binary `spatial true/false` verdict.

Add a renderer-layer model:

1. **TV.app app-level spatial flag**
   - `mediaFormatinfo ... rendering_spatial_audio`
   - only emitted by TV.app logs observed so far

2. **CoreAudio lower-level spatial evidence**
   - Atmos decoder active
   - OAR mode active
   - mixer content spatializable
   - AudioQueue spatialization enabled
   - AUSpatialMixerV2 configured

3. **Physical route layer**
   - MacBook speakers
   - AirPods/headphones
   - HDMI/AVR

For QuickTime/Safari/local-player captures, do not expect TV.app `mediaFormatinfo`. Instead, summarize:

- `FigFilePlayer` vs `FigStreamPlayer`
- runtime/asbd label (`ec+3`, `qc+3`, `qaac`, etc.)
- `mIsAtmos`
- `mIsOARMode`
- output channel count
- AudioQueue spatialization state
- AUSpatialMixer algorithm
- route capability

## Current best user-facing recommendation

For Apple TV+ content:

> Use TV.app streaming. It remains the known path with the special app-level spatial-rendering flag.

For local files on MacBook speakers:

> Test QuickTime Player against TV.app local playback by ear. QuickTime may be the best Apple-native local-file audio path observed so far, because it explicitly enables AudioQueue spatialization and AUSpatialMixerV2 for the local `ec+3` Atmos file.

For local files where library workflow or subtitle handling matters:

> TV.app local playback is still good: it decodes Atmos, enters OAR mode, and shows lower-level spatialization. It just has not shown the TV.app HLS `qc+3` app-level flag.

## Open question

Does QuickTime Player actually sound better than TV.app local playback on MacBook Pro Speakers?

Logs suggest it is plausible. They do not prove it.

The next step is a controlled A/B listening test, or adding a QuickTime capture mode to `dolby-tool` so future reports can compare TV.app local, QuickTime local, and Apple HLS with the same renderer-layer vocabulary.
