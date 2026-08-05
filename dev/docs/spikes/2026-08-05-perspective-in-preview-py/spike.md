# Perspective camera in `preview.py` — feasibility + perf + correctness

**Question.** `actor preview` (`preview.py`) is a strictly ORTHOGRAPHIC pure-Python rasterizer
(no camera, no perspective, no polygon clipper). The plan: add a posed PERSPECTIVE camera + the
SHOT grammar to it so ONE renderer serves both `actor preview` (ortho) and `level preview`
(posed perspective, whole level), retiring the Rust `uedcli-native/src/render.rs`. Does
perspective fit `preview.py` cleanly, is pure-Python raster fast enough for a draft, and does a
prototype agree with the Rust renderer being retired?

**Method.** A standalone harness (`proto_render.py` + `run_spike.py` + `clip_check.py`, all
committed here) ports `render.rs` into Python and feeds it the SAME
`preview_native.build_scene` output (world-space textured polys + texture table) that the Rust
`render_frame` consumes — so the Rust frame is an exact apples-to-apples oracle. Poses come
from the real grammar (`preview_shots.parse_shot`/`resolve_pose` + `preview_native.camera_basis`).
Run: `.venv/bin/python dev/docs/spikes/2026-08-05-perspective-in-preview-py/run_spike.py [N]`.

> Host limitation: the retail Deus Ex content (and the castle trunk from
> `2026-07-16-native-preview-anchor`) live behind dead `neob91` symlinks — not present on this
> host. So the CSG figure is measured on synthetic scenes and the castle numbers are cited from
> the committed `2026-07-16-native-preview-anchor/perf.md`, not re-run. A synthetic checker
> texture stands in for game content (the raster cost is per-pixel-sample, texture-source-agnostic).

## Verdict

**FEASIBLE and byte-level correct.** The perspective prototype matches `render.rs` to a
**mean-abs pixel diff of 0.000–0.001 / 255** across every scene and the near-clip cases — i.e.
the two renderers are effectively identical. Pure-Python raster of a whole-level frame at
`--size 1024` is **~1–4 s**, which is an acceptable offline-draft cost and is NOT the bottleneck
(the CSG solve dominates, as `perf.md` already found). Recommend proceeding with the
consolidation.

## 1. Feasibility — how the port fits

The load-bearing insight: under a perspective projection, on a planar face `1/d`, `u/d`, `v/d`
are AFFINE in screen space (exactly what perspective-correct interpolation exploits). So
`preview.py`'s existing affine solver (`_affine_on_plane`) and its even-odd scanline fill
**carry over unchanged in structure** — the prototype imports `_affine_on_plane` verbatim.

What perspective needs that `preview.py` lacks, in order of invasiveness:

- **NEW: a near-plane Sutherland–Hodgman clip** (`_clip_near`, camera space, `d >= NEAR=4.0`).
  This is the key unknown called out in the plan — `preview.py` has no clipper. It is ~20 lines,
  self-contained, and provably correct (see §3 clip cross-check). Without it, geometry behind or
  straddling the camera wraps into view.
- **NEW: a camera-space transform** per vertex (world → `(d, r, u)` via the SHOT basis) — ~10
  lines, ahead of projection.
- **CHANGED: the fill inner loop** gains ONE per-pixel divide (`u = (u/d)/(1/d)`), and the depth
  test flips sense (`zbuf` stores `1/d`, larger = nearer, vs ortho's smaller-depth-nearer).
- **The one helper that does NOT carry over:** `preview.py` anchors its affine solve on
  WORLD-space plane probes (`_plane_screen_probes`, stepping out in world space). Under
  perspective a world probe can fall behind the near plane, where its projection is invalid. The
  perspective path instead solves the affine `1/d`/`u/d`/`v/d` maps from the CLIPPED polygon's
  own projected vertices (`_solve_affine` here). `_affine_on_plane` is reused; `_plane_screen_probes`
  is replaced.

Net: a new clip+transform front-end plus a perspective variant of the fill; the affine math and
scanline are shared. This is an ADDED mode, not a rewrite — `actor preview` keeps its ortho path
(ortho depth/UV stay affine in screen space with no divide), and `level preview` gets the posed
perspective path. Moderately localized, not invasive.

## 2. Performance — pure-Python raster at `--size 1024`

One posed perspective frame, textured, fixed pose (~61% frame coverage), host-native
Linux/x86_64. `render.rs` (release) shown as the oracle/baseline:

| scene (brushes) | surviving surfaces | CSG solve (coarse core) | Rust `render_frame` | **Python prototype** | ratio |
|-----------------|--------------------|-------------------------|---------------------|----------------------|-------|
| 65              | 424                | 0.13 s                  | 0.030 s             | **1.13 s**           | 38× |
| 145             | 920                | 0.90 s                  | 0.044 s             | **1.33 s**           | 30× |
| 257             | 1608               | 4.09 s                  | 0.065 s             | **1.83 s**           | 28× |
| 401             | 2488               | 13.82 s                 | 0.089 s             | **2.05 s**           | 23× |

A full-frame (100% coverage) pose costs more: **2.7 s @424, 3.0 s @920, 4.1 s @1608 surfaces**.

Reading it:

- Pure-Python raster is **low single-digit seconds** at 1024 — well within an offline draft
  budget. The owner's "ship pure-Python, accept perf" ruling holds; the accepted cost is a
  **~25–40× per-frame slowdown vs Rust**, absolute ~1–4 s.
- Raster time grows SUB-linearly in surface count (it is dominated by covered pixels ≈ constant
  at fixed coverage, not face count), so it does not blow up on a busy level.
- **The CSG solve dominates, not the raster** — the same conclusion as `perf.md`. Retiring
  `render.rs` does not touch the bottleneck.
- Real-castle extrapolation: `perf.md` records Rust castle raster at 0.35 s/frame (1280×960).
  At the ~25–40× ratio, a pure-Python castle frame would be ~**9–14 s @1280×960**, ~**6–10 s
  @1024** — the high-overdraw end of the range. (Extrapolated, not measured — retail content
  absent.)
- CSG note: the coarse `build_geometry` core is cheap on simple convex cubes (splits cleanly);
  the castle's committed **8.0 s** is real retail geometry with far messier splits — cited, not
  reproduced here.

## 3. Correctness sanity — prototype vs `render.rs`

Same polys/textures/camera into both renderers, mean-abs pixel diff:

- Whole scenes (§2 table): **0.000–0.001 / 255** every run — visually and numerically identical.
  `frame_rust.png` / `frame_py.png` / `frame_diff8x.png` (diff amplified 8×, reads flat) are
  committed. Geometry, perspective, occlusion (z-buffer), shading and perspective-correct texture
  placement all agree.
- **Near clip in isolation** (`clip_check.py`, mirrors `render.rs`'s
  `near_plane_clips_geometry_behind_camera`, cross-checked Python vs Rust): a wall BEHIND the
  camera renders nothing (both 0 px); a wall STRADDLING the near plane clips to identical partial
  coverage (both 1664 px); a wall in front fills identically (both 4096 px). mad 0.0000 all three.

Both harnesses self-assert (`mad < 1.0`) and exit non-zero on drift — re-runnable regressions for
the finding. The remaining f32-vs-f64 gap (`render.rs` is f32, Python f64) is the sole expected
source of the ≤0.001 residual, matching the declared `--faces textured` divergence in
`architecture.md`.
