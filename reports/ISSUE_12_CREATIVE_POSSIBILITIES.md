# Issue 12 follow-up: Creative possibilities for engaging app-level spatial rendering on local content

Companion to `ISSUE_12_LOCAL_SPATIAL_RENDERING.md`. That report locates the
gate at the CoreMedia engine (`FigFilePlayer` vs `FigStreamPlayer`) and the
asbdFormatID (`ec+3` vs `qc+3`). The gate is upstream of any file-level
field, so this report deliberately stops investigating file-level tweaks and
instead enumerates ranked, falsifiable ways to make TV.app (or another Apple
player) take the FigStreamPlayer / qc+3 branch for content the user owns
locally.

## What we already know works

`FigStreamPlayer` + `qc+3` + `is rendering spatial audio = true` are seen
on Apple TV+ HLS playback. They are not seen on any FigFilePlayer playback.
So any creative path must end with one of:

- TV.app loading an asset that is internally treated as an HLS asset (so
  FigStreamPlayer takes it), or
- some other Apple player whose internal pipeline also produces the
  `qc+3` asbd / `is rendering spatial audio` flag, run against the same
  local source.

## What we found while probing TV.app

`/System/Applications/TV.app/Contents/Info.plist`:

- `CFBundleURLSchemes`: `daap`, `com.apple.tv`, `videos`, `com.apple.watchlist`,
  and a "Live Stream URL" group: `itls`, `itlss`, `itvls`, `itvlss`.
- `CFBundleDocumentTypes`: includes a TV-bundle type named
  `com.apple.TV.movpkg` with extension `movpkg` and `LSTypeIsPackage = 1`.
  TV.app's role for this UTI is `Viewer` with `LSIsAppleDefaultForType = Yes`.
- The standard local file UTIs are also accepted as viewer:
  `public.mpeg`, `com.apple.quicktime-movie`, `com.apple.protected-mpeg-4-video`,
  `com.apple.m4v-video`.

We confirmed on disk that other apps (Amazon Prime Video) already use this
mechanism: their downloaded content lives at
`~/Library/Containers/com.amazon.aiv.AIVApp/Data/Library/com.apple.UserManagedAssets.*/`
as `.movpkg` bundles. Inside each `.movpkg`:

- `boot.xml` declares `<HLSMoviePackage>` with
  `<HLSMoviePackageType>PersistedStore</HLSMoviePackageType>` and lists every
  `<Stream>` (video, audio, subtitle, trick play) by `ID`, `NetworkURL`
  (original HLS URL) and `Path` (local file under `Data/`).
- A schema is published by macOS at
  `/System/Library/Schemas/HLSMoviePackage.xsd` (referenced from `boot.xml`).
- Storage is fragmented mp4 segments stored as opaque filenames inside the
  `.movpkg` directory.

This means `.movpkg` is a documented Apple package format for "persisted
HLS." It is the on-disk form produced by `AVAssetDownloadTask`, and it is
what TV.app uses to play downloads from Apple TV+ offline. TV.app already
knows how to open Apple-managed `.movpkg` downloads directly. Playback of
the tested Apple-managed `.movpkg` goes through the CoreMedia HLS pipeline
(FigStreamPlayer / FigStreamProxy), not FigFilePlayer, because the asset is
HLS-backed.

The later `Grass Lands.movpkg` inspection changes the ranking: `.movpkg`
is the right infrastructure, but not a complete solution by itself. The
tested package engaged FigStreamPlayer and permitted multichannel, and its
master playlist advertised `audio-atmos_download-ap-aoc.tv.apple.com`.
However, the local Atmos stream was incomplete (`Complete=NO`,
`MediaBytesStored=0`) while the normal English stereo stream was complete
and selected. The obstacle is therefore TV.app trust / package completeness
and title/account/device download policy, not just the container format.

The local-HLS follow-up adds a separate finding: QuickTime Player can open
a locally served HLS package from the user's Atmos source and run it through
FigStreamPlayer. A Range-capable localhost server was required; Python's
basic `http.server` was insufficient for the byterange media requests. The
QuickTime raw log showed `FigStreamPlayer`, selected `[AudioGroup atmos]`
with `[dvh1.05.06,ec-3]`, created an `ec+3` 16-channel AudioQueue, forced a
7.1.4 Atmos decoder, and configured `AUSpatialMixerV2` with
`Atmos_7_1_4`. This is not TV.app local playback, but it is the strongest
Apple-native local playback alternative observed so far.

## Ranked creative paths

Ranked by confidence that the path actually flips the renderer state, given
what we already know.

### Tier A — Apple-managed paths most likely to answer the remaining question

1. **Stream the same Apple title online**
   - Play the same Prehistoric Planet / Grass Lands title online in TV.app
     on the same route.
   - Capture before playback starts.
   - Expected: if the title/account/device/route can receive Atmos online,
     the capture should show the online HLS group choosing Atmos or a
     Dolby-family runtime path (`qc+3` / app-level spatial true if the known
     Apple TV+ path is reached).
   - Falsification: if the online stream also resolves to stereo, the issue
     is not only download completeness for this title; it may be title,
     account, regional, route, or server-side policy.

2. **Download a different known Apple TV+ Atmos title**
   - Pick a title that advertises Atmos in TV.app and download it with the
     same Highest Quality setting.
   - Inspect its `.movpkg` inventory for `audio-atmos`, `ec-3`,
     `CHANNELS="16/JOC"`, `Complete=YES`, `MediaBytesStored`, and segment
     counts.
   - Expected: at least one title may download a complete playable Atmos
     group. If so, capture whether TV.app selects it offline.
   - Falsification: if multiple Apple TV+ Atmos titles advertise Atmos but
     all persist only stereo locally, offline downloads on this
     device/account/route likely do not include playable Atmos.

3. **Compare title/account/device behavior**
   - Compare the same title online vs downloaded, and compare multiple
     Atmos-marked titles after download.
   - If available, compare another Mac/account/route with the same title.
   - Expected: separates "this specific package is incomplete" from a
     broader TV.app download policy.

### Tier B — local `.movpkg` construction; lower confidence after Grass Lands

4. **Build a `.movpkg` from the local Atmos file via `AVAssetDownloadTask`**
   - Stand up a tiny local HTTP server (e.g. `python -m http.server`).
   - Package the local Atmos m4v as a real HLS variant via `MP4Box -dash`
     or any HLS packager (we have ffmpeg + MP4Box installed; `gpac/MP4Box`
     can output fragmented MP4 + m3u8 without re-encoding ec-3 audio).
   - Write a 30–50 line Swift command-line tool that creates an
     `AVAssetDownloadURLSession`, kicks off an `AVAssetDownloadTask` against
     `http://localhost:PORT/master.m3u8`, and saves the destination URL.
     The resulting bundle is a real `.movpkg`.
   - Double-click the `.movpkg` in Finder, or open via
     `open -b com.apple.TV /path/to/file.movpkg`.
   - Capture `log stream` with `dolby_tool` while playback runs.
   - Expected: only if TV.app accepts the package as trusted playback and
     persists/selects the Atmos group, it may route through FigStreamPlayer
     and reach the desired Dolby/spatial path.
   - Falsification: if TV.app refuses the package, ignores it, or selects a
     non-Atmos group, then local `.movpkg` construction is not practical for
     the TV.app path even though `.movpkg` is HLS-backed.

5. **Hand-author a `.movpkg` against the published schema**
   - `/System/Library/Schemas/HLSMoviePackage.xsd` defines the package
     format. A minimal `boot.xml` with one PersistedStore stream pointing
     at a local fragmented-mp4 file may be enough to make TV.app open it.
   - Same expected outcome as path 4. This path is cheaper if we can
     reproduce a valid `boot.xml` + `root.xml` directly without writing a
     Swift downloader, but it is less Apple-blessed and may hit schema
     validation rejection.

6. **Apple HLS Tools (`mediafilesegmenter` + `mediastreamvalidator`)**
   - Not installed on this machine. Download from
     `developer.apple.com/download/applications/` (free, Apple ID needed).
   - Once installed, `mediafilesegmenter` produces a canonical HLS bundle
     (master.m3u8 + media.m3u8 + .ts/.m4s segments) without re-encoding the
     ec-3 / Atmos audio. Pair with paths 4 or 5 above to feed the packager.
   - This produces the most Apple-canonical HLS package, which gives the
     highest chance the AVAssetDownloadTask in path 4 will succeed, but it
     still does not solve TV.app trust/package-completeness policy by itself.

### Tier C — tested alternatives outside TV.app downloaded playback

7. **TV.app "Live Stream URL" schemes (`itls://`, `itlss://`, `itvls://`,
   `itvlss://`)**
   - These are exposed in TV.app's Info.plist but undocumented. They look
     like Apple's IPTV/cable-provider live stream handlers.
   - Tried `http`, `itls`, `itlss`, `itvls`, and `itvlss` against
     `http://127.0.0.1:8765/master.m3u8`.
   - Result: TV.app produced 0 relevant events and made no localhost server
     requests. Treat this path as dead for arbitrary local HLS unless a
     provider-authenticated URL form is discovered.

8. **`open -b com.apple.TV http://localhost:8000/master.m3u8` against a
   local HLS server**
   - TV.app does not advertise generic `http`/`https` handler ownership for
     m3u8.
   - Tried directly; same result as the TV.app live-stream schemes: no
     playback events and no localhost fetches.

9. **Open via Safari in fullscreen video**
   - Safari plays HLS via CoreMedia's FigStreamPlayer. Drag an `m3u8` URL
     into Safari, then enter fullscreen video.
   - Expected: same FigStreamPlayer engine TV.app uses for Apple TV+, same
     asbdFormatID `qc+3`, same app-level spatial rendering, but reported
     under Safari's audit logs (not TV.app's `com.apple.TV:ampplay`).
   - Important: the `mediaFormatinfo` log line is emitted by the
     `com.apple.TV:ampplay` subsystem, which is TV.app-specific. Safari is
     unlikely to emit that exact line. The lower-level
     `SpatializationManager`, `ACDDPAtmosDecoder`, and `MEMixerChannel`
     events should still appear. Treat Safari's audible result as the
     real signal, not the missing TV-specific log line.
   - Tested follow-up: Safari failed to load both the direct playlist URL
     and a minimal same-origin `<video src="master.m3u8">` page on this
     machine, creating `safari-resource:/ErrorPage.html` tabs and 0
     local-player capture events. Treat Safari as unproven/blocked by
     launch or page-loading behavior unless that local load failure is
     solved.

10. **Open in QuickTime via File → Open Location**
   - Tested with a locally served HLS package built from the user's Atmos
     source.
   - The repeatable local-file workflow is now:
     `dolby-tool hls-package <local media file> <folder>` ->
     `dolby-tool hls-serve <folder> --open quicktime` ->
     `dolby-tool tvlog-capture --profile local-player`.
   - Result: QuickTime accepted `http://127.0.0.1:8765/master.m3u8`, used
     FigStreamPlayer, selected the Atmos HLS group, decoded `ec+3` 16ch,
     forced a 7.1.4 Atmos decoder, and initialized `AUSpatialMixerV2` with
     an `Atmos_7_1_4` input layout.
   - Caveat: QuickTime is not TV.app, so the TV-specific `mediaFormatinfo
     ... is rendering spatial audio = true` line is not expected. Judge it
     by CoreMedia/CoreAudio evidence and controlled listening, not by the
     missing TV.app-only flag.

### Tier D — unlikely to flip the engine

11. **Library import** (`File → Import` of an mp4/m4v into TV.app library)
   - Still a file-backed asset, still FigFilePlayer. Useful only as a
     control to confirm import does not help.

12. **Rename `.m3u8` to `.m4v` and hope TV.app does content sniffing**
   - TV.app will probably honor the UTI and refuse, or treat it as a corrupt
     m4v. Cheap to verify and dismiss.

13. **Force the engine via `defaults` plist or experimental TV.app flags**
    - No public defaults are documented for this. Skip unless a specific
      hidden flag is discovered.

### Tier E — out of scope here but worth noting

14. **Custom AVPlayer host app**
    - A 50-line SwiftUI macOS app that uses `AVPlayer` against
      `http://localhost:8000/master.m3u8` (or against a `.movpkg`),
      with `playerItem.allowedAudioSpatializationFormats = .multichannel`,
      `playerItem.audioTimePitchAlgorithm = .spectral`, etc.
    - This is not a solution path for the current TV.app/downloaded-content
      issue. It is retained only as a diagnostic control for separating
      CoreMedia / Atmos / spatial-renderer behavior from TV.app product
      behavior.

15. **Music app for Atmos audio-only files**
    - Apple Music's Atmos catalogue plays through CoreMedia HLS. A local
      `.m4a` with Atmos JOC may go through Music.app's local FigFilePlayer
      path. Same engine question as TV.app, likely same outcome. Mentioned
      here only because it is a second app for comparison.

## Recommended next experiments

The original recommendation was to build a local `.movpkg` and open it in
TV.app. The `Grass Lands.movpkg` evidence supersedes that as the primary
next step: an Apple-managed `.movpkg` already proved the HLS/FigStreamPlayer
infrastructure, but also proved that an advertised Atmos group can be
missing or incomplete in the local package.

Run these Apple-managed tests first:

1. Stream `Grass Lands` online in TV.app on the same route and capture before
   playback starts. Confirm whether online playback selects Atmos / `qc+3` /
   spatial true.
2. Download a different Apple TV+ title that advertises Atmos, inspect the
   `.movpkg`, and check whether the normal English `audio-atmos` stream is
   `Complete=YES` with local media bytes and segment inventory.
3. If a different title has complete local Atmos, capture its downloaded
   playback and verify whether TV.app selects `audio-atmos` or still chooses
   stereo.
4. If every downloaded Apple TV+ Atmos title has incomplete local Atmos, the
   conclusion is: Highest Quality does not download playable Atmos for this
   title/device/account/route; the stereo result is package contents, not
   runtime selection.

Execution update:

- `Grass Lands` could not be cleanly forced online while its downloaded
  package remained registered in TV.app. Normal play still chose
  `downloaded_movpkg` / `audio-stereo-160_download-ap-aoc.tv.apple.com`.
  Temporarily hiding the package made the cached library item fail or
  stay stopped, and the package was restored.
- A not-downloaded same-season Apple TV+ control, `Desert Lands`, did
  stream online successfully. Its capture selected
  `audio-atmos_vod-ap-aoc.tv.apple.com`, reached `qc+3`/16ch, and
  reported app-level spatial rendering true.
- A second downloaded Apple TV+ item, `Ted Lasso` / `The Hope That Kills
  You`, was inspected at
  `/Users/psp/Movies/TV/Media.localized/TV Shows/Ted Lasso/Season 1/The Hope That Kills You.movpkg`.
  It has complete top-level main video and complete top-level main
  `audio-stereo-128_download-ap-aoc.tv.apple.com`, but no complete
  top-level main-episode Atmos audio stream was found. The only
  `audio-atmos_download-ap-aoc.tv.apple.com` stream marked
  `Complete=YES` is inside an `InterstitialAssets/...movpkg` child
  package with 2 fragments and roughly 450 KB of audio data, so it is
  not evidence that the full episode downloaded Atmos.
- A local HTTP HLS package built from
  `/Users/psp/Desktop/Dolby Spatial Test.movpkg` was served from
  `.tmp/alt_hls`. A Range-capable localhost server was needed for
  QuickTime/Safari byterange requests; this is now repeatable via
  `dolby-tool hls-prepare <local.movpkg> .tmp/alt_hls --overwrite` followed by
  `dolby-tool hls-serve .tmp/alt_hls --open quicktime`.
- Direct packaging from a normal local file is now available too:
  `dolby-tool hls-package <local media file> <folder> --overwrite`
  stream-copies the first video stream and selected audio stream into fMP4
  HLS with a separate audio group by default, then the same `hls-serve`
  QuickTime workflow applies. A bare FFmpeg split fMP4 master failed in
  QuickTime with `CoreMediaErrorDomain error -12927`, so the tool now
  auto-adds Apple-player-friendly `CODECS`, `VIDEO-RANGE`, `FRAME-RATE`,
  and Atmos `CHANNELS="6/JOC"` tags when detected.
- Clean QuickTime capture of the auto-patched `hls-package` output
  reproduced the useful local-HLS path: `source=hls`, FigStreamPlayer,
  AudioGroup `group_audio` classified as Atmos, source `ec-3`, runtime
  `ec+3 ch=16`, Atmos decoder active, OAR active, forced 7.1.4 Atmos,
  and AUSpatialMixer layouts `Atmos_7_1_4`, `Stereo`.
- `dolby-tool hls-package-capture <local media file> <folder>` now wraps
  the working sequence so future tests do not accidentally start capture
  after QuickTime playback initialization.
- Wrapper validation
  `captures/alt_paths/20260523_quicktime_hls_package_wrapper.json`
  reproduced the full QuickTime local-HLS evidence in one command.
- TV.app did not open that arbitrary HLS URL through `http`, `itls`,
  `itlss`, `itvls`, or `itvlss`; it produced no playback events and made no
  localhost fetches.
- Safari did not open the same local HLS as either a direct `master.m3u8`
  navigation or a minimal same-origin HTML `<video>` page. It created
  failed-page tabs and `tvlog-capture --profile local-player` produced 0
  playback events, so this is currently a Safari launch/load failure rather
  than an Atmos-selection result.
- QuickTime Player did open the same local HLS URL. Raw log
  `captures/alt_paths/20260523_052228_quicktime_range_hls_raw.log` shows
  `FigStreamPlayer`, `[AudioGroup atmos]`, `[dvh1.05.06,ec-3]`, `ec+3`
  16ch AudioQueue input, `mIsAtmos = 1`, `mIsOARMode = 1`, `Forcing 7.1.4
  decoder for Atmos`, and `AUSpatialMixerV2` input layout
  `Atmos_7_1_4`.
- A fresh tool-driven confirmation reproduced the same path end-to-end:
  `hls-prepare` -> `hls-serve` -> QuickTime ->
  `tvlog-capture --profile local-player` produced
  `captures/alt_paths/20260523_fresh_quicktime_local_hls.json` with
  `source=hls`, `pipeline_engine=FigStreamPlayer`, selected HLS AudioGroup
  `atmos`, HLS audio codec `ec-3`, current/best audio
  `ec+3 ch=16 48000 Hz spatialization=yes`, Atmos decoder active, OAR active,
  forced 7.1.4 Atmos, and AUSpatialMixer layouts `Atmos_7_1_4`, `Stereo`.
- The Ted Lasso downloaded-playback capture selected
  `downloaded_movpkg` / `audio-stereo-128_download-ap-aoc.tv.apple.com`.
  It still showed transient `ec+3`/16ch lower-level evidence from
  advertised alternates, but main playback resolved to stereo with
  app-level spatial rendering false.
- The remaining high-value test is therefore narrower: find a downloaded
  Apple TV+ title/episode whose top-level main-episode `audio-atmos`
  stream is actually `Complete=YES` with local media bytes and segment
  inventory. If none appear across multiple titles, the practical
  conclusion is that Highest Quality is not persisting playable main
  Atmos for this title/device/account/route combination.
- `dolby-tool movpkg` now automates that inventory check and emits
  `movpkg_atmos_variant_missing_or_incomplete` when Atmos is advertised
  but not present as a complete top-level main-content stream.
- `dolby-tool movpkg-scan "/Users/psp/Movies/TV/Media.localized"` now
  batch-scans top-level downloaded packages while skipping interstitial
  child packages. The current local library scan finds two top-level
  packages, `Grass Lands` and `The Hope That Kills You`; both have
  complete main stereo and no complete top-level main Atmos.
- Local-file remux/container variants were tested from the same `Blood
  and Bone.mp4` source as 180s lossless MP4 faststart, M4V, and MOV
  clips. MP4/M4V preserved `dvh1`; MOV exposed `hev1`. All three played
  in TV.app as `local_file` / FigFilePlayer with `ec+3 ch=16`, active
  lower-level Atmos/spatial evidence, and app-level spatial rendering
  false. Container remuxing did not move TV.app onto the desired
  `qc+3` / app-spatial-true path.

Keep the local `.movpkg` recipe as a lower-priority diagnostic only. It is
still useful if the goal is to test how TV.app handles a locally produced
HLS package, but it is no longer the most practical path for the user's own
local files unless a TV.app-trusted package with complete Atmos can be
produced.

Lower-priority local package recipe:

1. Pick the existing local Atmos file already used in Local 1, Local 2,
   Local 6 captures. Keep the same source so the comparison is honest.
2. Use ffmpeg to remux it to fragmented mp4 (no re-encode):
   `ffmpeg -i SOURCE.m4v -c copy -movflags +cmaf+frag_keyframe+empty_moov
   -f mp4 frag.mp4`.
3. Use `MP4Box -hls 6000 -frag 6000 frag.mp4` to emit
   `master.m3u8`, `frag_audio.m3u8`, `frag_video.m3u8`, and the m4s
   segments. Inspect the master to confirm the audio variant is tagged
   `CODECS="ec-3"` and `CHANNELS="16/JOC"` (HLS Atmos signaling).
4. `python3 -m http.server 8000 --bind 127.0.0.1` from the directory with
   the manifests.
5. Write `download.swift`:
   ```swift
   import AVFoundation
   let url = URL(string: "http://localhost:8000/master.m3u8")!
   let cfg = URLSessionConfiguration.background(withIdentifier: "dolby-test")
   let session = AVAssetDownloadURLSession(configuration: cfg,
       assetDownloadDelegate: Delegate(),
       delegateQueue: .main)
   let asset = AVURLAsset(url: url)
   let task = session.makeAssetDownloadTask(asset: asset,
       assetTitle: "Local Atmos Test",
       assetArtworkData: nil,
       options: nil)!
   task.resume()
   RunLoop.main.run()
   ```
   `Delegate` saves `aggregateAssetDownloadTask` location on completion.
6. Open the resulting `.movpkg` in TV.app:
   `open -b com.apple.TV /path/to/file.movpkg`.
7. With `dolby_tool` capture running, observe whether the playback log
   emits:
   - `<<<< FigStreamPlayer >>>>` (instead of `FigFilePlayer`)
   - `[AudioFormat qc+3 ...]`
   - `asbdFormatID = qc+3, Dolby Atmos, ..., is rendering spatial audio`

If any of those three appear, the experiment shows that a local HLS package
can reach the desired TV.app path. If TV.app refuses the package or does not
select complete Atmos, the gate is deeper — tied to TV.app media-library /
Apple TV+ identity, package trust, or title/account/device download policy,
not merely the asset format.

### Stop conditions

Stop the broader investigation if:

- An Apple-managed downloaded title has complete local Atmos and TV.app
  selects it offline. Document the package pattern and capture evidence.
- Multiple Apple-managed downloaded Atmos titles advertise Atmos but persist
  incomplete local Atmos groups. Document this as a download-policy/package
  contents limitation, not a runtime spatialization failure.
- The lower-priority local `.movpkg` recipe succeeds and shows the renderer flag flipping. Document the
  recipe in this report, file a parser issue to detect the
  `FigStreamPlayer` event for local-`movpkg` playback, and ship a how-to
  in the dolby-tool UI.
- The lower-priority local `.movpkg` recipe fails. Paths 7 / 8 / 9 / 10 are
  then de-prioritized because they test the same HLS-engine idea on
  different launchers and the TV.app path already declined.
- Apple HLS Tools cannot be installed and we cannot produce a valid
  fragmented HLS source. In that case the experiment is blocked on
  packaging and the issue should record the blocker rather than spin.

## Suggested follow-up issues to file

- New issue: "Add a `.movpkg`-aware capture to dolby_tool: detect
  `FigStreamPlayer` events on locally-created packages and surface the
  asbdFormatID transition in the capture summary."
- New issue: "Parse `<<<< FigStreamPlayer >>>>` / `fpfs_*` audio events
  and tag them as `pipeline_engine = FigStreamPlayer` (mirrors the
  FigFilePlayer change suggested in `ISSUE_12_LOCAL_SPATIAL_RENDERING.md`)."
- New issue: "Document the experimental `.movpkg` recipe in the README so
  future captures can reproduce it without rewriting the Swift downloader."
- Optional: "Probe TV.app `itls://`/`itlss://`/`itvls://`/`itvlss://` URL
  handlers with a local HLS server; record whether any of them open."
