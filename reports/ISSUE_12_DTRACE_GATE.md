# Issue 12 dtrace findings: the spatial-rendering gate

Companion to `ISSUE_12_LOCAL_SPATIAL_RENDERING.md`,
`ISSUE_12_CREATIVE_POSSIBILITIES.md`, and `ISSUE_12_EXPERIMENT_RESULTS.md`.
This report documents live dtrace observations from a single session on
2026-05-23 that pin down the exact decision point at which TV.app's
`mediaFormatinfo ... is rendering spatial audio` flag is set.

## Environment

- Date: 2026-05-23
- macOS: 26.5 (25F71), Mac15,6
- TV.app: 1.6.5 (PID 2446 during HLS phase)
- Route: MacBook Pro Speakers, 2ch, built-in
- SIP config: `Debugging Restrictions: disabled`, `DTrace Restrictions: disabled`
  (set via `csrutil enable --without debug --without dtrace` from Recovery)

Both `task_for_pid` and dtrace pid-provider attach to Apple-signed apps
require both restrictions off. With them off, dtrace's `pid$target`
provider resolves symbols from the dyld shared cache for any loaded
framework.

## What was traced

`pid$target` probes were set on the following resolved symbols in
MediaToolbox, AudioToolbox, AVFoundationCF, AVFCore, and
MediaPlaybackCore:

- `FigPlayerStreamCreateWithOptions` / `FigPlayerFileCreateWithOptions`
  (MediaToolbox) — pipeline engine entry
- `FPSupport_GetAudioFormatDescriptionSpatializationEligibility`
  (MediaToolbox) — format-level eligibility check
- `AVCFPlayerItemSetAllowedAudioSpatializationFormats` /
  `playerItem_SetAllowedAudioSpatializationFormats` (AVFoundationCF)
- `-[AVPlayerItem _updateAllowedAudioSpatializationFormatsFromFigItem]`
  (AVFCore)
- `AudioQueueObject::CheckSpatialization` /
  `AudioQueueObject::AllowsSpatialization` (AudioToolbox)
- `ShouldRouteBypassSpatialization` (AudioToolbox)
- `SpatializationManager::EnableInternalSpatializationAUs` (AudioToolbox)
- `MEMixerChannel::ConfigureSpatializationUnit` / `...UnitFormat`
  (AudioToolbox)

A 25–30s window captured each side. Local trace was started cold against
TV.app, then "Blood and Bone" (the same local file used in earlier
Issue 8 / Issue 12 captures) was played. HLS trace started cold, then
Apple TV+ HLS content was played.

## The decisive observation

Both phases captured these four events for their respective
AVPlayerItem at creation time:

```
LOCAL (Blood and Bone, FigFilePlayer path):
  AVCFPlayerItemSetAllowedAudioSpatializationFormats  arg1 = 0x7
  playerItem_SetAllowedAudioSpatializationFormats     arg1 = 0x5
  FPSupport_GetAudioFmtDesc_SpatEligibility           ret  = 0x2
  AudioQueueObject::CheckSpatialization (fires, but allowed ∩ eligible = 0)

HLS (Apple TV+, FigStreamPlayer path):
  AVCFPlayerItemSetAllowedAudioSpatializationFormats  arg1 = 0x7
  playerItem_SetAllowedAudioSpatializationFormats     arg1 = 0x5
  FPSupport_GetAudioFmtDesc_SpatEligibility           ret  = 0x1
  AudioQueueObject::CheckSpatialization (fires, allowed ∩ eligible = 0x1)
```

The bitmask values map to the public `AVAudioSpatializationFormats`
NS_OPTIONS enum:

- `0x1` = `AVAudioSpatializationFormatMonoAndStereo`
- `0x2` = `AVAudioSpatializationFormatMultichannel`
- `0x3` = `AVAudioSpatializationFormatMonoStereoAndMultichannel`
- `0x4` = private/undocumented bit (consistently present in
  TV.app's filtered mask on this route — likely an internal
  capability flag, not a public format selector)

The gate is the **intersection** `allowedAudioSpatializationFormats ∩
FPSupport_eligibility` evaluated inside the AudioQueue's
`CheckSpatialization` method. When the intersection is empty, the
renderer reports `is rendering spatial audio = false`.

## Why the masks differ

### `allowedAudioSpatializationFormats` (player side)

TV.app calls `AVCFPlayerItemSetAllowedAudioSpatializationFormats` with
`0x7` for both local and HLS items — the app proposes "all formats
allowed."

Within AVFoundationCF / MediaPlaybackCore, an internal step normalizes
this value against the current output route. On MacBook Pro Speakers
(2ch built-in), Multichannel (`0x2`) is stripped, leaving `0x5`. This
happens at the same intermediate step for both local and HLS items.

For HLS items only, a second path also runs:
`-[AVPlayerItem _updateAllowedAudioSpatializationFormatsFromFigItem]`.
This method reads format hints from the FigItem (which is HLS-aware)
and can re-add Multichannel to the allow mask when the HLS manifest
declares an Atmos variant. For FigFilePlayer (local), no FigItem-derived
update runs.

### `FPSupport_GetAudioFormatDescriptionSpatializationEligibility` (format side)

`FPSupport` takes a `CMAudioFormatDescription` (or equivalent) and
returns a bitmask of spatialization formats the audio is eligible to
participate in. For the captures:

- The local file's EAC-3 Atmos audio is recognized as multichannel —
  eligibility = `0x2`.
- The HLS variant Apple TV+ first delivered on this route was the
  stereo / mono-stereo variant — eligibility = `0x1`.

(The Apple TV+ HLS path eventually transitions toward Atmos via ABR;
TV.app's `_updateAllowedAudioSpatializationFormatsFromFigItem` re-adds
Multichannel to the allow mask in time for the format eligibility to
intersect.)

### Intersection outcome on a 2ch route

```
LOCAL:  allowed = 0x5, eligible = 0x2  →  intersection = 0x0  →  spatial = false
HLS:    allowed = 0x5, eligible = 0x1  →  intersection = 0x1  →  spatial = true
```

For a hypothetical local file with stereo (not multichannel) audio,
`FPSupport` would return `0x1`, intersect with `0x5` → `0x1`, and
spatial would activate. This explains why the issue is specifically
local multichannel content on a stereo-only route, not local files in
general.

For local multichannel Atmos content to reach the same state as HLS
Atmos on MacBook speakers, either the allow-mask filter needs to keep
Multichannel (`0x2`), or the format eligibility needs to return a mask
that includes `0x1`. The first lever is what
`_updateAllowedAudioSpatializationFormatsFromFigItem` provides for HLS.

## Aggregate divergence (30-second captures)

Functions called only on the HLS side:

- `-[AVPlayerItem _updateAllowedAudioSpatializationFormatsFromFigItem]`
- `-[AVPlayerItem allowedAudioSpatializationFormatsWasSet]`
- `-[AVPlayerItem audioSpatializationAllowedWasSet]`
- plus their `_block_invoke` and `objc_msgSend$` companions

Functions called on both, with higher count on HLS (HLS path cycles
through state more during ABR):

| Function | local | hls |
|---|---|---|
| `FPSupport_GetAudioFormatDescriptionSpatializationEligibility` | 4 | 8 |
| `AudioQueueObject::CheckSpatialization` | 1 | 4 |
| `AudioQueueObject::ResetSpatializationCompression` | 4 | 8 |
| `MEMixerChannel::ConfigureSpatializerHost` | 6 | 8 |
| `MEMixerChannel::StoreSpatializationPreset` | 1 | 4 |
| `SpatializationManager::EnableInternalSpatializationAUs` | 1 | 4 |
| `ShouldRouteBypassSpatialization` | 17 | 29 |

The HLS path engages the AU pipeline four times (consistent with the
`spatial_rendering_changed_count: 4` observed in earlier captures).
The local path engages it once and never recurses.

## Implications

### What this changes about the Issue 12 conclusion

The earlier conclusion ("the gate appears to be the pipeline engine —
FigFilePlayer vs FigStreamPlayer — and the asbdFormatID
`ec+3` vs `qc+3`") was directionally right but at the wrong layer.

- The pipeline engine difference still matters, but only because
  FigStreamPlayer is what triggers
  `_updateAllowedAudioSpatializationFormatsFromFigItem`.
- The `ec+3` vs `qc+3` runtime token is a downstream **consequence**, not
  the gate itself. `qc+3` is what Apple's HLS Dolby-family path
  produces; the spatial flag is set independently by the
  allow ∩ eligible intersection.

The real gate is at the AVFoundation format-intersection layer inside
`AudioQueueObject::CheckSpatialization`, evaluated against
`allowedAudioSpatializationFormats` and the result of `FPSupport`.

### What this means for "make local files render spatial"

For a **custom AVPlayer app** (any non-TV.app process using
AVFoundation directly), the diagnostic result was:

1. Explicitly set
   `[playerItem setAllowedAudioSpatializationFormats:
   AVAudioSpatializationFormatMonoStereoAndMultichannel]` on the
   local-file AVPlayerItem.
2. If the AVF route-filter still strips Multichannel on this hardware
   (likely), the format-side lever is the alternative: present the
   audio to AVF as if it were stereo at the format-description layer
   (a custom AudioTap or a format-description override) so FPSupport
   returns `0x1`, then intersect with `0x5` → `0x1` → spatial.
3. This has diagnostic value for isolating TV.app's behavior, but it
   is not the solution path for this issue. The current path remains
   TV.app / Apple-managed downloads / local playback.

For **TV.app itself**:

- No in-app fix; TV.app is a signed Apple binary and its
  `mpc_updateAVAudioSpatializationFormatsForPlayerAudioFormat:spatialPreference:`
  call site (in MediaPlaybackCore) determines the allow mask for local
  items. That call site picks a `spatialPreference` value that excludes
  Multichannel for local file items on this route.
- The only working path is the original Tier A from
  `ISSUE_12_CREATIVE_POSSIBILITIES.md`: get content into a TV.app
  `.movpkg` carrying Apple-issued content identity so TV.app's
  FigStreamPlayer pipeline takes over.

## Parser recommendations (concrete)

`dolby_tool/tvlog.py` already parses `mediaFormatinfo` lines. The
intersection gate is the actionable signal we want surfaced. Suggested
additions:

1. **Capture the AVPlayerItem allowed-mask transition**. The log
   predicate already catches `process == "TV"`. The internal
   `_updateAllowedAudioSpatializationFormatsFromFigItem` likely emits
   os_log entries we can match — add a regex for that selector and
   record whether it fired during the capture (HLS marker).
2. **Add an `engine_evidence` field** that distinguishes runtime
   signatures of FigStreamPlayer vs FigFilePlayer, since the engine
   is the proxy for the FigItem-update path.
3. **Add a verdict-distinguishing tag** for "allow mask narrower than
   eligibility" if/when the log surface exposes either value
   directly. Today both are internal to AVF and not in the user-visible
   log surface, but if a future macOS update exposes them, the parser
   should track them.

## SpatialProbe harness experiment (2026-05-23)

Falsification condition #1 below was directly tested with a custom
AVPlayer harness (`harness/SpatialProbe`) — a ~80-line Swift executable
that loads "Blood and Bone.mp4" via `AVURLAsset`, sets
`item.allowedAudioSpatializationFormats = .monoStereoAndMultichannel`
(raw 0x3) on the `AVPlayerItem`, and plays. dtrace was attached against
the same probe set as above; `log stream` captured `mediaFormatinfo` /
SpatialMgr lines in parallel.

Two runs were captured:
- **Run A** (2026-05-23 02:58): wired headset route. Spatial output
  failed, as documented in the original write-up of this section
  (kept below).
- **Run B** (2026-05-23 03:07): MacBook Pro built-in speakers route —
  the same route as the TV.app capture. **Spatial output succeeded**
  (`spatialization = 1` in the SpatializationManager power-event log).
  This is the decisive result; see "Run B — success on MBP speakers"
  below.

### What dtrace caught (Swift/ObjC path)

The Swift→ObjC setter chain fired as expected. Walked from the top:

```
objc_msgSend$setAllowedAudioSpatializationFormats:        (SpatialProbe stub)
-[AVPlayerItem setAllowedAudioSpatializationFormats:]     (AVFCore)
_updateAllowedAudioSpatializationFormats                   (AVFCore — local-item variant)
-[AVPlayerItem allowedAudioSpatializationFormatsWasSet]    (AVFCore)
_updateAllowedAudioSpatializationFormats                   (AVFCore, again)
FPSupport_Eligibility RETURN -> 0x2                        (multichannel-only, same as TV.app local)
AudioQueueObject::CheckSpatialization ENTER/RETURN
AudioQueueObject::AllowsSpatialization RETURN -> 0x1       (AVF says: spatialization allowed)
ShouldRouteBypassSpatialization -> 0                       (route not auto-bypassed)
```

Two notes:

- The CF-prefixed probes used in the original TV.app capture
  (`AVCFPlayerItemSetAllowedAudioSpatializationFormats`,
  `playerItem_SetAllowedAudioSpatializationFormats`) did **not** fire.
  TV.app is a CF-based app; the Swift/AVFoundation path goes through
  `AVFCore` (ObjC) and does not load `AVFoundationCF` at all. The
  underlying business logic is the same, just behind different entry
  symbols.
- `_updateAllowedAudioSpatializationFormats` (no FigItem suffix) fires
  on this local item too — i.e., the player-side allow-mask normalization
  is **not** HLS-exclusive. The original report's reading of
  `_updateAllowedAudioSpatializationFormatsFromFigItem` as the
  HLS-specific lever may need re-examination; the FigItem suffix is one
  variant, and the non-suffixed sibling runs for local items.

### What log stream showed (the actual verdict)

`SpatializationManager` and `MEMixerChannel` log entries for the
SpatialProbe process during the same window:

```
SpatializationManager.cpp:184  Spatial info for binding = Default-Output:
  App = SpatialProbe
  Route = not capable of spatialization
  contentType = 'moov'
  overrideSpatialMode = 0
  preferencesVersion = 1
  Spatial preferences: {
    prefersHeadTrackedSpatialization = 0
    prefersLossyAudioSources = 0
    maxSpatializableChannels = 0
    alwaysSpatialize = 0
    spatialAudioSourceCount = 1
    spatialAudioSources = [ '?src' ]
  }
AudioQueueObject.cpp:5080  SetProperty: spatialization disabled,
   client-controlled. Format 6 ch, 48000 Hz, ec-3
MEMixerChannel.cpp:3273  6-channel audiovisual content is NOT eligible
   for spatialization
MEMixerChannel.cpp:3300  mFormatID='ec-3', mNumChannels=6,
   mBestAvailableContentType=3, mContentspatializable=0,
   mSpatializationStatus=1, err=0
```

Three new gate locations surface here, all downstream of AVF:

1. **Per-App / per-route capability** (`SpatializationManager.cpp:184`):
   the route is reported as `not capable of spatialization` with
   `maxSpatializableChannels = 0` for `App = SpatialProbe`. The `App`
   key in the binding suggests this is *per-app*, not just
   per-physical-route. TV.app probably yields a different verdict on
   the same physical hardware.
2. **`spatialAudioSources = [ '?src' ]`**: the source identifier is
   the unknown sentinel `'?src'`. TV.app presumably registers a
   recognized source identifier here (e.g. an Atmos / Dolby-family
   four-CC). The unknown source likely contributes to the
   `not capable` verdict.
3. **MEMixerChannel content eligibility**
   (`MEMixerChannel.cpp:3273/3300`): even ignoring the route verdict,
   6-channel EAC-3 with `mBestAvailableContentType=3` is explicitly
   rejected: `mContentspatializable=0`. This is the format-side gate
   evaluated inside the AU pipeline, distinct from `FPSupport`'s
   format-description eligibility (which returned 0x2 a few frames
   earlier).

### Run B — success on MBP speakers (2026-05-23 03:07)

Same SpatialProbe binary, same file, MBP built-in speakers as the
output route. The SpatializationManager binding is now reported as
spatial-capable:

```
SpatializationManager.cpp:184  Spatial info for binding = Default-Output:
  App = SpatialProbe
  Route = built-in speakers
  contentType = 'moov'
  Spatial preferences: {
    maxSpatializableChannels = 16
    spatialAudioSources = [ 'mlti' ]   # not '?src' — recognized source
  }
MediaToolbox:player  <<<< FigFilePlayer >>>> itemfig_isAtmosSupported:
   YES, because multichannel audio spatialization is allowed
AudioQueueObject.cpp:5080  spatialization enabled, client-controlled.
   Format 16 ch, 48000 Hz, ec+3
AUSpatialMixerV2  [setProperty] spatialization algorithm = 7
MEMixerChannel.cpp:3273  16-channel audiovisual content is eligible for
   spatialization
MEMixerChannel.cpp:3300  mFormatID='ec+3', mNumChannels=16,
   mBestAvailableContentType=3, mContentspatializable=1,
   mSpatializationStatus=2, err=0
SpatializationManager.cpp:1735  Logging power event: pid = 4768,
   name = SpatialProbe, spatialization = 1, stereoUpmix = 0,
   headTracking = 0
```

The relevant comparison against Run A (same harness, wired headset):

| Field                       | Run A (wired headset) | Run B (MBP speakers) |
|---|---|---|
| Route                       | not capable           | built-in speakers    |
| maxSpatializableChannels    | 0                     | 16                   |
| spatialAudioSources         | `'?src'`              | `'mlti'`             |
| Pipeline                    | FigFilePlayer         | FigFilePlayer        |
| Runtime fmt                 | ec-3, 6 ch            | **ec+3, 16 ch**      |
| `mContentspatializable`     | 0                     | 1                    |
| AudioQueue state            | "disabled, client-controlled" | "enabled, client-controlled" |
| SpatialMgr verdict          | spatialization = 0    | **spatialization = 1** |

Two consequential observations:

1. **The earlier report's `ec+3` vs `ec-3` association with HLS vs local
   was a confound.** Run B is a local file (the log explicitly says
   `FigFilePlayer`) and produces `ec+3` 16-channel output. The `ec+3`
   form is what the Atmos JOC decoder emits when the output route is
   spatial-capable *and* spatialization is enabled — i.e., it's
   route-dependent decoder behavior, not a property of the input
   container or the pipeline engine. The original TV.app local trace
   showed `ec-3` 6ch because TV.app had narrowed the allow mask to
   0x5, which kept the JOC decoder in its non-spatial passthrough mode.

2. **The "Issue 12" symptom (local Atmos can't render spatial on
   MacBook speakers) is TV.app-specific.** A 100-line Swift AVPlayer
   harness that simply sets
   `allowedAudioSpatializationFormats = .monoStereoAndMultichannel`
   on a local-file `AVPlayerItem` succeeds on the same hardware, same
   route, same file. There is no macOS-wide or hardware gate stopping
   non-TV.app processes from spatializing local Atmos.

### TV.app entitlements check

To rule out a private entitlement as TV.app's enabler, the system
TV binary was inspected with `codesign -d --entitlements -
/System/Applications/TV.app`. TV.app holds many private entitlements
(`com.apple.private.commerce`, `com.apple.private.appstored`,
`com.apple.private.fpsd.client`, `com.apple.private.tcc.allow`,
`com.apple.avfoundation.allow-system-wide-context`, etc.), but
**no spatial-audio-specific entitlement appears in its list**.
The closest AVF-related entitlements are
`com.apple.avfoundation.allow-system-wide-context`,
`com.apple.avfoundation.allows-access-to-device-list`, and
`com.apple.avfoundation.allows-set-output-device` — none of which
gate `allowedAudioSpatializationFormats` or the SpatialMgr
content-eligibility evaluation. TV.app's local-Atmos failure is
therefore **behavioral, not entitlement-based**: it stems from
TV.app's own choice of `spatialPreference` value passed to
`mpc_updateAVAudioSpatializationFormatsForPlayerAudioFormat:` for
local-file items.

### TV.app hook / patch feasibility with SIP enabled

The behavioral finding above does **not** imply that TV.app can be
practically patched on a normal SIP-enabled system.

Local checks on the same machine showed:

- `csrutil status`: `System Integrity Protection status: enabled.`
- `csrutil authenticated-root status`: `Authenticated Root status:
  enabled.`
- `/` is mounted `sealed` and `read-only`.
- `/System/Applications/TV.app` and its executable are marked
  `restricted`.
- TV.app's code signature has `flags=0x12000(library-validation,runtime)`
  and `Platform identifier=26`.
- TV.app does not carry a `disable-library-validation` entitlement.

That combination blocks the normal non-invasive hook routes:

| Route | SIP-enabled result |
| --- | --- |
| Modify `/System/Applications/TV.app` on disk | blocked by sealed read-only system volume, restricted file flags, and code-signing |
| Patch/re-sign a copy as TV.app | loses Apple platform signature/private entitlements and is not the same TV.app product path |
| `DYLD_INSERT_LIBRARIES` / dylib injection | blocked for protected Apple/platform binaries, and by hardened-runtime library validation |
| Frida / LLDB / task-port patching | not a reliable full-SIP path for an Apple platform binary; the earlier DTrace work already required disabling debug/DTrace SIP restrictions |
| `defaults` preference override | no observed preference key maps to the local-file `spatialPreference` call site |

TV.app strings do expose preference names such as
`downloadDolbyAtmos`, `downloadMultichannel`,
`preferredDolbyAtmosPlaySetting`, and `multichannelAudioStrategy`,
plus log strings for `AVCFPlayerSetMultichannelAudioStrategy`.
Those are worth knowing about, but they do not currently provide a
documented or observed override for
`mpc_updateAVAudioSpatializationFormatsForPlayerAudioFormat:
spatialPreference:` on local-file items.

Conclusion: with full SIP and authenticated root enabled, a practical
TV.app hook/patch of the local-file spatial preference is **not
available**. Doing this as an actual TV.app patch would require
weakening SIP/debug/library-validation protections or modifying the
sealed system/app signature path, which is outside the current
TV.app/downloaded-content/local-playback solution path.

### Updated gate model

The TV.app capture above identified the AVF-layer intersection as
"the gate". The SpatialProbe data shows that gate is satisfied for
non-TV.app callers (`AllowsSpatialization` returns 1), but the
user-visible flag still resolves to false because of **further
downstream gates inside AudioToolbox**:

```
   AVF layer (AVPlayerItem)
       ↓ allowedAudioSpatializationFormats: caller can set; AVF re-narrows per route
       ↓ FPSupport eligibility check
       ↓ AudioQueueObject::AllowsSpatialization  ← returned 1 for SpatialProbe
   ─── crossing into AudioToolbox SpatialMgr ───
       ↓ Per-App route-capability assessment    ← "Route = not capable" for SpatialProbe
       ↓ spatialAudioSources registration        ← '?src' for SpatialProbe
       ↓ MEMixerChannel content-eligibility      ← 6-ch ec-3 rejected
       ↓ "is rendering spatial audio" flag
```

The earlier report attributed the user-visible flag to the AVF
intersection. That was wrong — or, more precisely, the AVF
intersection is a necessary-but-not-sufficient condition. The
SpatialMgr per-App / source-identifier / MEMixerChannel layers also
get a vote, and at least one of them is what rejects SpatialProbe.

## Falsification conditions

These dtrace findings stand unless one of the following is shown:

1. ~~A custom AVPlayer app on the same hardware, calling
   `[playerItem setAllowedAudioSpatializationFormats:
   AVAudioSpatializationFormatMonoStereoAndMultichannel]` on a local
   multichannel Atmos file, **does not** produce
   `mediaFormatinfo ... is rendering spatial audio = true`. That would
   indicate an additional gate not captured in this trace.~~
   **SATISFIED 2026-05-23 by SpatialProbe (above)** — the AVF
   intersection is not the bottom gate; AudioToolbox SpatialMgr /
   MEMixerChannel have additional gates.
2. A TV.app `.movpkg` produced by TV.app's own download manager (for
   a purchased Apple TV title) can be opened and yields the spatial
   flag for what is effectively a local file — already listed as a
   falsification condition in `ISSUE_12_EXPERIMENT_RESULTS.md`.
3. A future macOS release changes the route-filter step so Multichannel
   is no longer stripped on built-in MacBook speakers — this would
   change the allow-mask values observed here.

## TV.app + downloaded `.movpkg` capture (2026-05-23 03:22)

Tested with `Grass Lands.movpkg` (Prehistoric Planet S3 E?,
downloaded via TV.app's own download manager). MBP built-in speakers
route. `log stream`-only capture (no dtrace) since the wildcard
probes had crashed TV.app on the prior attempt.

### Key empirical findings

1. **`.movpkg` engages FigStreamPlayer.** Every player log line is
   tagged `<<<< FigStreamPlayer >>>>` (not FigFilePlayer). The
   pipeline-engine hypothesis from the original gate model holds:
   `.movpkg` follows the HLS-style stream-player path, not the local
   file path, even though the asset URL is a local file
   (`file // redacted-GTPRKL // movpkg`).

2. **TV.app's `allowedAudioSpatializationFormats` for `.movpkg` items is
   the inverse of its local-file mask.** From the
   `fpfs_ReportAudioPlaybackThroughFigLog` line:

   ```
   [AudioFormat aac is decodable] [AudioChannels 2]
   [Spatialization Eligible yes] [Client permits multi: yes, stereo: no]
   [Spatialization no] [Rendition Stereo]
   ```

   `Client permits multi: yes, stereo: no` ⇒ allow mask 0x2
   (Multichannel only). Compare to TV.app's FigFilePlayer local-file
   mask of 0x5 (Stereo + private). This **confirms the FigItem-derived
   update path is what flips the mask to Multichannel-only** for
   stream-player items.

3. **The downloaded `.movpkg` capture briefly exposed an
   Atmos-capable evaluation, but this is not yet proof that the Atmos
   group is complete locally.** At t≈8.2s (when the interstitial preroll
   handed off to the feature item), MEMixerChannel briefly evaluated:

   ```
   MEMixerChannel.cpp:3273  16-channel audiovisual content is eligible
      for spatialization
   MEMixerChannel.cpp:3300  mFormatID='ec+3', mNumChannels=16,
      mBestAvailableContentType=3, mContentspatializable=1,
      mSpatializationStatus=0, err=0
   ```

   `ec+3` 16ch, `mContentspatializable=1` — the runtime saw an
   Atmos-capable source/configuration. But `mSpatializationStatus=0`
   (not 2), the log line does not name the HLS AudioGroup, and playback
   then settled on a different audio variant. Do not treat this single
   mixer line as proof that a complete local `audio-atmos-*` stream was
   downloaded until `boot.xml` / `root.xml` / playlist metadata and
   segment files confirm it.

4. **TV.app's download / playback policy selected the stereo variant,
   not Atmos.** The chosen alternate was:

   ```
   FigAlternate(82): AudioGroup audio-stereo-160_download-ap-aoc.tv.apple.com
                     codecs hvc1.2.20000000.L123.B0, mp4a.40.2
   ```

   `mp4a.40.2` = HE-AAC v2 stereo. From t≈8.5s onward, MEMixerChannel
   reports `mFormatID='qaac', mNumChannels=2, mContentspatializable=0`.
   `Spatialization no` and `Rendition Stereo` for the entire main
   feature.

### Downloaded `.movpkg` highest-quality follow-up

Follow-up constraints from the user:

- TV.app Playback Download Quality was already set to the highest
  available setting before this `.movpkg` was downloaded/tested.
- The TV.app audio picker only showed `English` and `English AD`.
- `English` was selected for the capture.
- Treat `English AD` as Audio Description unless logs prove it maps to
  the Atmos group. It is not a presumed quality/Atmos selector.

This removes "enable Highest Quality" as the unresolved fix. The
remaining question was narrower: **does the downloaded package contain
a complete playable Atmos AudioGroup, and if it does, why does TV.app
select `audio-stereo-160_download-ap-aoc.tv.apple.com` for normal
English playback?**

Current evidence table:

| Stream / evidence | Group / name | Language | Role / accessibility | Codec | Complete/downloaded status | Bytes / segments | Interpretation |
|---|---|---|---|---|---|---|---|
| `FigAlternate(82)` | `audio-stereo-160_download-ap-aoc.tv.apple.com` | English, inferred from selected UI track | normal `English`; not AD | `mp4a.40.2` manifest, runtime `aac `/`qaac` ch=2 | selected for downloaded playback | not measured in this log-only capture | main English stereo selected |
| transient mixer eval | group not logged | unknown | unknown | runtime `ec+3` ch=16 | unknown; not proven complete locally | unknown | Atmos-capable evaluation appeared briefly, but not selected |
| TV.app picker | `English` | English | normal dialogue | selected group resolved to stereo in logs | selected | n/a | normal English maps to stereo for this package/capture |
| TV.app picker | `English AD` | English | likely Audio Description | not captured | unknown | n/a | AD is not the desired quality track unless a follow-up log maps it to Atmos |

The package was later located at:

```text
/Users/psp/Movies/TV/Media.localized/TV Shows/Prehistoric Planet/Season 3/Grass Lands.movpkg
```

After granting Terminal access to the package, the downloaded manifests
and `StreamInfoBoot.xml` files were inspected. The package contains
5293 files, 309 manifest-like files, 95 top-level streams, and six
downloaded master playlists. The master playlists advertise all of
these audio groups:

- `audio-HE2-stereo-32_download-ap-aoc.tv.apple.com`
- `audio-stereo-64_download-ap-aoc.tv.apple.com`
- `audio-stereo-128_download-ap-aoc.tv.apple.com`
- `audio-stereo-160_download-ap-aoc.tv.apple.com`
- `audio-ac3_download-ap-aoc.tv.apple.com`
- `audio-atmos_download-ap-aoc.tv.apple.com`

Package-level stream mapping for the relevant English groups:

| Stream ID / source | Group / name | Language | Role / accessibility | Codec / channels | Complete/downloaded status | Bytes / segments | Interpretation |
|---|---|---|---|---|---|---|---|
| `1-4834137-ATP2X4XE2REC6Y7VVXWIN4RVIN5DZFSW` | `audio-stereo-160_download-ap-aoc.tv.apple.com` / `English` | `en` | `com.apple.amp.tv.is-default`, `public.original-content` | `mp4a.40.2`, `CHANNELS="2"` | `Complete=YES`; selected in playback log | 50,085,832 bytes, 416 `.frag`, playlist has `#EXT-X-ENDLIST` | complete local main English stereo |
| `1-0-SAX5S27ZLUZKR5K34VF5C5TWWLVKQE5Z` | `audio-atmos_download-ap-aoc.tv.apple.com` / `English` | `en` | `com.apple.amp.tv.is-default`, `public.original-content` | master says `ec-3`, `CHANNELS="16/JOC"`; playlist URLs contain `audio_en_gr2448_mp4a-A6` | `Complete=NO`; `MediaBytesStored=0`; not selected | 10,198,971 bytes, only 30 `.frag`; playlist references 416 media entries | Atmos is referenced, but not a complete playable local stream |
| `audio-ac3_download-ap-aoc.tv.apple.com` / `English` | `English` | `en` | `com.apple.amp.tv.is-default`, `public.original-content` | `ac-3`, `CHANNELS="6"` | referenced by master; no complete boot stream found in this package inventory | not complete in package inventory | 5.1 candidate is advertised but not downloaded as a complete local stream |
| `audio-stereo-160_download-ap-aoc.tv.apple.com` / `English ` | `English AD` equivalent | `en` | `public.accessibility.describes-video` plus default/original flags | `mp4a.40.2`, `CHANNELS="2"` | referenced separately from normal English | not the selected normal-English capture | AD is Audio Description, not the desired quality selector |
| `audio-atmos_download-ap-aoc.tv.apple.com` / `English ` | `English AD` equivalent | `en` | `public.accessibility.describes-video` plus default/original flags | `ec-3`, `CHANNELS="16/JOC"` | referenced in master, but its `g=2448` local stream is incomplete | incomplete | AD may also have an Atmos reference, but that does not make AD the desired normal-dialogue quality track |

The package-level verdict is therefore:

> Highest Quality did not download a complete playable Atmos group for
> this title/device/account/route. TV.app downloaded `.movpkg` has the
> right FigStreamPlayer infrastructure and the master playlist advertises
> `audio-atmos_download-ap-aoc.tv.apple.com`, but the local Atmos stream
> is `Complete=NO` with `MediaBytesStored=0` while the selected
> `audio-stereo-160_download-ap-aoc.tv.apple.com` stream is complete.
> The stereo result is due to downloaded package contents, not merely
> runtime spatialization selection.

This also explains why the brief `ec+3`/16ch mixer evaluation could
appear without main playback settling on Atmos: the manifest advertises
an Atmos-capable rendition, but the persistent package state does not
contain a complete local Atmos stream for the normal selected playback.

### Online Apple TV+ control capture

An online control was run after the package inspection to separate
title/service capability from downloaded-package completeness.

First, the same `Grass Lands` item was started normally through
TV.app's AppleScript-visible HLS media item while the download remained
installed. That did **not** force online playback. It still resolved to
the downloaded package:

| Capture | Item | Download state | Delivery | Selected group | Runtime / renderer | Result |
|---|---|---|---|---|---|---|
| `captures/issue12_grass_lands_online_attempt_20260523_043238.json` | `Grass Lands` | downloaded | `downloaded_movpkg` | `audio-stereo-160_download-ap-aoc.tv.apple.com` | `qaac`/2ch; app spatial false | TV.app still chose the local complete stereo stream |

Two non-destructive attempts were then made to force `Grass Lands`
online without deleting the download. In both attempts, the package was
temporarily renamed out of the way from a Terminal/tmux context with
Movies access, and then restored in a `finally` block:

| Capture | Method | Result |
|---|---|---|
| `captures/issue12_grass_lands_forced_online_20260523_043528.json` | play cached HLS media database item while package path was missing | TV.app failed lookup with `Can't get track 1 of library playlist 1 whose database ID = 56. (-1728)`; no playback events |
| `captures/issue12_grass_lands_forced_online_url_20260523_043754.json` / `captures/issue12_grass_lands_forced_online_click_20260523_044103.json` | open Apple TV episode URL while package path was missing, then use keyboard/click UI controls | TV.app showed the episode page and Dolby Atmos badge, but playback stayed stopped; no HLS playback selection |

That result means the current TV.app library state binds the downloaded
`Grass Lands` episode to its local package. Hiding the package is not a
clean way to make TV.app fall through to online playback; it leaves the
episode in a broken "download expected" state until the package is
restored.

A different Apple TV+ Atmos episode from the same season, `Desert
Lands`, was then opened by URL with no local download present. Its
toolbar showed `Not Downloaded`, and playback started online. The
capture confirmed that the service/title/route can select Atmos online:

| Capture | Item | Download state | Delivery | Selected group | Runtime / renderer | Result |
|---|---|---|---|---|---|---|
| `captures/issue12_desert_lands_url_click_20260523_044429.json` | `Desert Lands` | not downloaded | `online_hls` | `audio-atmos_vod-ap-aoc.tv.apple.com` | `qc+3`/16ch; `mediaFormatinfo ... rendering spatial audio = true`; first true at 25.46s | online Apple TV+ selects Atmos and reaches app-level spatial rendering |

Relevant parsed fields from that online control:

```text
pipeline_engine: FigStreamPlayer
hls_delivery: online_hls
selected_hls_audio_group: audio-atmos_vod-ap-aoc.tv.apple.com
selected_hls_audio_group_kind: atmos
allowedAudioSpatializationFormats: 0x7
route: built-in speakers
mediaFormatinfo: qaac/2ch false -> qc+3/16ch true
mixer: qc+3 ch=16 content spatializable, status=2
spatial_rendering_changed_count: 4
app_spatial_rendering_ever_true: true
app_spatial_rendering_last_state: true
```

This is now the clean contrast:

- Apple TV+ **online HLS** for a not-downloaded Atmos episode can select
  `audio-atmos_vod-*`, transition to `qc+3`/16ch, and reach app-level
  spatial rendering true.
- Apple TV+ **downloaded `.movpkg`** for `Grass Lands` uses the same
  FigStreamPlayer family and permits multichannel, but its local
  normal-English Atmos group is incomplete, so TV.app selects the
  complete stereo `audio-stereo-160_download-*` group.

### Ted Lasso downloaded `.movpkg` follow-up

A second downloaded Apple TV+ title was inspected after the `Grass
Lands` result:

```text
/Users/psp/Movies/TV/Media.localized/TV Shows/Ted Lasso/Season 1/The Hope That Kills You.movpkg
```

This package is useful because it initially appears to have an
`audio-atmos_download-ap-aoc.tv.apple.com` stream marked
`Complete=YES`. Raw stream location and segment counts change that
interpretation: the complete Atmos stream belongs to an
`InterstitialAssets/...movpkg` child package with only 2 media fragments,
not to the main episode stream inventory.

Relevant local package rows:

| Stream / path | Group / name | Language | Role / accessibility | Codec / channels | Complete/downloaded status | Bytes / segments | Interpretation |
|---|---|---|---|---|---|---|---|
| `0-4482011-BELNUQV4ER6D7W2OC7FQFXZEEY5VMJF7` | main video | n/a | n/a | video | `Complete=YES` | 663,399,476 bytes; 493 `.frag`, 10 `.initfrag` | complete main episode video |
| `1-4482011-5KHVNJOD7PS6MYKJKXGP43FGF5WJO6O6` | `audio-stereo-128_download-ap-aoc.tv.apple.com` / `English` | `en` | `com.apple.amp.tv.is-default`, `public.original-content` | `mp4a.40.2`, 2ch | `Complete=YES` | 31,684,679 bytes; 370 `.frag`, 10 `.initfrag` | complete main English stereo |
| `InterstitialAssets/A4CIWHM67RY7B3N5W6OUQPVFN2JV3HSJ.movpkg/0-14238665-R465VTV4I6Q7OJZRBXKZRTXWVXCNITU7` | interstitial video | n/a | n/a | video | `Complete=YES` | 10,028,775 bytes; 2 `.frag`, 1 `.initfrag` | short interstitial/preroll asset |
| `InterstitialAssets/A4CIWHM67RY7B3N5W6OUQPVFN2JV3HSJ.movpkg/1-14238665-4KUQGGFOY3RZ374YBMA4G4Q6RIROJZLK` | `audio-atmos_download-ap-aoc.tv.apple.com` | multiple languages in grouped manifest rows | includes normal and AD rows in grouped manifest table | `ec-3`, `16/JOC` | `Complete=YES`, but only inside the interstitial child package | 450,734 bytes; 2 `.frag`, 1 `.initfrag` | complete short interstitial Atmos, not complete main-episode Atmos |
| referenced-only main manifest groups | `audio-ac3_download-ap-aoc.tv.apple.com`, `audio-atmos_download-ap-aoc.tv.apple.com`, `audio-ec3-stereo_download-ap-aoc.tv.apple.com`, other stereo groups | includes `English` and `English AD` rows | AD rows carry `public.accessibility.describes-video` | `ac-3`, `ec-3`, `mp4a.40.2` | no complete top-level main-episode audio stream found for these groups | no local main-episode media bytes/segments mapped | advertised alternatives, not complete local main audio |

Search coverage for this package:

```text
files: 4863
manifest-like files: 297
StreamInfoBoot.xml: 96
playlists: 101
audio-atmos: 5
audio-stereo: 5
ec-3: 5
mp4a.40.2: 5
Complete>YES: 98
download-ap-aoc: 197
vod-ap-aoc: 0
AD: 11
description: 4
accessibility: 4
public.accessibility.describes-video: 4
```

A downloaded-playback capture was then run for the TV.app library item
`The Hope That Kills You`:

| Capture | Delivery | Selected group | Runtime / renderer | Result |
|---|---|---|---|---|
| `captures/issue12_ted_lasso_downloaded_20260523_045907.json` | `downloaded_movpkg` | `audio-stereo-128_download-ap-aoc.tv.apple.com` | selected variant `dvh1.05.01,mp4a.40.2`; `mediaFormatinfo` main playback `qaac`/2ch with app spatial false; transient `ec+3`/16ch mixer/decoder evidence also appeared | TV.app selected the complete local stereo stream for the main episode |

This is the second downloaded-title data point supporting the
package-content conclusion:

> Highest Quality did not download a playable Atmos group for this
> title/device/account/route. The Ted Lasso package advertises Atmos
> alternates and contains a complete short interstitial Atmos stream,
> but the main episode has complete local stereo and no complete
> top-level main-episode Atmos stream. The stereo result is due to
> downloaded package contents, not runtime selection of a complete
> local Atmos group.

The capture parser's generic `movpkg_atmos_variant_present_but_not_selected`
verdict is accurate for log-visible HLS alternates, but too broad for
package completeness. The follow-up tool now has a `.movpkg` inventory
pass:

```bash
uv run python -m dolby_tool movpkg \
  "/Users/psp/Movies/TV/Media.localized/TV Shows/Ted Lasso/Season 1/The Hope That Kills You.movpkg" \
  --selected-group audio-stereo-128_download-ap-aoc.tv.apple.com
```

For Ted Lasso, that inventory verdict is:

```text
movpkg_atmos_variant_missing_or_incomplete
```

The inventory pass checks the selected group against
`StreamInfoBoot.xml`, `Complete`, local media bytes, segment counts, and
whether the matching stream is top-level main content or an
`InterstitialAssets/...movpkg` child package.

Clean downloaded-playback capture recipe:

1. Disable network/Wi-Fi so playback must use the local download.
2. Open TV.app directly to Library / Downloaded item.
3. Start `dolby-tool` TV Capture before pressing play.
4. Play 45-60 seconds with `English` selected.
5. Capture selected AudioGroup, codec, runtime audio,
   `mediaFormatinfo`, `MEMixerChannel`, SpatialMgr route/source, and
   `FigAlternate` selection lines.
6. Optionally repeat with `English AD`, but only to map that label; do
   not assume AD is the Atmos-quality option.

### Bonus: tvlog parser updates relevant here

The parser now surfaces:

- `route_spatial_capable` (true when `maxSpatializableChannels > 0`)
- `spatial_audio_sources` and `spatial_source_unknown`
- `spatial_binding_apps`
- `selected_hls_audio_group`
- `selected_hls_audio_group_kind` (`stereo`, `atmos`, or
  `audio_description` when inferable)
- `hls_delivery` (`downloaded_movpkg` vs `online_hls` when the
  AudioGroup hostname exposes it)
- `downloaded_hls_verdict`, including:
  `movpkg_figstreamplayer_selected_stereo`,
  `movpkg_atmos_variant_present_but_not_selected`, and
  `movpkg_atmos_variant_selected`

Recommended next parser/tool extension:

- The `.movpkg` inventory pass can emit
  `movpkg_atmos_variant_missing_or_incomplete` when the log advertises
  `audio-atmos_download-*` but the package lacks a complete top-level
  main-content Atmos stream with local media bytes and segment files.
- Keep the existing log-only verdicts, but label them as HLS alternate
  selection verdicts. The Ted Lasso follow-up shows why log-visible
  Atmos alternates are not enough: a complete Atmos stream can belong
  to an interstitial child package while main episode playback still has
  only complete stereo locally.

The saved 03:22 capture now parses as:

```text
hls_delivery: downloaded_movpkg
pipeline_engine: FigStreamPlayer
selected_hls_audio_group: audio-stereo-160_download-ap-aoc.tv.apple.com
selected_hls_audio_group_kind: stereo
audio_codec: mp4a.40.2
downloaded_hls_verdict: movpkg_atmos_variant_present_but_not_selected
current audio: qaac ch=2
```

### Local HTTP HLS / QuickTime follow-up

A local HLS package was built from the user's Atmos source and served from
`.tmp/alt_hls` over `http://127.0.0.1:8765/master.m3u8`.

Important setup detail: Python's basic `http.server` was not enough for this
test because QuickTime/Safari need byte-range media requests. A Range-capable
localhost server returned `206 Partial Content` for the fragmented media and
allowed normal playback.

TV.app was tested against the same local HLS URL through:

```text
http://127.0.0.1:8765/master.m3u8
itls://127.0.0.1:8765/master.m3u8
itlss://127.0.0.1:8765/master.m3u8
itvls://127.0.0.1:8765/master.m3u8
itvlss://127.0.0.1:8765/master.m3u8
```

Those TV.app attempts produced 0 relevant playback events and no localhost
server fetches. Current verdict: TV.app's Live Stream URL schemes are not a
practical arbitrary-local-HLS launch path in this form.

QuickTime Player opened the same local HLS URL successfully. The broad raw
capture at
`captures/alt_paths/20260523_052228_quicktime_range_hls_raw.log` showed:

```text
FigAssetCreateWithURL ... <http // redacted ... // m3u8>
<<<< FigStreamPlayer >>>> FigPlayerStreamCreateWithOptions
FigAlternate ... [AudioGroup atmos] [dvh1.05.06,ec-3]
AudioQueueNewOutput 16 ch, 48000 Hz, ec+3
ACDDPAtmosDecoder ... mIsAtmos = 1, mIsOARMode = 1
Forcing 7.1.4 decoder for Atmos
AUSpatialMixerV2 ... Setting audio channel layout Atmos_7_1_4
```

Conclusion: QuickTime + local HTTP HLS with Range support is now the strongest
observed Apple-native local playback alternative. It reaches FigStreamPlayer
and strong CoreAudio Atmos/spatial mixer evidence without TV.app and without a
custom player app. It does not answer the narrower TV.app-local question,
because QuickTime does not emit TV.app's `ampplay mediaFormatinfo` flag.

Tooling follow-up: `dolby-tool tvlog-parse` now parses saved compact raw logs
into the normal structured capture summary, and
`dolby-tool tvlog-capture --profile local-player` uses a broader
QuickTime/Safari/WebKit predicate for future local-player controls.
`dolby-tool hls-prepare <local.movpkg> <folder>` now flattens simple
persisted-HLS packages into a serveable HLS folder.
`dolby-tool hls-serve <folder> --open quicktime` now provides the
Range-capable localhost server needed for this workflow.

Fresh end-to-end confirmation (2026-05-23): using the merged tooling,
`hls-prepare` -> `hls-serve` -> QuickTime ->
`tvlog-capture --profile local-player` produced
`captures/alt_paths/20260523_fresh_quicktime_local_hls.json` with
`source=hls`, `pipeline_engine=FigStreamPlayer`, selected HLS AudioGroup
`atmos`, HLS audio codec `ec-3`, current/best audio
`ec+3 ch=16 48000 Hz spatialization=yes`, Atmos decoder active, OAR active,
forced 7.1.4 Atmos, and AUSpatialMixer layouts `Atmos_7_1_4`, `Stereo`.

## Bottom line (2026-05-23)

- **For local-file Atmos playback with `is rendering spatial audio = true`
  on a spatial-capable route, the only blocker identified so far is
  TV.app's own behavior.** SpatialProbe proved that an AVFoundation
  caller can render the same local content spatially on MBP speakers,
  but that was a diagnostic control, not the proposed solution path.
- The earlier characterization of the gate as an AVF allow ∩ eligibility
  intersection was correct but incomplete: it is downstream of the
  per-route SpatialMgr capability check and the per-route Atmos JOC
  decoder mode selection. On a non-spatial-capable route, the JOC
  decoder keeps the stream in `ec-3` 6ch and MEMixerChannel rejects
  6-channel content. On a spatial-capable route with the allow mask set
  correctly, the same decoder produces `ec+3` 16ch and MEMixerChannel
  accepts it.
- TV.app's failure on local Atmos is not gated by entitlements (verified
  by `codesign -d --entitlements -`). It is a product-level decision in
  the `spatialPreference` value chosen by TV.app inside
  `mpc_updateAVAudioSpatializationFormatsForPlayerAudioFormat:`. TV.app
  cannot be patched in place under normal SIP. The only remaining TV.app
  path for the same content remains a TV.app-trusted `.movpkg` with a
  complete main Atmos stream; outside TV.app, QuickTime local HTTP HLS is
  now the strongest Apple-native workaround candidate.

## Raw trace excerpts

Local (Blood and Bone, 25s window, ~11 lines of events):

```
=== TRACE2 START pid=2446 phase=local ===
AVCFPlayerItemSetAllowedAudioSpatializationFormats arg0=8bcaaed00 arg1=0x7 (=7)
playerItem_SetAllowedAudioSpatializationFormats     arg0=8bcaaed20 arg1=0x5 (=5)
FPSupport_Eligibility ENTER arg0=8ba3e57c0 arg1=0 arg2=60
FPSupport_Eligibility RETURN -> 0x2 (=2)
AudioQueueObject::CheckSpatialization arg0=8be3eb200 arg1=8bb8c7d80
FPSupport_Eligibility ENTER arg0=8ba3e57c0 arg1=16bba1c78 arg2=120a8
FPSupport_Eligibility RETURN -> 0x2 (=2)
=== TIMER EXIT ===
```

HLS (Apple TV+, 25s window):

```
=== TRACE2 START pid=2446 phase=hls ===
AVCFPlayerItemSetAllowedAudioSpatializationFormats arg0=8bb93c900 arg1=0x7 (=7)
playerItem_SetAllowedAudioSpatializationFormats     arg0=8bb93c920 arg1=0x5 (=5)
FPSupport_Eligibility ENTER arg0=8bc6578e0 arg1=16c348298 arg2=60
FPSupport_Eligibility RETURN -> 0x1 (=1)
AudioQueueObject::CheckSpatialization arg0=8c2353200 arg1=8bb8c7d80
FPSupport_Eligibility ENTER arg0=8bc6578e0 arg1=16c604f80 arg2=2d5a80019858702c
FPSupport_Eligibility RETURN -> 0x1 (=1)
FPSupport_Eligibility ENTER arg0=8b9df2f80 arg1=16bba0408 arg2=60
FPSupport_Eligibility RETURN -> 0x1 (=1)
AudioQueueObject::CheckSpatialization arg0=8c2352800 arg1=8bb8c7d80
FPSupport_Eligibility ENTER arg0=8b9df2f80 arg1=16cfde3e0 arg2=d30780019858702c
FPSupport_Eligibility RETURN -> 0x1 (=1)
=== TIMER EXIT ===
```

The first FPSupport call in each phase corresponds to the initial
AVPlayerItem creation; subsequent calls correspond to format
refresh events as the item begins playback.
