# Issue 8: ec+3 vs qc+3 Playback Paths

## Environment

- Date: 2026-05-22
- macOS: 26.5 (25F71)
- Mac model: Mac15,6
- TV.app: 1.6.5
- Output route tested: MacBook Pro Speakers, 2 channels, 48000 Hz, built-in transport
- External route coverage: not completed; no external output route was visible to `system_profiler SPAudioDataType`, `SwitchAudioSource` is not installed, and Bluetooth listed `JBL Tune 720BT` as nearby but not connected

## Short Conclusion

On the built-in MacBook speakers, Apple TV+ HLS and the local TV.app file both reach Apple's CoreAudio spatial machinery: both show 16-channel Dolby-family decode paths, `Spatialization Eligible yes`, `Spatialization yes`, `SpatializationManager` activity, `ACDDPAtmosDecoder` Atmos/OAR states, built-in-speaker route metadata, and head tracking disabled.

That means there is still no evidence that `ec+3` is inherently better than `qc+3`, and `qc+3` remains best interpreted as an Apple/CoreMedia runtime label for the HLS path whose source variants advertise `ec-3`.

There is one important renderer difference in the built-in-speaker logs: TV.app's `mediaFormatinfo` line says the HLS `qc+3` Dolby Atmos path "is rendering spatial audio", while the local `ec+3` Dolby Atmos line says "is not rendering spatial audio". Other local lines still report spatialization enabled/status active, so this is not enough by itself to prove Apple TV+ gets a privileged renderer. It is enough to justify surfacing a "Spatial renderer evidence" section and repeating the test on AirPods / headphones / HDMI.

## Evidence Table

Captures were run with `dolby_tool.tvlog.LogCapture` while driving TV.app through Computer Use.

| Source | Title / item | Output route | Decoded FourCC | Source audio label | Runtime audio | Channels | Spatialization eligible | Spatialization active | Head tracking | Renderer hints | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Apple TV+ / HLS | F1 The Movie | MacBook Pro Speakers | `qdh1` in first run, HLS variants include `dvh1` | HLS variants advertise `ec-3`, `audio-atmos`, plus stereo `mp4a` | `qaac`, then `qc+3` | `qaac ch=2`, `qc+3 ch=16` | yes | no on `qaac`, yes on `qc+3` | off (`headTracking = 0`, `prefersHeadTrackedSpatialization = 0`) | `ACDDPAtmosDecoder mIsAtmos = 1`, `mIsOARMode = 1`; `MEMixerChannel qc+3 ch=16 mContentspatializable=1 mSpatializationStatus=2`; `mediaFormatinfo qc+3 Dolby Atmos ... is rendering spatial audio`; route built-in speakers | Strongest built-in renderer evidence is for `qc+3 ch=16`; stereo `qaac` is an observed alternate/fallback and is not the best path |
| Local TV.app file | The Boys S5E8, "Blood and Bone" | MacBook Pro Speakers | `dvh1` | Local file runtime decoder reports E-AC-3 / Atmos path | `ec+3` | `ec+3 ch=16` | yes | yes | off (`headTracking = 0`, `prefersHeadTrackedSpatialization = 0`) | `ACDDPAtmosDecoder mIsAtmos = 1`, `mIsOARMode = 1`; `MEMixerChannel ec+3 ch=16 mContentspatializable=1 mSpatializationStatus=2`; `SpatializationManager spatialization = 1`; `mediaFormatinfo ec+3 Dolby Atmos ... is not rendering spatial audio`; route built-in speakers | Mixed renderer evidence: lower-level CoreAudio spatial status is active/spatializable, but app-level `mediaFormatinfo` says not rendering spatial audio |

The issue body also included representative prior captures matching this pattern:

| Source | Decoded FourCC | Current audio | Best observed audio | Observed source note |
| --- | --- | --- | --- | --- |
| Local file | `dvh1` | `ec+3 ch=16` | `ec+3 ch=16` | Dolby Vision active |
| Apple TV+ / HLS | `dvh1` | `qc+3 is decodable ch=16` | `qc+3 is decodable ch=16` | Dolby Vision active; observed `qaac`/`aacp ch=2` and `qc+3 ch=16` |

## Parser Behavior

- `qc+3` is preserved as its own audio token instead of normalized to `ec+3`.
- `ec+3`/`ec-3`/`ec3` and `qc+3` with at least 16 channels are ranked in the same top observed-audio tier.
- `qc+3` is not marked as confirmed Atmos unless separate spatialization evidence exists.
- `qaac` and `aacp` are treated as AAC-like stereo fallback or alternate observations when reported with 2 channels.
- Apple-style HLS variant lines such as `FigAlternate(...):[0x...] ... [AudioGroup ...] [dvh1...,ec-3]` are parsed for bitrate, resolution, codec, video range, HDCP, and frame rate.
- TV.app audio lines are parsed for non-adjacent route/spatial fields, including `Spatialization Eligible`, `Spatialization`, and `SampleRate`.
- Renderer hint lines are parsed narrowly for TV.app `mediaFormatinfo`, `SpatializationManager` power events, route lines, `ACDDPAtmosDecoder` subtype/state, `MEMixerChannel` spatial status, and `AVCFPlayerItemSpatialAudioRenderingDidChangeNotification`.

## Answers

1. Does `qc+3` appear only for Apple TV+ / HLS streams?
   - In these captures, `qc+3 ch=16` appeared on Apple TV+ / HLS only.
   - The local file used `ec+3 ch=16`, not `qc+3`.

2. Does `ec+3` ever appear for Apple TV+ / HLS playback?
   - The Apple TV+ HLS variant metadata advertised `ec-3` in `AudioGroup audio-atmos...` variants.
   - The runtime audio playback event still reported `qc+3 ch=16`, not `ec+3`.
   - CoreAudio decoder internals may still show `ec+3` subtype while the TV.app runtime audio label is `qc+3`.

3. Do `ec+3 ch=16` and `qc+3 ch=16` show the same spatialization / Atmos / route metadata?
   - On built-in speakers, both were `ch=16` and `Spatialization Eligible yes`.
   - Both raw audio lines also included `Spatialization yes`.
   - Both showed `ACDDPAtmosDecoder mIsAtmos = 1`, `mIsOARMode = 1`, built-in-speaker route metadata, head tracking off, and `MEMixerChannel ... mContentspatializable=1`.
   - The clearest difference is app-level `mediaFormatinfo`: HLS `qc+3` said "is rendering spatial audio", while local `ec+3` said "is not rendering spatial audio". Because local also showed active lower-level spatialization, this is a lead, not final proof.

4. Does the selected output device change the reported token?
   - Not fully answered. Only built-in speakers were available during this run.
   - External route testing is still required for AirPods / HDMI / Bluetooth / DAC behavior.

5. Is there evidence that `ec+3` is higher quality than `qc+3`?
   - No. The token name alone is not evidence of higher quality.
   - Both built-in-speaker captures showed 16-channel spatialization-eligible playback and Atmos decoder activity.
   - The Apple TV+ HLS manifest layer still advertised `ec-3` Atmos variants while the runtime event exposed `qc+3`, which supports treating `qc+3` as a runtime/CoreMedia representation rather than a downgrade.

6. Is `qc+3` likely an Apple-private/CoreMedia runtime label?
   - Yes. That is the best-supported current label: an Apple/CoreMedia Dolby-like runtime path for TV.app HLS playback.
   - The UI should not imply that `qc+3 ch=16` is automatically worse than `ec+3 ch=16`.

7. Does Apple TV+ appear to get extra hidden spatial/audio functionality over local TV.app files?
   - Not proven.
   - The built-in-speaker logs do show one possible Apple-native advantage: `mediaFormatinfo` says HLS `qc+3` is rendering spatial audio, while the local `ec+3` sample says it is not.
   - Counterpoint: the local path still shows `Spatialization yes`, `SpatializationManager spatialization = 1`, `ACDDPAtmosDecoder mIsAtmos = 1`, OAR mode, and `MEMixerChannel ... mSpatializationStatus=2`.
   - The conservative interpretation is that both enter the Apple renderer stack, but the final app-level spatial-rendering flag may differ. This must be repeated on the same external route before claiming Apple-native streams are privileged.

## Interpretation

- `ec+3` vs `qc+3`: current evidence supports treating `ec+3` as the source/container or local FigFilePlayer E-AC-3/Atmos label, and `qc+3` as TV.app/CoreMedia's runtime label for the HLS Dolby-family path. HLS source variants still advertised `ec-3`.
- MacBook speakers are not receiving a real 16-speaker layout. They are a 2-channel built-in route receiving a rendered/spatialized output derived from a 16-channel Dolby-family decode path.
- `qaac` / `aacp` observations should be treated as stereo alternate or fallback states unless they are the only audio state observed.
- Head tracking was off in these built-in-speaker runs. That is expected for MacBook speakers and does not answer AirPods behavior.
- Apple-native streams may have a different app-level spatial-rendering state on the built-in route, but the evidence is incomplete and partly contradictory.

## UI / Parser Recommendation

- Label `ec+3` as a standard Dolby Digital Plus / E-AC-3 path.
- Label `qc+3` as an Apple/CoreMedia Dolby-like runtime path, not as a warning state by default.
- Label `qaac` and `aacp` as AAC-like 2-channel fallback or alternate observations when they appear with 2 channels.
- Keep "current audio" and "best observed audio" distinct, because the latest event can be a stereo fallback even when a higher-channel path was observed earlier in the capture.
- Add a "Spatial renderer evidence" section to TV Capture showing output route, app-level spatial rendering flag from `mediaFormatinfo`, `SpatializationManager` spatialization/stereo-upmix/head-tracking state, Atmos decoder state/subtype, mixer spatializable/status hints, and spatial-rendering-change notifications.
- Do not collapse renderer evidence into the `ec+3`/`qc+3` pill. The renderer evidence is a separate question from the codec token.

## Follow-Up Work

- Run the remaining external-route matrix:
  - Apple TV+ / HLS on one external route, preferably Apple headphones with Spatial Audio.
  - Local Dolby Vision / Atmos-capable file on the same external route.
- Repeat the built-in-speaker local capture once more and check whether `mediaFormatinfo ec+3 ... is not rendering spatial audio` is stable or a timing artifact.
- Add a non-TV.app control only after identifying the local file path reliably; compare whether IINA/mpv expose any Apple `SpatializationManager` / `ACDDPAtmosDecoder` path or just ordinary stereo/downmix output.
- If future captures expose additional route log lines that are not currently parsed, add narrow regex support using the raw captured lines as fixtures.
- Do not claim `ec+3` is better than `qc+3` unless a future capture supplies concrete bitrate, layout, sample-rate, substream, or renderer evidence.
