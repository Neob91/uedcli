+++
priority = "p1"
kind = "owner-question"
summary = "Native `level materialize` — full offline `.dx` build WITHOUT UnrealEd is fully reverse-engineered + specced"
+++

# Native `level materialize` — full offline `.dx` build WITHOUT UnrealEd is fully reverse-engineered + specced

p1. Done autonomously overnight (2026-07-15).
The three hard unknowns are now closed: **CSG/BSP** (both D2 gaps — leaf-filter + node emission —
byte-decoded, 33/33 checks), **lighting** (the decisive find: `LIGHT APPLY` stores **1-bit
visibility masks, not intensities/colours** — collapses the "2nd long pole" to a per-lumel BSP
ray test; format double-proven), and the **ULevel body / actor bodies / GUID mint / reachspecs /
package assembly** (ULevel round-trips **100/100** byte-exact; GUID/gen **100/100**). Spec:
`spec.md`; evidence: `spikes/2026-07-15-native-materialize/`
(3 sections + reproducible harness). **Two cold reviewers ran; findings folded** (Tier-K LineCheck
battery reinstated, lighting shadow-correctness gate added, import resolver + `Actors[0]/[1]`
synthesis owned, zones scoped honestly, Scale/UPolys assigned). **NEEDS ANDRZEJ SIGN-OFF** before
the port: it PROPOSES decisions that revise the "lighting/paths = defer to optional editor
final-bake" disposition (`spikes/2026-06-27-decontainerize-uedcli/05-lighting-and-paths.md`) — see
spec §9. Until sign-off these are proposals, NOT in `decisions.md`. The port itself is a scoped
multi-slice build (N-1..N-5, spec §7), not overnight work.
