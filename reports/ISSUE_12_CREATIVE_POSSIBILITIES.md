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
knows how to open a `.movpkg` directly. Playback of a `.movpkg` goes through
the CoreMedia HLS pipeline (FigStreamPlayer / FigStreamProxy), not
FigFilePlayer, because the asset is HLS-backed.

This is the highest-confidence creative path.

## Ranked creative paths

Ranked by confidence that the path actually flips the renderer state, given
what we already know.

### Tier A — most likely to actually engage FigStreamPlayer + qc+3

1. **Build a `.movpkg` from the local Atmos file via `AVAssetDownloadTask`**
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
   - Expected: TV.app routes the asset through FigStreamPlayer, asbdFormatID
     becomes `qc+3`, and `mediaFormatinfo ... is rendering spatial audio`
     can flip to `true` on built-in MacBook speakers.
   - Falsification: if asbdFormatID stays `ec+3`, then `.movpkg` import does
     not change the engine, and the engine choice is made deeper than
     "asset type."

2. **Hand-author a `.movpkg` against the published schema**
   - `/System/Library/Schemas/HLSMoviePackage.xsd` defines the package
     format. A minimal `boot.xml` with one PersistedStore stream pointing
     at a local fragmented-mp4 file may be enough to make TV.app open it.
   - Same expected outcome as path 1. This path is cheaper if we can
     reproduce a valid `boot.xml` + `root.xml` directly without writing a
     Swift downloader, but it is less Apple-blessed and may hit schema
     validation rejection.

3. **Apple HLS Tools (`mediafilesegmenter` + `mediastreamvalidator`)**
   - Not installed on this machine. Download from
     `developer.apple.com/download/applications/` (free, Apple ID needed).
   - Once installed, `mediafilesegmenter` produces a canonical HLS bundle
     (master.m3u8 + media.m3u8 + .ts/.m4s segments) without re-encoding the
     ec-3 / Atmos audio. Pair with paths 1 or 2 above to feed the packager.
   - This produces the most Apple-canonical HLS package, which gives the
     highest chance the AVAssetDownloadTask in path 1 will succeed.

### Tier B — promising but unproven

4. **TV.app "Live Stream URL" schemes (`itls://`, `itlss://`, `itvls://`,
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

5. **`open -b com.apple.TV http://localhost:8000/master.m3u8` against a
   local HLS server**
   - TV.app does not advertise generic `http`/`https` handler ownership for
     m3u8, so this is most likely a no-op. Still cheap to try.
   - Same expected outcome as path 4 if it works.

6. **Open via Safari in fullscreen video**
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

7. **Open in QuickTime via File → Open Location**
   - QuickTime accepts HLS URLs via `Open Location`. Same caveat as Safari:
     QuickTime is not TV.app, so the TV-specific app-level log line will
     not appear, but the underlying CoreMedia engine choice is what
     matters audibly.

### Tier C — unlikely to flip the engine

8. **Library import** (`File → Import` of an mp4/m4v into TV.app library)
   - Still a file-backed asset, still FigFilePlayer. Useful only as a
     control to confirm import does not help.

9. **Rename `.m3u8` to `.m4v` and hope TV.app does content sniffing**
   - TV.app will probably honor the UTI and refuse, or treat it as a corrupt
     m4v. Cheap to verify and dismiss.

10. **Force the engine via `defaults` plist or experimental TV.app flags**
    - No public defaults are documented for this. Skip unless a specific
      hidden flag is discovered.

### Tier D — out of scope here but worth noting

11. **Custom AVPlayer host app**
    - A 50-line SwiftUI macOS app that uses `AVPlayer` against
      `http://localhost:8000/master.m3u8` (or against a `.movpkg`),
      with `playerItem.allowedAudioSpatializationFormats = .multichannel`,
      `playerItem.audioTimePitchAlgorithm = .spectral`, etc.
    - This is not TV.app, so the "hidden Apple technology in TV.app" framing
      does not strictly apply, but the underlying CoreMedia / Atmos /
      spatial-renderer stack is the same. If the local source rendered via
      this app sounds the same as TV.app + Apple TV+ on the same MacBook
      Pro Speakers, then the "hidden Apple technology" is just
      FigStreamPlayer + qc+3, and any small Swift app can use it.

12. **Music app for Atmos audio-only files**
    - Apple Music's Atmos catalogue plays through CoreMedia HLS. A local
      `.m4a` with Atmos JOC may go through Music.app's local FigFilePlayer
      path. Same engine question as TV.app, likely same outcome. Mentioned
      here only because it is a second app for comparison.

## Recommended next experiment

Run path 1 (`AVAssetDownloadTask` against a local HLS server, then open
the produced `.movpkg` in TV.app) end-to-end with `dolby_tool.tvlog`
capture. Concrete order:

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

If any of those three appear, the experiment succeeds and we know the gate
is purely "is the asset HLS-backed." If none of them appear and we get
`FigFilePlayer` + `ec+3` again, the gate is deeper — probably tied to
TV.app's media-library / Apple TV+ identity, not the asset format.

### Stop conditions

Stop the broader investigation if:

- Path 1 succeeds and shows the renderer flag flipping. Document the
  recipe in this report, file a parser issue to detect the
  `FigStreamPlayer` event for local-`movpkg` playback, and ship a how-to
  in the dolby-tool UI.
- Path 1 fails. Path 4 / 5 / 6 / 7 are then de-prioritized because they
  test the same engine choice on different launchers and the engine
  already declined.
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
