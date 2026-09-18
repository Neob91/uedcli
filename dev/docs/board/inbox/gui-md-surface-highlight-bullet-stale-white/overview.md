+++
priority = "p3"
kind = "docs"
summary = "dev/docs/GUI.md's surface-highlight bullets describe the old additive-white overlay, replaced today by the real UED22 flat-azure stipple -- needs the owner's yes to edit"
+++

# `dev/docs/GUI.md`'s surface-highlight bullets are stale

Found while updating the (owner-approved) vertex/pivot bullets nearby (2026-09-18) -- noticed but out
of scope for that specific approval, so filed separately rather than silently fixed.
`dev/docs/` needs the owner's explicit approval to edit; this is a proposal, not an edit.

The "Whole-brush surface highlight" and "Texture (single-surface) highlight" bullets both describe
"an additive-white overlay" as the highlight technique. This is now wrong for the surface/texture
variant: `surface-selection-highlight-color-disassemble` (done 2026-09-18) replaced it with a flat,
UNBLENDED azure `RGB(0,127,255)` stipple pattern (1 drawn pixel per 16, on a fixed screen-space
lattice), disassembly-confirmed against UED22's real `SoftDrv.dll` surface draw call. Full detail:
`GUI-PARITY.md`'s "Surface selection highlight color" section.

Only the SURFACE/TEXTURE-selection variant changed -- confirm before editing whether the WHOLE-BRUSH
actor-tint variant (a different code path per `SelectionHighlight.tsx`, mentioned in the same GUI.md
bullet) was also changed or is still additive-white; word the correction precisely for whichever is
actually still true.
