+++
priority = "p2"
kind = "debug"
summary = "`level doctor` reports a MOVER built via `brush intersect` as non-manifold / not watertight — FALSE POSITIVE"
+++

# `level doctor` reports a MOVER built via `brush intersect` as non-manifold / not watertight — FALSE POSITIVE

A glass-door mover (solid frame + subtracted opening + flush
**semisolid** translucent pane, welded with `brush intersect`) trips 16–32 `watertight … shared by 3
faces (non-manifold)` errors, because the semisolid pane's side faces intentionally COINCIDE with the
subtracted reveal walls (that non-merging is the whole point — see
`leveldesign/general/recipes/glass.md`). But (a) a **mover never goes through world BSP**, so the
manifold/CSG-hole requirement simply doesn't apply to it, and (b) an intentional coincident-semisolid
interior is a valid UE1 construction. The door renders correctly in `level photo --game` regardless.
Doctor's watertight check should **skip mover brushes** (and/or brushes with intentional coincident
semisolid faces), or downgrade to info. (Surfaced building the DeusExMover glass door, live-verified
2026-07-25.)
