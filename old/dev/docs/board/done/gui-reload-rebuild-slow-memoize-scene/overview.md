+++
priority = "p1"
kind = "debug"
summary = "Fixed: /load and /rebuild rebuilt ClassIndex/ClassDefaults from scratch every call -- now memoized for the serve process's life, per owner ruling 2026-09-28"
+++

# GUI reload/rebuild slow: memoize scene-resolution inputs

Done. Owner asked why the GUI's Reload/Rebuild felt slow and whether a lighter CSG-only build
variant was needed. Profiling (real levels, `dev/games/trunks/`) found the dominant cost of both
was NOT the native CSG/lighting solve: `uedcli/serve/app.py`'s `_scene_inputs(project)` rebuilt a
`ClassIndex`/`ClassDefaults` pair from scratch on every single `/load`/`/rebuild` request, re-parsing
every referenced class's schema with no memo surviving the call (~3s on a real level). This was
deliberate in the original code (a stale schema could silently mis-solve CSG/lighting, and a
project's on-disk package config could change without a `serve` restart) -- relaxing it needed an
explicit owner decision, not a unilateral perf fix.

Owner ruling 2026-09-28: already-loaded packages are never invalidated during a `serve` run; a
manual reload verb is future work, not built here. `_scene_inputs` now memoizes its result for the
life of the process, keyed by `project.root` (a stable, hashable value present on both the real
`config.Project` and the `SimpleNamespace` stand-ins the test suite uses -- not `id(project)`, which
would carry a GC-reuse hazard). No invalidation/fingerprinting logic added, per the ruling.

Separately raised and deliberately NOT done here (bigger, real architecture change, needs its own
design pass): incremental Reload that only re-resolves actors that changed since the session's last
Load, instead of re-deriving the whole trunk every time. Blocked on `_LoadedTrunk`'s tables becoming
actor-addressable and a stable per-texture-ref registry (today's texture indices are shared/deduped
across actors by table position). Not filed as its own board item yet.
