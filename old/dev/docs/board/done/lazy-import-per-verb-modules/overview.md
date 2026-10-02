+++
priority = "p?"
kind = "unknown"
summary = "Lazy-import per-verb modules — DROPPED as obsolete (Andrzej, 2026-07-20)"
+++

# Lazy-import per-verb modules — DROPPED as obsolete (Andrzej, 2026-07-20)

The item's premise
(~1s import tax, ~2s→1.1s warm-start win) was measured on the **retired dev CONTAINER** (`_dev-run.sh`,
gone 2026-07-14). Re-measured HOST-NATIVE (the current runtime): `bin/uedcli level select` ≈ 0.21s
total, of which uedcli imports are only **~37ms** (`-X importtime`: `uedcli.cli` cum 37ms, `model`
20ms, `dataclasses` 15ms); the rest is Python+wrapper startup. A lazy restructure would save ~20-30ms
while being invasive on the shared cli/dispatch bottleneck AND constrained (the top-level `dispatch()`
exception guard pins `driver`/`editor`/`geometry` imports). Not worth it — closed, not built.
