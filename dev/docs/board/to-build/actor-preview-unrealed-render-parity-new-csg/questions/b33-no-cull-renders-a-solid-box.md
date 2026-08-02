# Spec B3.3 "front never used to remove a face" renders a subtracted room as a solid box

## Context

Slice 1 is a go/no-go: "if the ortho pipeline cannot draw world-space fragments faithfully, stop and
re-plan." It cannot, as B3.3 is written.

Reproduced with the real `build_geometry_bspcsg` solve over a 1024 subtract room holding a 256 add,
plus a 128 add buried in solid 4000 UU away. Fragments were rendered through `preview.py`'s own ortho
primitives (`_framing`, `_face_depth_affine`, `_fill_face`, `_is_front`), the pipeline slice 2 feeds.

**The solve is correct.** The buried add yields 0 fragments (culled by containment); the in-room add
yields 6; the room yields 6. bspcsg also orients every surviving surface's normal INTO the empty
space — a consistent outward-from-solid winding.

**B3.3 as written yields a solid box.** With `cull_front=False` and `front` never removing a face
(spec Design §3, plan slice 2), every fragment is drawn against the shared z-buffer. The room's
camera-facing walls are its NEAR shell; each has a normal pointing away from the camera (into the
room), so they are back-faces — but B3.3 draws them, they win the depth test, and they occlude the
interior. Measured iso view: room shell 41616 px visible, in-room add 0 px. The render is an opaque
box; the interior the parity feature exists to show never appears.

**The only faithful render removes faces by facing.** Dropping each fragment whose post-CSG normal
faces away from the camera (a standard backface cull, clean because bspcsg orients all normals into
empty) reveals the room interior AND the add with correct occlusion: room 39015 px, add 2601 px. No
depth-only or flag-only mechanism can do this — behind the nearest opaque surface nothing shows, so
the near shell must be removed, and the only thing distinguishing it is its facing.

So B3.3's premise — "the solve has ALREADY resolved visibility globally" — is false. The solve
resolves CONTAINMENT (which surfaces exist), not per-view facing. Faithful parity needs a per-view
backface cull, which B3.3 explicitly forbids. This is a direct spec contradiction, not an
implementation choice, so it is the owner's to resolve — the decision rule bars "fixing" it silently.

Evidence renders (throwaway harness, not committed): B3.3 no-cull = solid gold box with the blue add
hidden; backface cull = gold room interior with the blue add inside it. This confirms the prior
NO-GO attempt.

## Proposed resolution (owner to rule)

Allow a per-view backface cull of the solved fragments by their post-CSG normal on the `textured`
path — replacing B3.3's "cull_front=False, front never removes a face." Because bspcsg orients every
surface's normal into empty space, this is one uniform test (drop fragments whose normal faces away
from the camera), not the current per-brush subtract-only `cull_front` heuristic. If rejected, the
CSG-solved `textured` mode cannot render a room interior through the ortho pipeline and the feature
needs re-scoping.

## Answer
