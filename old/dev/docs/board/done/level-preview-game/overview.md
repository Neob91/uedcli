+++
priority = "p?"
kind = "unknown"
summary = "`level preview --game` — ONE-EXEC batch drive (from ~9s to ~2.2s warm)"
+++

# `level preview --game` — ONE-EXEC batch drive (from ~9s to ~2.2s warm)

— BUILT + live-verified
2026-07-17 (spec `spec.md`; decision 14:42; 2-reviewer
design gate). Replaced the warm container's ~8-10 per-op `docker exec`/`stats`/`cp` round-trips with
ONE `docker inspect` (reuse gate) + ONE `docker exec` of the in-container `preview_batch.py`
(deliver → 3-phase travel/skip → per-shot `PrepareCamera`+settle+X-grab → framed PNGs on stdout).
Renamed link verb `Screenshot`→`PrepareCamera` (poses only, replies sync; the settle moved to the
batch because `bPlayersOnly` freezes the link actor's Tick/Timer). `ensure_image` source-hash marker
fast-path (skips docker on the warm path). A persistent published-port DAEMON was designed then
REJECTED by review. Live: cold ~60s → **warm reuse ~2.2s** → **10-shot 8.37s all distinct** → idle
self-death. +`test_preview_batch.py` (fake link). **Remnant (→ inbox):** ≤1s target unmet (dev-CLI
Python startup floor) — needs the Nuitka binary + folding the 2nd docker call + settle tuning.
