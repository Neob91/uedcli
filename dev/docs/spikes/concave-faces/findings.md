# Spike: are UnrealEd brush faces always convex?

**Question.** The on-face number-decal placement (`preview._max_inscribed_box`) has a fast exact path
for convex faces and a slower fallback for concave ones. Is the fallback ever actually needed — i.e.
are UE1 brush faces always convex, or can a face be concave?

**Answer: convex is the strong norm, but NOT a hard invariant.** UnrealEd's brush builders and CSG
produce convex faces (the engine fan-triangulates a face from vertex 0, which only renders correctly
for a convex polygon), and our own `builders.py` tiles the linear staircase into per-step *convex*
faces rather than one concave face precisely because "a non-convex FPoly is a real CSG defect that
`check_convex` rightly rejects." BUT UnrealEd lets you **vertex-edit a brush arbitrarily**, so a
hand-edited (or thus-imported) face *can* be concave. It is not enforced.

**Measured (live 2026-07-23)** with `count_concave_faces.py` against the exported real Deus Ex maps in
`Temp/`:

| map                    | faces  | faces >4 verts | concave | %     |
|------------------------|--------|----------------|---------|-------|
| `hexagon.t3d`          | 2441   | 222            | 14      | 0.57% |
| `downtown.deduped.t3d` | 13013  | 550            | 18      | 0.14% |

So concave faces are **rare but real** (~0.1–0.6% of faces) in shipped maps. `_max_inscribed_box` must
therefore stay correct for concave faces (it detects convexity per face via `_poly_convex_2d` and falls
back to a bounded grid search), NOT assume convexity.

`count_concave_faces.py` is the harness. Run:
`cd Tools/uedctl && env PYTHONPATH=. .venv/bin/python dev/docs/spikes/concave-faces/count_concave_faces.py \
Temp/hexagon.t3d Temp/downtown.deduped.t3d` (re-measure if the map set changes).
