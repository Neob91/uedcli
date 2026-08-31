# actor rotate

`actor rotate <names…|-> (--by | --to) PITCH,YAW,ROLL [--pivot … | --pivot-actor …]` — rotate a
group around a pivot.

Rotates N actors (point actors + brushes) together — it orbits each Location about the pivot and
composes each orientation into the actor `Rotation` field, **the way UnrealEd stores a rotated
brush** (the PolyList stays local; the engine applies `Rotation` at CSG build). `--by` is a
**relative** rotation in **unreal rotation units** (16384 = 90°) `PITCH,YAW,ROLL` (negatives
allowed); `--to` sets the field **absolutely in place** (Location never moves; excludes `--pivot`).
The pivot is `--pivot X,Y,Z`, or `--pivot-actor NAME`'s Location, or (default) **the `Location` of
the set member nearest the selection's bbox center**. A brush's `Location` is the point that stays
fixed when it turns about itself, and it is an **authored** coordinate — so the pivot inherits
whatever grid you built on rather than being computed and rounded onto a different one. A lone
brush turns in place.

Details that follow from that:

- **Brushes supply the pivot** when the selection has any; otherwise point actors' Locations do. So a
  lone decoration — or several sharing one Location — turns about **exactly** its own Location, and an
  off-grid prop is never dragged onto the grid by turning it.
- **Equidistant members take the alphabetically first Name** — the pivot is always a Location that
  exists in the trunk, never an average of several (which would land off-grid). It does not depend on
  the order names arrive in the pipe. Use `--pivot X,Y,Z` or `--pivot-actor` to pick a different one.
- **Locations are used as authored**, with no filtering. A brush in the raw CSG form
  (`Location=(0,0,0)` with world-space vertices) contributes the world origin, and a set of only
  those turns about the origin — `--pivot`/`--pivot-actor` overrides it.
- **There is no fallback rule**: every actor has an *effective* Location — an unauthored property
  takes its **class default** — so a non-empty selection always has a pivot. The default is resolved
  from the class, not assumed zero: `Engine.Camera` defaults `Location=(X=-500,Y=-300,Z=300)`. The
  class schema is consulted only for an actor that states no Location, so an ordinary rotate stays offline.

> The two reference points differ on purpose. Rotation and scale pivot near the center (you turn a
> thing about its middle). Placement anchors the bbox-min corner — `stash`/`prefab apply --at`,
> `actor duplicate --at`, and stash capture's normalization all land the set's minimum corner on the
> target, because you place a prefab by dropping a corner on a grid point you can read off and type.

A zero result is **written out** (`Rotation=(Pitch=0,Yaw=0,Roll=0)`), not omitted: an actor with no
`Rotation` property takes its *class* default, which is not zero for every class, so `--to 0,0,0`
means "unrotated" only when the rotator is there to say so.

See also: [`brush scale`](../brush/core.md), [`actor move`](move.md).
