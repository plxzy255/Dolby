# Next steps and edge cases

Grouped by cost. Each item: what to try, what we'd learn, and what would
falsify it.

## Priority 0 — settle the 2026-05-23 contradiction

The N2 baseline capture taken on 2026-05-23 shows the system layer
reporting spatial = on for TV.app local playback (allow mask 0x7, mixer
spatializable=1, SpatialMgr spatialization=1, source `'mlti'`). Only
`mediaFormatinfo` still says false. The earlier dtrace data had the AVF
intersection resolving to 0. These cannot both be true today.

Two cheap disambiguations:

### P0a. Audible A/B
- TV.app local vs QuickTime+HLS+local (`dolby-tool hls-package-capture`)
  on the same file, same MBP speakers, volume-matched.
- If they sound the same → TV.app local is actually rendering spatial
  audio and the `mediaFormatinfo` line is cosmetic. This effectively
  resolves the user's goal.
- If TV.app local sounds narrower or non-spatialized while QuickTime+HLS
  feels enveloping → the `mediaFormatinfo` flag is accurate; the
  positive system-layer signals come from a path the actual output
  isn't using.

### P0b. Fresh dtrace re-attach
- Requires Recovery boot + `csrutil enable --without debug --without
  dtrace`.
- Re-run `harness/spatial-probes.d` against TV.app playing the local
  file. Capture: `AVCFPlayerItemSetAllowedAudioSpatializationFormats`
  arg1, `playerItem_SetAllowedAudioSpatializationFormats` arg1
  (post-narrowing value), `FPSupport_…Eligibility` return,
  `AudioQueueObject::AllowsSpatialization` return.
- If `AllowsSpatialization` now returns 1 (and the older trace had 0):
  the AVF gate is materially different now. We've improved without
  realizing it.
- If `AllowsSpatialization` still returns 0: the visible-log
  signals (mask=0x7, mixer status=2) are from a non-load-bearing path
  and the AVF gate is still active — just not visible in `log stream`.

## Cheap, untested (do these first)

> N2 (defaults probes) is **done** as of 2026-05-23: all four candidate
> keys — `preferredDolbyAtmosPlaySetting`, `multichannelAudioStrategy`,
> `downloadDolbyAtmos`, `downloadMultichannel` — are no-ops on the
> local-file spatial path. See `03_evidence_matrix.md`.

### N1. Capture the actual `spatialPreference` integer TV.app passes
- Probe `-[AVPlayerItem(MediaPlaybackCore) mpc_updateAVAudioSpatializationFormatsForPlayerAudioFormat:spatialPreference:]`
  on TV.app for local vs HLS, recording `arg2` (and `arg1` audio format).
- We know it strips Multichannel for local; we don't know the integer
  identity. If it's a small enum, the value may be writable via
  `defaults` or via a hook.
- Requires SIP debug+dtrace off (already used in earlier sessions).
- Note: now overlaps with P0b. Combine into one dtrace session when SIP
  is next adjusted.

### N2. ~~Probe TV.app `defaults` keys~~ — DONE (negative)
- Tested 2026-05-23: `preferredDolbyAtmosPlaySetting` (1, 2, 3),
  `multichannelAudioStrategy` (1, 2), `downloadDolbyAtmos`,
  `downloadMultichannel`. None changed any signal. Captures in
  `captures/n2_defaults/`.

### N3. Investigate the undocumented `0x4` bit
- Consistently set in TV.app's filtered allow mask on MBP speakers.
  Never investigated. Walk the AVF code path for the value's origin —
  is it a route-capability bit AVF adds, or a TV.app-only marker?
- Test what `setAllowedAudioSpatializationFormats:0x4` alone does in
  SpatialProbe.

### N4. SpatializationManager source-token mechanism
- What causes a process to register `'mlti'` vs `'?src'`? SpatialProbe
  reaches `'mlti'` on MBP speakers with no entitlements, so it's not
  entitlement-gated. Candidates: Info.plist keys, NSAudioSession
  category, `AVAudioSession` config, presence of an Atmos-eligible
  format-description.
- Probe `SpatializationManager::registerApp` (or equivalent symbol —
  need to resolve) for the registration call path.

### N5. AirPods / Beats route
- Untested across every path. Apple's "Spatial Audio" headphones are
  the only route besides MBP speakers known to register spatial-capable.
- Run SpatialProbe + TV.app local on AirPods Pro/Max. If TV.app local
  still fails on AirPods, the route layer is not the gate; if it
  succeeds, the gate is route-dependent.

### N6. Music.app local Atmos `.m4a`
- Atmos `.m4a` in Music.app library. Apple's Music app might or might
  not be subject to the same `mpc_updateAVAudioSpatializationFormats…`
  call site that TV.app uses. Cheap second-app comparison.

### N7. Safari retry with HTTPS + user-gesture autoplay
- Previous Safari failure was cold-load. Serve HTTPS (self-signed cert
  trusted in Keychain) + a page with explicit click-to-play, then
  capture. Safari uses CoreMedia HLS via WebKit; if it engages
  `FigStreamPlayer` like QuickTime did, it's another path.

## Medium cost

### M1. Install Apple HLS Tools (`mediafilesegmenter` + `mediastreamvalidator`)
- `developer.apple.com/download/applications/`. Apple-canonical HLS
  output. Pair with `AVAssetDownloadTask` to produce a `.movpkg` that
  most closely resembles Apple-managed packages. Still unlikely to
  pass TV.app's content-identity check, but it removes the
  packaging-quality variable from the experiment.

### M2. Wider Apple TV+ Atmos title sweep for `Complete=YES`
- 2/2 inspected titles (`Grass Lands`, `Ted Lasso S1E1`) lack complete
  top-level main Atmos despite advertising it. Download 3–5 more
  Atmos-marked titles at Highest Quality on this account, scan with
  `movpkg-scan`. If 0/N are complete, the offline Atmos pipeline on
  this account/region is effectively broken; if some are complete,
  capture playback on those.

### M3. Inspect a known-good `.movpkg` byte-for-byte
- Compare boot.xml, root.xml, persisted segment layout, manifest
  signatures, anything Apple-specific between (a) a `Complete=YES`
  Apple-managed package if we can obtain one, and (b) our externally
  built `AVAssetDownloadTask` package. Identify the trust signal that
  TV.app's handler is checking.

### M4. Hook `mpc_updateAVAudioSpatializationFormats…` in a custom AVPlayer
- Inside a custom app, swizzle/intercept the
  MediaPlaybackCore category method. Force-pass `0x7` as the new mask
  regardless of `spatialPreference`. If a non-TV.app process exhibits
  the same call site (i.e., the category method also fires in our app
  via MediaPlaybackCore), this experiment isolates the call as the
  single lever. Falsification: if MediaPlaybackCore is TV.app-private,
  the symbol won't be reachable.

### M5. Local file → AVAggregateAssetDownloadTask
- Variant of A3 using the aggregate download task with explicit Atmos
  audio variant selection. May produce a more "Apple-blessed" package
  than the plain `AVAssetDownloadTask`. Still likely fails the trust
  check, but cheap once a fragmented HLS source is built.

## Expensive / structural

### X1. TV.app patching
- Requires weakening SIP (sealed system snapshot, library validation,
  hardened runtime, code-signing). Not in scope for the user's
  daily-driver Mac.

### X2. Replace TV.app with a custom AVPlayer app
- Not a "TV.app does it" solution. We already have SpatialProbe as a
  diagnostic and QuickTime+HLS as a daily-usable player. A
  feature-complete library-app replacement is a separate project.

## Edge cases nobody has looked at yet

These are gaps I noticed while consolidating the older reports. None of
them have been tested.

- **HDMI/AVR route**: not tested. An external Atmos AVR might register
  as spatial-capable in SpatialMgr and could change TV.app's
  `spatialPreference` decision (it might choose a different value when
  the route advertises multichannel capability).
- **Aggregate Audio Device**: route an Atmos-capable HDMI output through
  an Aggregate Device. TV.app may see "MBP speakers" routing layer
  while audio actually goes elsewhere. Diagnostic only.
- **TV.app library `.movpkg` symlinks**: TV.app library lives at
  `~/Movies/TV/Media.localized/`. Inserting a symlink to our externally
  built `.movpkg` might bypass the "open from outside library" path
  TV.app rejected. Possibly probed but not captured in earlier reports.
- **Sidecar `Info.plist` next to local file**: Apple's media library
  sometimes consults sidecars. Could carry a custom UTI hint. Long
  shot.
- **Local AAC Atmos in `.m4a`**: untested format. Atmos JOC over AAC
  (Apple Music's path). If TV.app's call site treats AAC Atmos
  differently from EAC-3 Atmos, that's a lever.
- **TV.app launched via `LSOpenURLsWithRole` Editor role**: different
  LaunchServices role on the open might engage a different code path.
  Cheap to try; very long shot.
- **`com.apple.private.tcc.allow` injection** via TCC.db edits: not
  feasible with SIP; listed only to mark it as explicitly out of scope.
- **macOS 26.5 vs other versions**: untested on macOS 25.x or earlier.
  The call site name (`mpc_updateAVAudioSpatializationFormatsForPlayerAudioFormat:spatialPreference:`)
  may not exist in older versions; the gate might be at a different
  layer there.
- **TV.app + AirPlay receiver as a way to launder the route**: send
  audio to an AirPlay receiver and see whether the SpatialMgr `App`
  binding now sees a different effective route.

## Suggested execution order

If we only have a session for ~1–2 hours:

1. **P0a (audible A/B)** — could resolve the user's goal in one listening test
2. N5 if AirPods available
3. N6 (Music.app)
4. N3 / N4 (need SpatialProbe variants)

If we can boot to Recovery and re-disable debug/dtrace SIP:

5. **P0b + N1 + N3 + N4** (single dtrace session) — settles the gate
   model, captures `spatialPreference` arg, traces `0x4` bit origin,
   and traces SpatializationManager source-token registration

If we have a full day:

6. M2 (Atmos title sweep)
7. M1 (Apple HLS Tools install + canonical package)
8. M3 (.movpkg byte diff)
9. M4 (MediaPlaybackCore hook in a custom AVPlayer)
