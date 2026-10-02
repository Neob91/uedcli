+++
priority = "p2"
kind = "unknown"
summary = "No first-class \"flip CSG op\" affordance (add↔subtract)"
+++

# No first-class "flip CSG op" affordance (add↔subtract)

The add/subtract-**twin** idiom
(build a solid, carve its identical void — the *dominant* real-DX workflow) requires
`actor prop set <dup> CsgOper=CSG_Subtract`, with the enum spelling reverse-engineered from generator
T3D. Add `actor duplicate --csg add|subtract` (flip on copy) or a `brush csg set add|subtract` verb so
the workflow is discoverable, not folklore. (Blind-build test, 2026-07-25.)
