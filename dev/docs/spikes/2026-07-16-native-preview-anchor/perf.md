# S7 acceptance + perf record (castle trunk, 2026-07-16)

**Trunk:** the full castle, regenerated from `Maps/Test_Castle.dx` via
`../2026-07-15-native-materialize/harness/ingest_dx_trunk.py` (161 actors / 95 brushes /
622 texture refs, all qualified from the map's own import table, 0 misses) into
`_scratch/castle/uedctl/maps/foobar`.

**Batch:** 8 shots at 1280×960 / FOV 75 — interior, approach, exterior bird's-eye (the shot
the editor backend could never take), straight-down top-down, two orbit ring shots, a
look-at-roofline, and a gatehouse look-up.

**Wall clock (host-native, Linux/x86_64, release build):**

| run | time |
|---|---|
| 8 shots end-to-end (`bin/uedctl level preview …`) | **11.4–11.5 s** |
| 1 shot end-to-end | 9.0 s |
| `build_geometry` (Rust CSG carve of the 95-brush trunk) | **8.0 s** (profiled) |
| trunk read | 0.11 s |
| texture decode (9 distinct packages/textures) | 0.24 s |
| rasterize + PNG encode per frame | ~0.35 s |

**Verdict vs the ≤10 s soft target:** an 8-shot batch misses by ~1.4 s, and the cost is
entirely the one-time `build_geometry` call — NOT the rasterizer (0.35 s/frame; rayon rows,
the spec's known lever, would buy nothing here). The CSG core belongs to the
native-materialize line (this build's concurrency contract forbids touching it); boarded as
an inbox item (preview needs neither collision hulls nor render bounds — skipping
`bsp_build_bounds` for preview-only builds is the obvious lever, needs coordination).

**Eyeball pass observations (all draft-acceptable):**
- Bird's-eye / top-down / orbit / look-at all compose correctly; the moat renders (textured
  water sheet — portal faces render opaque by design), gatehouse doors + planked bridge read
  clearly, tower cones shade distinctly from walls.
- Small BLACK SPECKLES on tower-roof cones at some angles — coplanar-fragment z-fighting
  (the known N-2 un-merged coplanar residuals) — boarded, don't chase (plan §2 said board a
  semisolid/render artifact rather than chase mid-build).
- The "sky" above the ramparts is the airspace ceiling's texture (correct v1 behavior:
  `PF_FakeBackdrop` renders its texture like any face; no sky-zone projection in the draft
  tier).
