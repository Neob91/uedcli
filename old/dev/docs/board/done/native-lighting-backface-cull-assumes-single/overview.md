+++
priority = "p3"
kind = "implement"
summary = "DONE 2026-08-27. The editor's own test (render.dll 0x100198c7) keeps a surface whenever PlaneDot >= -1.0 and NEVER back-face culls a PF_TwoSided or PF_Portal one. Both are now in light.rs::light_in_front; the answer came from disassembly, not from an oracle map with a lit two-sided surface."
+++

# native lighting backface cull assumes SINGLE-SIDED surfaces — resolved

The item asked for an oracle map with a lit two-sided surface before adding a `PF_TwoSided` bypass,
and said not to guess. The disassembly answered it instead: `URender::OccludeBsp`'s back-face branch
(`render.dll 0x100198c7`–`0x100198dd`, which the lighting gather reaches through
`URender::GetVisibleSurfs`) is

    if( !IsFront && PlaneDot < -1.0f && !(PolyFlags & 0x04000100) ) drop the surface

with `IsFront = PlaneDot > 0`. Two facts fall out: the exemption mask is `PF_TwoSided (0x100) |
PF_Portal (0x04000000)`, and the tolerance for everything else is a full world unit behind the
plane, not a strict sign test. `light.rs::light_in_front` now implements both, pinned by
`light_in_front_matches_plane_side`.

Measured on UNATCO against the editor's own `LIGHT APPLY`: (surface, light) pairs native was MISSING
dropped from 146 to 7.
