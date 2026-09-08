# Geometry-alignment eval — UNATCO reference solutions

`index.html` is the reference-solution page for two UNATCO HQ tasks (widen Manderley's office,
raise its ceiling), used to validate what "correct" means per aspect before grading subagent
trials against it.

## Pipeline — never hand-build a picture

1. `scripts/gen_diffs.py` — the single source of truth. Defines, per aspect, the exact ops (or
   `assert_unchanged` for actors that must NOT move) that make it correct. Writes `diffs/*.json`.
2. `scripts/render_from_diff.py` — for each aspect diff: applies the WHOLE task's diff (every
   aspect combined) to the untouched baseline trunk, then renders `actor diagram` highlighting
   just that aspect's actors, into `img/<id>.png`. A picture always reflects the fully-correct
   scene, never a partially-applied one — this is what fixed the earlier bug where a "CORRECT"
   picture was quietly rendered from a trunk missing one other aspect's fix.
3. `scripts/build_page.py` — assembles `index.html` from `diffs/*.json` plus the small set of
   hand-captured supplementary photos in `img/` that no diff drives (`EXTRA_PHOTOS` in the script).

Re-run in that order after editing any diff. Never hand-edit a `diffs/*.json` or a picture directly.

## Diff JSON shape

```json
{
  "id": "t1_wall",
  "ops": [
    {"kind": "brush_vertex_move", "actor": "Brush418", "at": [[x,y,z], ...], "by": [dx,dy,dz]},
    {"kind": "actor_move", "actors": ["Switch6", ...], "by": [dx,dy,dz]},
    {"kind": "assert_unchanged", "actors": ["Light156", ...]}
  ],
  "highlight": ["Brush418", "Brush420"]
}
```

This is also the grading oracle: for each aspect, apply the same ops to a subagent's trunk actor
set (or just read its final state) and compare against what applying the ops to the baseline
would produce; an `assert_unchanged` actor must equal its baseline value exactly.

## Base trunks

`unatco_gt` (untouched UNATCO baseline) lives in job-scratch, not this repo. Set
`BASE_TRUNKS_DIR` to wherever your own extraction lives before running the scripts.
