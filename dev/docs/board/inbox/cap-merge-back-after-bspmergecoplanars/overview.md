+++
priority = "p3"
kind = "unknown"
summary = "Cap merge-back after `bspMergeCoplanars`"
+++

# Cap merge-back after `bspMergeCoplanars`

Materialize an L-profile
`brush build extrude` and count cap SURFACES in the built map. Prediction (an inference from the
`TryToMerge` decode, never observed): the build pass fuses tiles wherever each pairwise merge's
two INPUTS have vertex counts summing to ≤16 — so a 2-piece cap fuses back to one surface and a
3+-piece cap may fuse only partially. A by-product is whether `Engine.dll`'s `RemoveColinears`
carries a convexity reject our Rust port omits. Spec §6.1 / §11 of the (now landed) profile
generators; nothing depends on the answer, it is a documentation-truth item.
