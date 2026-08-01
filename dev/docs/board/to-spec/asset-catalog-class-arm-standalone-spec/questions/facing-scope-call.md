# Scope C1's settled claim to seating, marking world-facing UNVERIFIED pending the RotOrigin probe?

## Context

Spec §3, §8.6. The mesh-local thin extent axis equals the world mount normal **only when `RotOrigin`
is identity**. UE1 bakes `Scale`, `Origin`, and `RotOrigin` into the mesh-to-world transform; the
rasterizer applies only `Scale`. `RotOrigin` prevalence across DX deco meshes is unmeasured.

- **Proposed:** scope C1's SETTLED claim to the **vertical/seating** half (height, footprint, `z=0`
  seating — this closes finding 7's sinking defect with no rendering), and mark **world-facing
  UNVERIFIED** pending a `RotOrigin`/`Origin` prevalence probe. The probe is a build-time TODO landing
  in `dev/docs/unrealed/`, not an owner question; if real DX packages are content-blocked it stays a
  board TODO and world-facing stays unverified.
- **Alternative the gate may pick:** block C1's facing claim entirely until the probe is unblocked.
- **At stake:** overclaiming world-facing before the probe would let an agent trust the thin axis as a
  mount normal when a non-identity `RotOrigin` silently breaks that mapping.
- **Grounded:** the decoder already returns `rot_origin` (spike `2026-07-25-native-mesh-decode`,
  `umesh.py`), so the probe is cheap once the decoder is promoted into `uedcli/`.

**Recommendation:** adopt the scoped claim — build C1's seating/footprint now, do not assert
world-facing until the probe runs. `direction/asset-catalog.md` ("never a wrong pixel / named error
over a guess") favours the conservative scope.

## Answer

<!-- Empty = open. -->
