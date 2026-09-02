# Spec DRAFT — make `actor diagram` faster

Status: draft for owner review. Numbers below were measured in THIS container (no game content),
so `wire` only; `flat`/`textured` fill cost is estimated, not measured (see Open questions).

## Goal

`actor diagram` is the model-side build-loop viewer, so its latency is felt on every
iterate-and-look cycle. Profile where the time goes and cut it, keeping byte-pinned output identical
except where a lever is explicitly a visible change the owner approves.

## Current state (measured)

Renderer is a pure-Python stdlib rasterizer, `preview.py`. Third-party deps are **Pillow only**
(`bin/_venv.sh` `_DEPS_SPEC`; `pyproject.toml`); NumPy is NOT installed and NOT a dependency.
Default surface: `--layout quad` (four half-size panes), `--size 1024`, `--annotate all` (every face
index + every actor name), `--faces wire` (`cli/parsers/_arguments.py:205` `_preview_opts`).

Fixture: `uedcli/tests/fixtures/level_small.t3d`, 15 actors / 13 brushes. In-process render times
(mean of 6, size 1024):

| Case | annotate=all (default) | annotate=none |
|------------------------|-----------------------:|---
| quad wire | ~500–650 ms | ~90 ms |
| single iso wire | ~450 ms | ~40 ms |

- Pure geometry (wire, no annotations) is cheap: single iso 31 ms @1024, 65 ms @2048.
- PNG encode (Pillow, 1024²) ≈ 30 ms.
- End-to-end CLI (`actor diagram --from-t3d …`, default quad) ≈ 0.47 s wall (adds ~0.15 s Python
  start + parse).

**The dominant cost is the on-face annotation layout, not fill or encode.** cProfile of 3× quad @1024
(3.0 s total, ~1.0 s/quad), by cumulative time:

| Function | file:line | cum (of 3.0 s) |
|---------------------------|-------------------|---
| `_onface_candidates` | `preview.py:1559` | 1.11 s |
| `_draw_painted_decal` | `preview.py:1672` | 1.04 s |
| `_max_inscribed_box` | `preview.py:1458` | 0.90 s |
| `_erode_convex` | `preview.py:1400` | 0.81 s |
| `_clip_ge` | `preview.py:1356` | 0.37 s |
| `_draw_overlap_keyline` | `preview.py:1703` | 0.21 s |
| `_resolve_decals` | `preview.py:1621` | 0.17 s |
| `_scene_geometry` (geom) | `preview.py:1867` | 0.16 s |
| `_line` (wireframe) | `preview.py:540` | 0.12 s |

So ~85 % of a default render is placing each poly's index number **inside its face** via a
max-inscribed-box search (`_max_inscribed_box` erodes the convex face polygon by the glyph box and
clips it against every edge for a grid of candidate centres), plus the overlap key-line. Turning
annotations off drops quad @1024 from ~600 ms to ~90 ms (~7×). Fill (`--faces flat/textured`) and
`--size` are secondary at the default annotate setting.

## Design — options

The lever is the on-face decal placement. Ordered by value, least invasive first.

### A. Speed up the decal placement to BYTE-IDENTICAL output (recommended, primary)

`_max_inscribed_box` recomputes an `_erode_convex` (a full edge-clip over the polygon) for each
candidate centre in a `cols×rows` grid, and `_clip_ge` is called 226 k times per quad. Faithful
speedups that MUST reproduce the same chosen box (so every pinned image is unchanged):

- Hoist per-face invariants out of the candidate loop (face edges/normals, glyph box) instead of
  recomputing inside `_erode_convex`/`_clip_ge`.
- Prune the candidate grid with a cheap reject (a candidate whose axis-aligned distance to the
  nearest edge is already smaller than the current best half-extent cannot win) before the full
  erode — same maximum, fewer full clips.
- Skip the whole search for a face whose projected screen area is below the smallest legible glyph
  (the number would be culled anyway; verify it currently IS culled so output is unchanged).

Tradeoff: preserves every byte-pin and adds no dependency; ceiling is bounded by staying
output-faithful (realistic target ~2–3× on the annotation stage).

### B. Cache geometry shared across the four quad panes

`render_quad_pgm` (`preview.py:2494`) calls `render_brushes_pgm` four times; each re-runs
`_scene_geometry` and per-actor world transforms. World-space actor geometry (`rotation.*`) is
view-independent — compute once, project per pane. Modest (geometry is 0.16 s of 1.0 s) but free of
output change.

### C. A draft/quality knob (visible change — needs owner sign-off, see Open questions)

If A+B miss the target, expose a speed lever. Two candidate spellings (pick one, do not ship both —
`direction/conventions.md` no-alias):

- Lean on the existing `--annotate none|name` (already the fast path) and document it as the "fast
  iterate" setting — zero new surface, but the default stays slow.
- A new `--quality {full,draft}` (default `full`) where `draft` drops on-face index placement to a
  plain centroid dot/number (cheap, no inscribed-box search) and skips the overlap key-line:

  ```
  --quality {full,draft}   render fidelity vs speed (default full). 'draft' places face
                           numbers at the face centroid instead of the largest inscribed box
                           and skips the overlap key-line — a faster look for the build loop;
                           'full' is the publish-quality layout.
  ```

  Tradeoff: `draft` output differs from `full`, so it needs its own pinned goldens; it does not
  change the `full` default anyone relies on.

### D. NumPy vectorization — REJECTED unless the owner lifts the Pillow-only policy

Vectorizing the fill and the inscribed-box test in NumPy would help most on large `--size`/filled
renders, but NumPy is not a dependency and the project is deliberately Pillow-only. This is the
owner's call — see `questions/allow-numpy-dependency.md`. Recommendation: do A+B first; do not add
NumPy for this.

### Recommendation

Do **A + B** (identical output, no new dependency). Reserve **C** (`--quality draft`) only if A+B do
not reach the target. Do not add NumPy (D).

### Proposed target (owner to confirm)

A quad of a ~20-brush selection at the default `--size 1024`, `--annotate all`: **≤ 250 ms
in-process render** (from ~600 ms today), end-to-end CLI **≤ 0.4 s**. The `≥20-brush` quad becomes a
committed perf regression test (wall-time assertion with generous headroom, marked so it can be
skipped on a slow CI box).

## Edge cases

- Byte-pinned goldens (`test_preview.py`, `test_actor_preview.py`, `test_preview_faces.py`) must
  stay green under A/B — that is the correctness bar for those two options. A single changed pixel is
  a regression, not a speedup.
- `--annotate none` and a brush-only scene already skip the decal path; the optimization must not
  regress those.
- `flat`/`textured` carry a one-time class-schema load (`ClassDefaults`, ~0.1–0.3 s cold per class
  per `architecture.md`) that `wire` does not — a separate, fixed cost; measure it on real content
  before claiming a filled-mode number.

## Tests

- Keep every existing preview byte-pin green (proves A/B changed nothing visible).
- Add a wall-time perf regression: a ≥20-brush synthetic scene, quad, default settings, asserting
  under the agreed target with headroom; skippable marker.
- If C ships: pinned goldens for `--quality draft` on the standard fixtures, and a test that `full`
  output is unchanged from today.

## Open questions

- `questions/allow-numpy-dependency.md` — may preview take a NumPy dependency (option D)? Blocks only
  D; A+B+target proceed regardless.
- Confirm the perf target number above.
- Whether to add `--quality draft` (option C) now or defer until A+B are measured on real content.
