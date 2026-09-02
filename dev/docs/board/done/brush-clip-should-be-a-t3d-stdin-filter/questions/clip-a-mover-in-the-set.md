# Should `brush clip` clip a Mover in the piped set, or refuse it for parity with intersect/deintersect?

## Context

The `brush clip` filter refuses only non-brush (point) actors. A Mover carries a brush, so a Mover
in the piped set gets clipped like any brush — matching the deleted by-name form and the clip spec,
which call out only point actors.

The sibling generators `brush intersect`/`deintersect` REFUSE a Mover (a mover has no part in world
CSG). Clip is different: clipping a mover's brush geometry is a real operation, so clipping it may be
correct. But the divergence is unstated.

No behaviour changed pending the answer — clip currently clips movers.

## Answer

<!-- Empty = open. Write the decision here. -->
