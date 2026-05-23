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

### Tier C — promising but unproven

7. **TV.app "Live Stream URL" schemes (`itls://`, `itlss://`, `itvls://`,
   `itvlss://`)**
   - These are exposed in TV.app's Info.plist but undocumented. They look
     like Apple's IPTV/cable-provider live stream handlers.
   - Try `open "itls://localhost:8000/master.m3u8"` (and the other three
     variants) with a local HLS server running and capture the log stream.
   - Expected: if TV.app interprets the URL as HLS and starts a live
     playback, FigStreamPlayer takes over and the renderer flag can flip.
   - Falsification: if TV.app errors out, ignores the URL, or routes
     through a placeholder UI ("This provider is not supported in your
     region"), this path is dead.

8. **`open -b com.apple.TV http://localhost:8000/master.m3u8` against a
   local HLS server**
   - TV.app does not advertise generic `http`/`https` handler ownership for
     m3u8, so this is most likely a no-op. Still cheap to try.
   - Same expected outcome as path 7 if it works.

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

10. **Open in QuickTime via File → Open Location**
   - QuickTime accepts HLS URLs via `Open Location`. Same caveat as Safari:
     QuickTime is not TV.app, so the TV-specific app-level log line will
     not appear, but the underlying CoreMedia engine choice is what
     matters audibly.

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
