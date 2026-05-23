# Why TV.app specifically fails, and what we can(not) do about it

## The exact call site

For local-file items, TV.app's MediaPlaybackCore calls

```
-[AVPlayerItem(MediaPlaybackCore)
    mpc_updateAVAudioSpatializationFormatsForPlayerAudioFormat:spatialPreference:]
```

with a `spatialPreference` value that causes
`_updateAllowedAudioSpatializationFormats` to strip Multichannel from the
allow mask on a 2ch route. The HLS sibling
`_updateAllowedAudioSpatializationFormatsFromFigItem` does not run for
`FigFilePlayer`-backed items, so there is no second pass to put
Multichannel back.

The **actual integer value** of `spatialPreference` for local-file items
has not been captured. The dtrace probe ran on the framework selector but
did not record arg2. This is a cheap follow-up — see
`06_next_steps_and_edge_cases.md`.

## Entitlements audit

`codesign -d --entitlements - /System/Applications/TV.app` (2026-05-23)
shows many private entitlements:

- `com.apple.private.commerce`, `com.apple.private.appstored`
- `com.apple.private.fpsd.client`
- `com.apple.private.tcc.allow`
- `com.apple.avfoundation.allow-system-wide-context`
- `com.apple.avfoundation.allows-access-to-device-list`
- `com.apple.avfoundation.allows-set-output-device`

**No spatial-audio-specific entitlement appears.** The
`allow-system-wide-context` / `allows-set-output-device` entitlements
control device selection, not spatialization mask. TV.app's local-Atmos
failure is **behavioral product code**, not entitlement-based.

This is further confirmed by SpatialProbe: an ad-hoc-signed binary with
no entitlements at all reaches `spatialization = 1` on the same hardware,
same file, same route.

## Preference keys that exist but do not apply

TV.app's strings expose:

- `downloadDolbyAtmos`
- `downloadMultichannel`
- `preferredDolbyAtmosPlaySetting`
- `multichannelAudioStrategy`
- AVF symbol `AVCFPlayerSetMultichannelAudioStrategy`

`defaults read com.apple.TV` showed no current keys with these names, and
the `mpc_updateAVAudioSpatializationFormatsForPlayerAudioFormat:` call
site was not observed reading any preference value during the dtrace
window. **No `defaults` lever has been confirmed**, but the keys have not
been actively written and tested either — also a cheap follow-up.

## SIP / hook feasibility

| Route | Result on a normal SIP-enabled machine |
|---|---|
| Modify `/System/Applications/TV.app` on disk | Blocked: sealed read-only system volume, `restricted` file flags, library validation |
| Patch + re-sign a copy as TV.app | Loses Apple platform signature and private entitlements; not the same product path |
| `DYLD_INSERT_LIBRARIES` / dylib injection | Blocked: hardened-runtime library validation, no `cs.disable-library-validation` entitlement |
| Frida / LLDB / task-port | Not reliable for an Apple platform binary; even DTrace required disabling debug/dtrace SIP restrictions |
| `defaults` override | No key observed mapping to the local-file `spatialPreference` call site |

Verified locally on 2026-05-23:
- `csrutil status`: enabled
- `csrutil authenticated-root status`: enabled
- `/` mounted `apfs, sealed, local, read-only, journaled`
- TV.app signature `flags=0x12000(library-validation,runtime)`,
  `Platform identifier=26`
- Gatekeeper: `source=Apple System / origin=Software Signing`

**Conclusion:** a practical TV.app patch of the local-file spatial
preference is not available with normal SIP protections. DTrace was
enough to *observe* the call site, not enough to *change* it.

## What "TV.app local works" would require

One of:

1. A documented Apple-supplied user preference that maps to the
   `spatialPreference` value. None known.
2. A `defaults`-writable internal key that bypasses the local-item branch.
   None confirmed; cheap to try.
3. Getting TV.app onto `FigStreamPlayer` for a user-supplied asset. The
   asset has to be loaded as HLS, not as a file. `.movpkg` is the
   Apple-blessed container for "persisted HLS" — but the tested
   externally-built `.movpkg` was ignored by TV.app, and Apple TV+
   downloads on this account did not persist a complete Atmos audio
   group locally (see `04_paths_explored.md`).
4. A future macOS / TV.app update that changes the call-site behavior.
