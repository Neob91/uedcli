# Confirm the `--faces flat` edge-colour fix and the related rulings made and implemented with it

## Context

RULED by the owner and IMPLEMENTED in S2 of `actor diagram --faces`, kept as the only record of why
`flat`'s colour roles are assigned as they are, and of a second observable a cold review found under
the same root cause.

**The defect.** Two spec rulings were individually fine and jointly empty: §4.5 — a `flat` fill is
the `(front, back)` pair chosen by `_is_front`, unshaded; §4.6/decision 2.5 — `flat` keeps its
wireframe and an edge draws iff its face survived the cull and is front-facing for its brush. Combined,
every drawn edge is painted in exactly its own face's fill colour, so no edge is visible on its own
brush. Measured: a subtracted room with an added pillar and crate rendered as **exactly three colours**,
two flat silhouettes, no interior creases and no boundary between the abutting pillar and crate — the
very failure decision 2.5 was written to prevent.

**The fix, as ruled.** Under `flat` only, each surviving face's edges draw in the **other** member of
its brush's colour pair (non-subtract `_is_front` edges in `back_rgb`, subtract far edges in
`front_rgb`). One line in `_scene_geometry`, no new constant; the CSG hue is preserved because both
members share the hue. Chosen from four real renders (a=as-specified, unusable; **b=partner member,
taken**; c=fixed dark outline, needs a second rule on the black-fill legacy path; d=fade the fill,
moves fill off §4.5's exact palette value). Only b is committed.

**Second observable (same root cause), fixed with it.** `--highlight` was invisible under `flat` on
every non-subtract brush: `vivid` is the pair's front member and the surviving face fills with that
same member. Fix, extending the ruling one step: a filled render has three roles (fill, edge,
highlight) and one two-member pair, so a highlighted face **inverts** — fill takes the partner member,
outline takes its own.

**Also standing, resolved by the review round.** `--layout breakdown` under `flat` used to refuse a
`--focus` it ignores; the refusal is now scoped off `breakdown` (still refused under `single`/`quad`,
where `--focus` reaches the output; S3 removes it entirely).

**Mirror refusal deleted.** Owner ruling: "Mirrored brushes SHOULD WORK CORRECTLY." `flat`'s exit-2
on a mirrored brush is deleted with its test and every doc/`help=` claim (including the destructive
"un-mirror the brush" advice). A reflection negates each face's Newell normal so `_is_front` inverts;
correcting the boolean (`_is_front_corrected`) fixes cull, the three colour roles, the `flat` edge rule
and `occluders` at once. An even number of negative axes is a 180° rotation (det +1), untouched.
`wire` is left uncorrected deliberately (it culls nothing; correcting it changes the byte-identity
golden — parked as `wire-renders-a-mirrored-brush-with-its-front`). Coverage gap closed:
`level_small.t3d` carries three mirrored brushes and now has a committed `flat` golden.

**Third edge-pass ruling — drop the front-facing condition.** Owner ruling: draw edges on any FILLED
face. `draw_edge` becomes "is this face filled". It fixed a back-facing single-sided face (two abutting
`nonsolid` sheets wound away from the camera rendered as one block with zero edge pixels). Cost: on
faceted/abutting geometry a silhouette gains ≤1px in its own hue (55px, 0.084%, in the re-blessed
`level_small.t3d` flat golden). Supersedes §4.6's front-facing condition. Full numbers:
`filled-edges-on-every-face-extend-a-faceted`.

## Answer

<!-- Empty = open. Write the decision here. -->
