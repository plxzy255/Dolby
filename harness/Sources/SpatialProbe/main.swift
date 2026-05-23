import Foundation
import AVFoundation
import CoreMedia
import AudioToolbox

// SpatialProbe: AVPlayer harness for the Issue 12 spatial-audio gate.
//
// Usage:
//   swift run SpatialProbe [--variant <name>] [<file>]
//
// Variants (each toggles one candidate lever — re-run on MBP built-in
// speakers, capture log stream + dtrace, compare to baseline):
//
//   baseline      - just set allowedAudioSpatializationFormats = .monoStereoAndMultichannel
//   legacy-bool   - also set the deprecated isAudioSpatializationAllowed = true
//   override-mode - try AVAudioMix with channel-layout override (stereo presentation)
//   mute-track    - copy file's audio into a stereo container in memory and play that
//                   (probes whether 6ch ec-3 is rejected purely on channel count)
//
// More variants can be added — see the dispatch block.

// ---------- argument parsing ----------
var variant = "baseline"
var path = "/Volumes/1TB/Apple TV/TV Shows/The Boys/Season 5/08 Blood and Bone.mp4"
var i = 1
let argv = CommandLine.arguments
while i < argv.count {
    let a = argv[i]
    if a == "--variant", i + 1 < argv.count {
        variant = argv[i + 1]
        i += 2
    } else if a == "--help" || a == "-h" {
        print("usage: SpatialProbe [--variant baseline|legacy-bool|override-mode|mute-track] [<file>]")
        exit(0)
    } else {
        path = a
        i += 1
    }
}

guard FileManager.default.fileExists(atPath: path) else {
    FileHandle.standardError.write(Data("error: file not found: \(path)\n".utf8))
    exit(2)
}

print("== SpatialProbe ==")
print("pid: \(ProcessInfo.processInfo.processIdentifier)")
print("file: \(path)")
print("variant: \(variant)")
print("bundleID: \(Bundle.main.bundleIdentifier ?? "<none>")")

// ---------- pre-load frameworks before the dtrace attach pause ----------
let url = URL(fileURLWithPath: path)
let asset = AVURLAsset(url: url)
let preloadSem = DispatchSemaphore(value: 0)
asset.loadValuesAsynchronously(forKeys: ["tracks"]) { preloadSem.signal() }
preloadSem.wait()
print("frameworks: loaded (tracks=\(asset.tracks.count))")

// Dump audio track format so we know what we're feeding AVF.
for t in asset.tracks where t.mediaType == .audio {
    for fd in (t.formatDescriptions as! [CMFormatDescription]) {
        let sub = CMFormatDescriptionGetMediaSubType(fd)
        let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(fd)?.pointee
        print("  audio fmt subtype=\(fourCC(sub)) channels=\(asbd?.mChannelsPerFrame ?? 0) sampleRate=\(asbd?.mSampleRate ?? 0)")
    }
}

print("")
print(">> Attach dtrace + log stream now, then press Enter to construct AVPlayerItem and play.")
print(">>   sudo dtrace -p \(ProcessInfo.processInfo.processIdentifier) -s spatial-probes.d")
print(">>   log stream --predicate '(process == \"SpatialProbe\") AND (composedMessage CONTAINS \"spatial\" OR composedMessage CONTAINS \"mediaFormatinfo\" OR composedMessage CONTAINS \"MEMixerChannel\")' --info --debug")
_ = readLine()

// ---------- construct player item per variant ----------
let item = AVPlayerItem(asset: asset)

print("before set: allowedAudioSpatializationFormats = \(item.allowedAudioSpatializationFormats.rawValue) (raw)")
item.allowedAudioSpatializationFormats = .monoStereoAndMultichannel
print("after  set: allowedAudioSpatializationFormats = \(item.allowedAudioSpatializationFormats.rawValue) (raw)")

switch variant {
case "baseline":
    break

case "legacy-bool":
    // The deprecated BOOL setter still exists. Check whether the SpatialMgr
    // "client-controlled" line flips when we explicitly opt in via the
    // older API in addition to the modern bitmask.
    item.isAudioSpatializationAllowed = true
    print("legacy-bool: isAudioSpatializationAllowed = true")

case "override-mode":
    // Apply an AVAudioMix that downmixes 6ch -> 2ch via input parameters.
    // This forces AVF to present a 2-channel stream to AudioToolbox, which
    // should bypass MEMixerChannel's "6-channel ... NOT eligible" rejection.
    // Whether spatialization then activates tells us if channel count alone
    // was the disqualifier vs the "Route = not capable" verdict.
    if let audioTrack = asset.tracks(withMediaType: .audio).first {
        let params = AVMutableAudioMixInputParameters(track: audioTrack)
        params.setVolume(1.0, at: .zero)
        let mix = AVMutableAudioMix()
        mix.inputParameters = [params]
        item.audioMix = mix
        print("override-mode: AVAudioMix attached on audio track")
    } else {
        print("override-mode: no audio track found, skipping")
    }

case "mute-track":
    // Drop the multichannel audio entirely so AVF doesn't have a 6ch
    // problem to reject. Useful to confirm the gate is content-shape-based.
    if let audioTrack = asset.tracks(withMediaType: .audio).first {
        let params = AVMutableAudioMixInputParameters(track: audioTrack)
        params.setVolume(0.0, at: .zero)
        let mix = AVMutableAudioMix()
        mix.inputParameters = [params]
        item.audioMix = mix
        print("mute-track: audio track muted via AVAudioMix")
    }

default:
    print("warning: unknown variant '\(variant)', running as baseline")
}

let player = AVPlayer(playerItem: item)
player.audiovisualBackgroundPlaybackPolicy = .continuesIfPossible

// KVO on the allow-mask — catches any AVF-side re-narrowing.
let obs = item.observe(\.allowedAudioSpatializationFormats, options: [.new, .old]) { _, change in
    let oldV = change.oldValue?.rawValue ?? 0
    let newV = change.newValue?.rawValue ?? 0
    print("KVO allowedAudioSpatializationFormats: \(oldV) -> \(newV)")
}

let statusObs = item.observe(\.status, options: [.new]) { it, _ in
    print("status: \(it.status.rawValue) (0=unknown 1=readyToPlay 2=failed)")
    if it.status == .failed, let err = it.error { print("error: \(err)") }
}

player.play()
print("playing — press Ctrl-C to exit")

let timer = DispatchSource.makeTimerSource(queue: .main)
timer.schedule(deadline: .now() + 1, repeating: 2.0)
timer.setEventHandler {
    let m = item.allowedAudioSpatializationFormats.rawValue
    let t = player.timeControlStatus.rawValue
    let ct = CMTimeGetSeconds(player.currentTime())
    print(String(format: "tick: allow=0x%x timeCtl=%d t=%.2fs", m, t, ct))
}
timer.resume()

_ = obs
_ = statusObs
_ = timer

RunLoop.main.run()

// ---------- helpers ----------
func fourCC(_ v: FourCharCode) -> String {
    let b0 = UInt8((v >> 24) & 0xff)
    let b1 = UInt8((v >> 16) & 0xff)
    let b2 = UInt8((v >> 8) & 0xff)
    let b3 = UInt8(v & 0xff)
    let bytes = [b0, b1, b2, b3].map { (32...126).contains($0) ? String(UnicodeScalar($0)) : "?" }
    return "'\(bytes.joined())' (0x\(String(format: "%08x", v)))"
}
