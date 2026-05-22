# Repository Review (initial push → current upstream)

## Scope reviewed
- Commit history from first commit to current `HEAD` on branch `work`.
- Current codebase architecture, runtime behavior, and risk areas.

## Commit timeline
1. `f37d118` — Replaced prior scaffold with Python/FastAPI `dolby-tool` app.
2. `917ba61` — Migrated dependency/runtime workflow to `uv`.
3. `63aa833` — Pinned Python 3.14, refactored launcher entrypoint, lint updates.
4. `a489ba2` — Fixes for stop flow, drag/drop behavior, and Safari HTTPS-only handling.
5. `a353e60` — Launcher adjusted to open Safari.
6. `0ad430f` — Drag/drop lookup fallback for external/unindexed volumes.
7. `b8a5add` — README refresh for Python/uv and UX details.

## Current architecture
- **Backend:** FastAPI app with REST endpoints (`/api/inspect`, `/api/compare`, `/api/find`, `/api/list`, `/api/pick`) and a WebSocket endpoint (`/ws/tvlog`).
- **Core logic:**
  - `inspect.py` wraps `ffprobe` (+ optional `mediainfo`) and normalizes DV/HDR/audio metadata.
  - `compare.py` generates per-file scorecards and multi-file winner labels.
  - `tvlog.py` tails macOS unified logs and parses playback telemetry.
- **Frontend:** static single-page app (`web/index.html`, `web/app.js`, `web/styles.css`) with tabs for Inspect / Compare / TV Capture.
- **Runtime tooling:** `uv`-managed Python project with script entrypoint and bash launcher.

## Strengths
- Clear module boundaries and responsibilities.
- Good UX fallback strategy for drag/drop path resolution on macOS browser differences.
- Pragmatic resilience around subprocess tooling (`ffprobe`, `mediainfo`, `log`, `osascript`).
- Data model is rich enough for practical DV/HDR triage and side-by-side ranking.

## Risks / gaps observed
1. **Path-based trust model exposed on localhost API**
   - APIs inspect/list arbitrary paths on the host machine. This is expected for a local tool, but there is no additional guardrail if the service is exposed beyond localhost.
2. **macOS-only runtime assumptions**
   - Core workflows depend on `log stream` and `osascript`; non-macOS behavior fails by design rather than gracefully disabling features.
3. **Single-process capture state**
   - Global `_capture` state is intentional for a single-user flow, but concurrent clients/tabs can interrupt each other.
4. **Heuristic winner selection/scoring**
   - Compare weighting is opinionated and may not align with all quality preferences (e.g., bitrate-heavy emphasis).

## Recommended next improvements
1. Add explicit host-binding / localhost-only startup checks and warning banner when non-loopback bind is used.
2. Add optional "capabilities" endpoint so UI can proactively disable unsupported features (`osascript`, `log`, `mediainfo`) without trial-and-error.
3. Move compare weights into user-adjustable settings in UI.
4. Add lightweight unit tests for `tvlog.py` parsers and `compare.py` scoring invariants.

## Overall assessment
The project has evolved coherently from initial push to current upstream. The recent sequence of commits improves installation reliability (`uv`) and macOS UX correctness (drag/drop + Safari behavior), while preserving a focused local-tool architecture.
