+++
priority = "p?"
kind = "unknown"
summary = "Small-features bundle (unattended build #2)"
+++

# Small-features bundle (unattended build #2)

— BUILT 2026-07-18. Three offline features:
(5) **`actor bbox <names…|->`** — world AABB (min/max/size/center) enclosing the passed actors as
ONE box (multi-actor case IS the union — no `--union` flag); reuses `writes.union_bounds` (honours
rotation/scale/location, point actor = zero-size box); `--field min|max|size|center` bare
extractor + `--json`; count summary → stderr; unknown name → clean exit 2. (6) **`--json` output**
on `actor find` (JSON name array), `brush poly list` (`{actor, polys:[…]}`), `project show`
(`{root,game,maps,prefabs,catalog,search_path}`), and the new `bbox` — default text output
unchanged. (7) **`--rotate PITCH,YAW,ROLL`** on the generators (`brush build`/`actor build`) —
SETS the `Rotation` field absolutely (fresh actor = identity, no ambiguity), stored not
vertex-baked, warns off-grid on brushes; NOT on `actor add`. All regression-tested
(`test_bbox.py` + extensions to generators/trunk-verbs/project-show); Python suite green.
