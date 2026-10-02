# actor bbox

`actor bbox <names…|-> [--field F | --json]` — the world axis-aligned bounding box enclosing the
given actors as ONE box.

Honours each actor's rotation/scale/location; a point actor contributes a zero-size box at its
Location. Default prints four labeled `min`/`max`/`size`/`center` lines; `--field
min|max|size|center` prints just that one bare `x,y,z` vector; `--json` emits `{min,max,size,center}`
each `{x,y,z}`. The count summary goes to stderr.

The reported numbers are **tolerance-snapped** to within 0.001 uu of a whole number: UE1's rotator
table is not exact — a 180° yaw carries `sin = -8.742278e-08`, so a ±64 vertex offset leaks ~6e-06
into the cross axis and a brush exactly on `Y=228` would otherwise report `227.999994`, reading as
"off-grid" for geometry whose trunk is exact. A **genuine** fraction (a 2.5-uu semisolid, an
odd-span center) is preserved — the snap only fires inside that band. `brush vertex list` and the
stash summary snap the same way, so every report of a world coordinate agrees. The snap is confined
to reporting: `doctor`, the CSG core and the preview cameras see raw values, because a cleaned
coordinate feeding a geometric *decision* would mask the faults those tolerances exist to catch.
`actor find --within-bbox` compares within the same tolerance, so a box piped from
`actor bbox --field min/max` contains the actor it came from.

See also: [`actor find`](find.md).
