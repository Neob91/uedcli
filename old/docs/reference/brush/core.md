# brush core

clip / snap / replace / scale / apply-transform

**`brush clip -|FILE`** is a stateless T3D **filter**: it reads a brush set as a T3D snippet on stdin
(`-`) or from a saved FILE, clips **every** brush in it by one world plane, and writes the clipped
brushes to stdout — so a chamfered box is one pipe:
`brush build cube … | brush clip - --plane 96,0,0 1,0,1 --keep below | actor add -`. The plane is
world-space (`--axis` + `--offset`, or point+normal) and is mapped into each brush's own local frame,
so a rotated/scaled brush clips correctly and keeps its `Rotation`. `--keep below` (default) keeps the
side opposite the normal. Empty stdin is a clean no-op (exit 0); a non-brush (point) actor in the set,
or a plane that would discard a whole brush, is a clean error (exit 2 naming it). A plane that misses a
brush's interior passes that brush through unchanged with a `did not intersect brush <name>` note on
stderr. To clip a **placed** actor, compose with `replace`:
`actor show WALL | brush clip - --plane … | brush replace WALL -`.

**`brush snap -|FILE --grid N --tolerance T`** is a stateless T3D **filter** that cleans off-grid
float noise: it reads a brush set on stdin (`-`) or a FILE, and for every brush rounds each **local**
vertex component to the nearest multiple of `--grid` **when it is within `--tolerance`** of it,
leaving a component farther than the tolerance in place. So a corner that drifted to `x=15.997`
snaps to `16`, while a genuinely off-grid `x=8.5` (nowhere near a 16-grid line) is preserved —
intentional angles survive, only slop is corrected. Snapping is per-axis and per-vertex, so a slant
vertex keeps its off-grid axis and cleans the others. Off-grid coordinates are the main cause of BSP
holes, so this is the tool for cleaning imported or drifted geometry before a build. Both flags are
**required** (no default grid/tolerance would be a silent guess); rounding is half toward +∞. A
`--tolerance` at or above half the grid snaps every component to a grid line — allowed, with a note on
stderr that it will destroy angles. Empty stdin is a clean no-op (exit 0); a non-brush (point) actor,
a non-positive grid, a negative tolerance, or a snap that would push a face non-planar is a clean
error (exit 2 naming it). To snap a **placed** actor, compose with `replace`:
`actor show WALL | brush snap - --grid 16 --tolerance 0.05 | brush replace WALL -`.

**`brush replace <name> -`** swaps a brush's **shape in place** from a piped generator T3D on stdin
(`-` is the sole shape source — the `build → replace -` convention, not a name list), **keeping** the
target's Name, `order_value`, Group, CsgOper, actor-level solidity PolyFlags, and old
Location/PrePivot. Only the incoming **PolyList** is taken (its own Location/PrePivot/Name ignored),
but its **per-surface attributes come with it** — reapply any `brush poly set` edits afterward. Empty
stdin is a clean no-op; input with no brush geometry, or more than one brush, is a clean error
(exit 2). E.g. `brush build cube --width 512 … | brush replace WALL -`.

**`brush scale`** (renamed from `actor scale` 2026-07-20 — MainScale is a brush-family property; a
mesh uses `DrawScale`) sets MainScale on BRUSH actors — `--to` absolute in place, `--by` a per-axis
factor that also orbits each Location about the pivot (`Loc' = P + S·(Loc−P)`). A negative axis
mirrors; there is no separate `mirror` verb (`mirror` = `brush scale --by -1,1,1`). It shares
`actor rotate`'s default pivot, so a lone brush mirrors **about its own `Location`** — in place. A
point actor is rejected.

**`brush apply-transform`** (renamed from `actor apply-transform`) bakes MainScale + Rotation +
PostScale permanently into the brush vertices and resets those fields (the offline
`ACTOR APPLYTRANSFORM`): reverses winding on a mirror/negative determinant, rewrites PrePivot, leaves
Location, rejects movers. `--lock-textures` (the DEFAULT) transforms the texture axes with the
geometry; `--no-lock-textures` leaves the mapping fixed.

See also: [`brush poly`](poly.md), [`brush build`](build.md), [`actor rotate`](../actor/rotate.md).
