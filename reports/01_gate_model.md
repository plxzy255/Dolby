# The multi-layer spatial-rendering gate

> **Caveat (2026-05-23):** A fresh N2-probe baseline capture (TV.app local,
> MBP speakers, same file) shows mask=0x7, mixer `mContentspatializable=1
> status=2`, SpatialMgr `spatialization=1`, source `'mlti'`. Only
> `mediaFormatinfo` is still false. This is **inconsistent** with the
> dtrace data below, which had the intersection resolving to 0.
> Possibilities: (a) the system layer has been changed in a recent
> OS/TV.app build, (b) the AVF re-narrowing still occurs but isn't in
> the visible log surface, (c) `mediaFormatinfo` reports a TV.app-internal
> state independent of CoreAudio. Resolving this requires a re-attached
> dtrace pass; instructions in `06_next_steps_and_edge_cases.md`.

Evidence base: live dtrace session on 2026-05-23 (SIP debug/dtrace
restrictions disabled), TV.app 1.6.5, macOS 26.5 (25F71), Mac15,6, MBP
built-in speakers (2ch) as primary route. Cross-validated against
SpatialProbe Run B (same hardware, same file, succeeded) and the
QuickTime + local-HLS capture (FigStreamPlayer path on a non-TV.app
process).

## The gate is not one check; it is a stack

```
   AVF layer (AVPlayerItem)
       ↓ allowedAudioSpatializationFormats           (caller-set 0x7;
                                                      AVF re-narrows per route)
       ↓ FPSupport_GetAudioFormatDescriptionSpatializationEligibility
                                                     (format-side mask)
       ↓ AudioQueueObject::CheckSpatialization       (intersection)
       ↓ AudioQueueObject::AllowsSpatialization      (0/1 verdict to caller)
   ─── crossing into AudioToolbox SpatialMgr ───
       ↓ SpatializationManager per-App / per-route capability
       ↓ spatialAudioSources registration            ('mlti' vs '?src')
       ↓ MEMixerChannel content-eligibility          (channels + format)
       ↓ AtmosDecoder mode                            (ec-3 6ch passthrough
                                                       vs ec+3 16ch JOC)
       ↓ "is rendering spatial audio" app-level flag
```

A capture can fail at any layer. SpatialProbe Run A (wired headset) failed
at the SpatializationManager per-route layer despite AVF returning
`AllowsSpatialization = 1`. TV.app local fails at the AVF intersection
layer. So a single check ("does AVF think this can spatialize?") is not
sufficient; you have to look at the whole stack.

## Layer 1 — AVF allow mask

The bitmask matches the public `AVAudioSpatializationFormats` NS_OPTIONS:

- `0x1` = MonoAndStereo
- `0x2` = Multichannel
- `0x3` = MonoStereoAndMultichannel
- `0x4` = **undocumented**; consistently set in TV.app's filtered mask on
  this route. Never investigated. See `06_next_steps_and_edge_cases.md`.

Callers (TV.app, SpatialProbe) initially set `0x7`. AVF normalizes against
the current route. On MBP speakers (2ch), Multichannel is stripped on the
local path:

```
LOCAL (TV.app):  set 0x7  →  normalized 0x5
LOCAL (SpatialProbe): set 0x3 (explicit)  →  normalized 0x3
HLS  (TV.app):  set 0x7  →  normalized 0x5
                          →  _updateAllowedAudioSpatializationFormatsFromFigItem
                          re-adds 0x2 from FigItem manifest metadata
                          →  effective 0x7
```

Key call sites (resolved against the dyld shared cache):

- `AVCFPlayerItemSetAllowedAudioSpatializationFormats` (AVFoundationCF) —
  TV.app's CF path
- `-[AVPlayerItem setAllowedAudioSpatializationFormats:]` (AVFCore) —
  Swift/AVF path (SpatialProbe)
- `-[AVPlayerItem _updateAllowedAudioSpatializationFormats]` (AVFCore) —
  player-side normalization; **fires on local items too**, contrary to an
  earlier reading
- `-[AVPlayerItem _updateAllowedAudioSpatializationFormatsFromFigItem]`
  (AVFCore) — HLS-only; reads Atmos hints from the FigItem manifest
- `-[AVPlayerItem(MediaPlaybackCore) mpc_updateAVAudioSpatializationFormatsForPlayerAudioFormat:spatialPreference:]`
  — this is where TV.app picks the `spatialPreference` value that strips
  Multichannel for local items. The integer it actually passes has not
  been captured; see `06_next_steps_and_edge_cases.md`.

## Layer 2 — FPSupport format eligibility

`FPSupport_GetAudioFormatDescriptionSpatializationEligibility`
(MediaToolbox) returns a bitmask of formats the audio is eligible to
participate in. Observed returns:

- Local EAC-3 Atmos 16ch: `0x2` (multichannel-only)
- HLS initial stereo variant: `0x1` (mono-stereo only)
- HLS Atmos variant after ABR: `0x2` (transitions; the FigItem re-add
  brings Multichannel back into the allow mask in time)

## Layer 3 — AudioQueue intersection

`AudioQueueObject::CheckSpatialization` evaluates
`allowedAudioSpatializationFormats ∩ FPSupport_eligibility`. On the 2ch
route:

```
TV.app local:    allowed 0x5 ∩ eligible 0x2 = 0x0  →  spatial false
TV.app HLS:      allowed 0x7 ∩ eligible 0x1 = 0x1  →  spatial true
SpatialProbe:    allowed 0x3 ∩ eligible 0x2 = 0x2  →  spatial true
```

`AudioQueueObject::AllowsSpatialization` exposes the resulting 0/1 to
callers. **This is not the final gate**: SpatialProbe Run A returned 1
here and still failed downstream.

## Layer 4 — SpatializationManager per-app/per-route

`SpatializationManager.cpp:184` posts a binding record:

```
Spatial info for binding = Default-Output:
  App = <process name>
  Route = built-in speakers  | not capable of spatialization
  maxSpatializableChannels = 16 | 0
  spatialAudioSources = [ 'mlti' ] | [ '?src' ]
```

`'mlti'` (multi) is the recognized Atmos source token. `'?src'` is the
unknown sentinel. SpatialProbe Run B on MBP speakers got `'mlti'` and
spatialized; Run A on a wired headset got `'?src'` and did not. The
mechanism that registers a recognized source ID for an app is **not
understood**. It is per-app (the `App` key proves that) but it is not
gated by the entitlements TV.app holds, since SpatialProbe (an ad-hoc
binary with no entitlements) also reaches `'mlti'` on built-in speakers.

## Layer 5 — MEMixerChannel content eligibility

`MEMixerChannel.cpp:3273/3300` evaluates the runtime format:

```
6-channel ec-3:   mContentspatializable=0, mSpatializationStatus=1  (rejected)
16-channel ec+3:  mContentspatializable=1, mSpatializationStatus=2  (accepted)
```

The transition between these two states is route-and-allow-mask dependent.
The Atmos JOC decoder emits `ec+3` 16ch when the route is spatial-capable
*and* the allow mask permits Multichannel. Otherwise it stays in `ec-3`
6ch passthrough. **The earlier `ec+3` (HLS) vs `ec-3` (local) association
was a confound** — Run B is a local file producing `ec+3` 16ch. The token
follows the route+mask, not the source container.

## Final flag

The app-level `mediaFormatinfo ... is rendering spatial audio = true/false`
line in `com.apple.TV:ampplay` reflects the result of the whole stack as
TV.app's cmplayer sees it. It is one signal, not the only spatialization
signal — lower-level Atmos / OAR / AudioQueue / mixer state can be active
even when this flag is false.

## What this changes vs older notes

- The earlier hypothesis "FigFilePlayer vs FigStreamPlayer is the gate"
  was directionally right but at the wrong layer. The engine difference
  matters because FigStreamPlayer triggers
  `_updateAllowedAudioSpatializationFormatsFromFigItem`, which re-adds
  Multichannel to the allow mask. The engine itself is not a check.
- The `ec+3` vs `qc+3` runtime token was treated as a gate. It is a
  downstream consequence of the JOC decoder mode, which depends on the
  intersection result.
- AVF intersection is **necessary but not sufficient**. SpatialMgr and
  MEMixerChannel still get a vote.
