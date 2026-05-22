# Follow-up report: Apple HLS vs local TV.app spatial renderer behavior

## Summary

I tested Apple TV+ / HLS and local TV.app playback across MacBook speakers, wired JBL, and Bluetooth JBL routes.

The main finding is that the interesting difference is not `ec+3` vs `qc+3`. It is the app-level spatial-rendering flag from `mediaFormatinfo`.

On MacBook Pro Speakers, Apple TV+ / HLS reached `qc+3 ch=16` and showed `mediaFormatinfo ... rendering spatial audio = true` during capture. The local TV.app file reached `ec+3 ch=16` and showed lower-level Dolby/spatial machinery, but its `mediaFormatinfo` line remained `rendering spatial audio = false`.

This suggests Apple TV+ / HLS may get a different or more complete app-level spatial renderer state on built-in MacBook speakers than local TV.app files. This is not final proof yet because the local file still showed `Spatialization yes`, `SpatializationManager spatialization=true`, Atmos decoder activity, OAR mode, and mixer spatializable status.

## Built-in speaker results

### Apple TV+ / HLS

- HLS source variants advertised `ec-3` Atmos audio groups.
- Runtime audio reported `qc+3 ch=16`.
- App-level spatial flag reached `rendering_spatial_audio = true`.
- SpatializationManager reported spatialization active.
- Atmos decoder reported Atmos/OAR state.
- Mixer reported `qc+3 ch=16` spatializable.

### Local TV.app file

- Runtime audio reported `ec+3 ch=16`.
- App-level spatial flag reported `rendering_spatial_audio = false`.
- SpatializationManager still reported spatialization active.
- Atmos decoder reported Atmos/OAR state.
- Mixer reported `ec+3 ch=16` spatializable.

## JBL wired/Bluetooth results

The JBL tests did not show an Apple-native advantage.

For Apple TV+ / HLS on JBL, the selected HLS audio path became stereo `mp4a.40.2` / `qaac ch=2`, not the Atmos `ec-3` / `qc+3 ch=16` path.

For the local file on JBL, playback also did not show a spatialized Atmos path. It fell to non-spatial `ec-3` / 6-channel style mixer evidence.

This suggests non-Apple JBL wired/Bluetooth routes are not useful for proving MacBook speaker spatial rendering quality, but they do confirm that output route strongly affects audio selection.

## Interpretation

Current best interpretation:

- `ec+3` is the local/container or FigFilePlayer E-AC-3 / Dolby path.
- `qc+3` is Apple/CoreMedia's runtime label for Apple HLS Dolby-family playback.
- Apple HLS can advertise `ec-3` at the source/HLS layer while exposing `qc+3` at runtime.
- `qc+3` should not be treated as worse than `ec+3`.
- The real question is whether `mediaFormatinfo rendering_spatial_audio=true` is only available for Apple-native HLS.

## Current conclusion

There is now a plausible lead that Apple TV+ / HLS gets app-level spatial rendering on MacBook speakers while local TV.app `ec+3` playback may not. This is not fully proven because local playback still enters lower-level spatial/Atmos machinery.

The next test should repeat only built-in-speaker playback with stable capture timing:
start playback, wait for playback to stabilize, then capture 20–30 seconds without stopping or changing routes during the capture.

If Apple HLS repeatedly shows `rendering_spatial_audio=true` and local repeatedly shows `rendering_spatial_audio=false`, then the tool should surface this as a likely Apple-native spatial-renderer advantage.
