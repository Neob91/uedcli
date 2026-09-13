+++
priority = "p3"
kind = "unknown"
summary = "CSG checkpoint/resume in native BSP core for late-actor edits"
+++

# CSG checkpoint/resume in native BSP core for late-actor edits

Follow-up from the `level photo --native` scene-cache work (owner-directed, not itself a board
item): `build_geometry_bspcsg` always starts from `Model::default()` and
applies brushes in `level.order`; there is no way to hand it a starting `Model` plus only a suffix
of new/changed brushes. CSG is order-dependent — editing actor K leaves the tree state through K-1
untouched in principle, but every brush from K onward is applied against a tree shape that has now
changed, so today any edit forces a full from-scratch rebuild.

A checkpoint/resume capability (accept a starting `Model` + the changed suffix of `level.order`)
would let an edit to one of the LAST actors reuse most of the tree. It would not help an edit to an
early actor (the whole suffix after it is still invalidated), so the payoff is workflow-dependent —
biggest for iterative append-and-preview loops, no help for editing early/foundational geometry.

Scoped as a BSP-core change (`uedcli-native/src/bspcsg.rs`), not touched by the geometry/lighting
split cache landing separately. Not spec'd or spiked — nice-to-have, not committed to.
