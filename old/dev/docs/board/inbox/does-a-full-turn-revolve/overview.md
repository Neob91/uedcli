+++
priority = "p3"
kind = "unknown"
summary = "Does a FULL-TURN revolve (a genus-1 torus brush) build correctly?"
+++

# Does a FULL-TURN revolve (a genus-1 torus brush) build correctly?

`brush build revolve --angle 65536` emits a single brush with a hole through it. Nothing in
`kb/csg-bsp.md`, `quirks.md` or the spikes evidences UE1 `bspBrushCSG` behaviour on a genus-1
brush — the staircase precedent covers only a simply-connected stepped hull. Materialize one and
check the built map for holes; the fallback if it builds badly is two 180° revolves (two
brushes), which costs an actor and nothing else. Spec §4.7 / §11.
