# May a Mover be a `crosses` SOURCE in `actor survey`?

## Context

The last unresolved kind in the spec's CSG-kind table. The factual half is settled by
`dev/docs/spikes/2026-09-23-actor-survey-csg-kind-and-cost/`:

- A Mover is excluded from world CSG entirely (`brush_marshal._in_world_csg`; the editor's own
  iteration filter is `AActor::IsStaticBrush`). So it contributes no solid to the world, can never
  be carved, and can never be the TARGET of a world `crosses`. That half needs no ruling.
- But a Mover carries a real private `UModel` of genuine solid matter (`unbuilt.build_mover_shape_model`,
  byte-verified against the UNATCO golden), and that matter can extend into world solid.

The catch is the same one measured for collision extents: a door sitting in its frame at the base
pose overlaps world solid *by design*. `DeusExMover` is 398 of the 456 mover brushes in the shipped
corpus, and most of them are doors in frames.

Options:

- (a) **No** — a Mover is never a `crosses` source. Simplest, and consistent with it being outside
  world CSG in every other respect. Cost: a mover genuinely embedded in a wall by mistake goes
  unreported at the `csg` tier (raw `touches` still fires).
- (b) **Yes, with the depth annotation** — same treatment the spec now gives a collision extent:
  report `crosses(<depth>uu)` and let the reader judge. Cost: it fires on most doors, at their base
  pose only, which is the pose the trunk stores.
- (c) **Yes, but only past the mover's own keyframe travel** — report only where the mover's swept
  volume across its keyframes intrudes. Much more work, and needs a keyframe sweep the codebase does
  not have.

Recommendation: (a) for v1. The mover-in-frame overlap is the normal case rather than the exception,
(b) adds a line to nearly every door's survey, and (c) is a feature of its own. If a real
misplaced-mover case turns up in use, it gets its own revision against that example.

## Answer

<!-- Empty = open. -->
