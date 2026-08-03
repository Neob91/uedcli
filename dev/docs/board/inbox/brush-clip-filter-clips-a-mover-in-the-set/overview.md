+++
priority = "p3"
kind = "owner-question"
summary = "brush clip filter clips a Mover in the set; intersect/deintersect refuse one"
+++

# brush clip filter clips a Mover in the set; intersect/deintersect refuse one

> Migrated to `brush-clip-should-be-a-t3d-stdin-filter`'s `questions/clip-a-mover-in-the-set.md`.
> Kept here because this slug is cited from that item's `overview.md`.

The new `brush clip` filter (item `brush-clip-should-be-a-t3d-stdin-filter`) refuses only non-brush
(point) actors. A Mover carries a brush, so a Mover in the piped set gets clipped like any brush —
matching the deleted by-name form and the clip spec, which calls out only point actors.

The sibling generators `brush intersect`/`deintersect` REFUSE a Mover (a mover has no part in world
CSG). Clip is different: clipping a mover's brush geometry is a real operation, so clipping it may be
correct. But the divergence is unstated.

Owner decision: leave clip clipping movers, or refuse them for parity with intersect/deintersect? No
behaviour changed pending the answer — clip currently clips them.
