+++
priority = "p2"
kind = "debug"
summary = "`brush build cylinder/cone --sides > 16` now tiles the cap (was one invalid >16-vertex face)"
+++

# `brush build cylinder/cone --sides > 16` now tiles the cap

Fixed. `cylinder`/`cone` build their end cap(s) via `profile.convex_pieces`, exactly like `extrude`:
a convex ≤16-vertex ring is one cap face per end (`--sides ≤ 16` byte-identical to before), and
above 16 the cap is tiled into convex ≤16-vertex pieces — an engine `FPoly` holds at most 16
vertices (`kb/csg-bsp.md` §5.2). No `--sides` upper bound, no CLI change.

`spec.md`/`plan.md` stay here: they are the shared ephemeral spec/plan for the whole
extrude/revolve/units feature (this item is its deferred §12 remnant), still cited by the open
`brush-build-revolve-allow-a-profile-touching` and `brush-build-cylinder-cone-axis-x-y-z` items.
