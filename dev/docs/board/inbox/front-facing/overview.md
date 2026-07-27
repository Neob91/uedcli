+++
priority = "p3"
kind = "implement"
summary = "front-facing"
+++

# front-facing

true-occlusion label filter` — the `--labels` grammar's `poly:vis` ships meaning
**front-facing** (the cheap backface cull). A stricter "don't label a face whose centroid is hidden
behind other geometry" filter is a possible future refinement — either tightening `vis` or a new
filter name — needing a real painter/z-buffer occlusion pass over the projected faces in the stdlib
rasterizer. Optional, low priority; noted from spec `specs/2026-07-22-labels-granularity.md` (A4).
