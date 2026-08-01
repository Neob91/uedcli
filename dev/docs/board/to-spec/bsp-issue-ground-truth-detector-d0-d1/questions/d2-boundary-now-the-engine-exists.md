# Now that the offline engine exists, is D2 still "for later," and where is the D1/D2 line?

## Context

The spec treats D2 (the fully-offline engine) as an optional multi-week future port, and the sibling
board item `d2-fully-offline-bsp-csg-collision-engine` is marked FOR LATER on that basis. That
premise is stale: the engine substrate is built in Rust and validated against editor goldens (see
this item's `spec.md` Pre-spec audit notes). D2's one distinctive value — catching silent-absence
holes by diffing should-vs-did — now needs a diff/report layer on the existing native build, not a
new engine.

Decisions for the owner:
- (a) Keep D2 parked as "for later" on PRIORITY grounds, even though the engine exists — accept that
  the detector item ships without silent-absence coverage.
- (b) Pull D2 forward, since only the diff/report layer remains, not the engine.
- (c) Merge D2 into this detector item — one native-build detector covering located issues AND
  silent-absence — and retire the D0/D1-vs-D2 split entirely.

Recommendation: independent of priority, D2's overview must be re-scoped to "diff/report over the
native build" (its engine premise is dead). Whether that work is now vs later, and whether it stays
a separate item, is the owner's call.

## Answer

<!-- Empty = open. -->
