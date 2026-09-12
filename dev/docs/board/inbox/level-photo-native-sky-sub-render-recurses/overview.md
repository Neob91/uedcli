+++
priority = "p3"
kind = "implement"
summary = "level photo --native sky sub-render recurses redundantly at every depth"
+++

# level photo --native sky sub-render recurses redundantly at every depth

Found in Task 3's review of `add-pf-fakebackdrop-support-to-level-photo`
(`uedcli-native/src/render.rs`'s `Blend::Backdrop` sub-render, commit `b3d6711a`). The sky
sub-render's `backdrop_indices` filter runs over the FULL, unfiltered `polys` list at every
recursion level (unlike the mirror-cluster loop, which excludes the triggering mirror's own faces
from its own reflection via `cluster.indices.contains(&j)`), so on any level with at least one
`PF_FakeBackdrop` face the sky block fires again at recursion depth 1 and depth 2, each time
computing the SAME sky-camera image (the sky camera's location/basis/fov never change with
recursion depth) a second and third time for no visual benefit. Net cost: two wholly redundant
full-scene renders per frame on every sky-bearing level, and the sky branch multiplies against
mirror clusters (`(clusters+1)^3` sub-renders where the pre-existing mirror-only cap-3 work left
`clusters^3`).

This is CORRECT per the ratified spec (`add-pf-fakebackdrop-support-to-level-photo/spec.md:181-186`
explicitly sanctions whole-scene, no-exclusion sky rendering as a known-cost simplification,
matching the pre-existing "a sky room that isn't sealed can leak" caveat) — not a bug, and NOT
fixed as part of that item per `CLAUDE.md`'s decision-adherence rule (a ratified decision isn't
altered without an explicit yes). The obvious fix — exclude backdrop faces from the sky's own
sub-scene, mirroring the mirror cluster's self-exclusion — would terminate the redundant recursion
after one level, but changes spec'd behavior and needs the owner's yes first.

Not measured end-to-end yet (`level photo`'s Python wiring, Tasks 4-5 of the same plan, isn't built
yet as of this finding) — worth a real wall-clock measurement on a sky-heavy level once wired,
before deciding whether this is worth a dedicated fix pass.
