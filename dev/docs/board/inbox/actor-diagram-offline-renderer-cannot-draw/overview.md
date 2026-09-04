+++
priority = "p?"
kind = "bug"
summary = "actor diagram offline renderer cannot draw revolve/extrude swept solids"
+++

# actor diagram offline renderer cannot draw revolve/extrude swept solids

`actor diagram` (both `--faces wire` and `--faces textured`) renders a `brush build revolve`
solid as a flat quad / drops it entirely — the swept geometry is not drawn. `brush build`'s own
help already warns that the offline draft renderer assumes convex solids; this is the same class
of gap for the diagram renderer.

Repro (no game assets needed):

```
P="--project dev/games"
uedcli $P brush build revolve --point 160,0 --point 300,0 --point 300,240 --point 160,240 \
  --angle 90 --segments 8 --axis z --at 0,0,0 --base-name R > r.t3d
uedcli $P actor diagram --from-t3d r.t3d --layout single --view iso --out r.png   # flat quad, not a swept solid
```

Impact: revolve/extrude geometry (curved corridors, arches, cornices) can't be previewed offline;
only `level photo --game` (real engine) shows them. Found 2026-09-04 while trying to showcase a
revolved turning corridor in the README. Not triaged; likely needs the diagram renderer to
tessellate non-convex/multi-cap swept brushes the way UnrealEd does.
