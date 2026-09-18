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

## Outcome (2026-09-18, owner-approved)

Confirmed by reading `web/src/scene/SelectionHighlight.tsx` and its call sites in `Viewport3D.tsx`/
`OrthoViewport.tsx` directly (not assumed):

- **"Texture (single-surface) highlight"** (`SurfaceSelectionHighlight`) still exists and now draws
  the disassembly-confirmed flat azure `RGB(0,127,255)` stipple, not additive-white. Bullet reworded
  to describe it.
- **"Whole-brush surface highlight"** no longer exists at all, for either color -- a whole selected
  brush gets NO per-face highlight now; it's shown only by `BrushOutlines`' bold ring (owner ruling,
  already implemented, code comment: "A selected WHOLE BRUSH is shown as a selected ACTOR ... NOT by
  lighting up its faces"). The bullet described a mechanism that was removed, not merely recolored --
  replaced with a short note to that effect, and the stale cross-reference to it earlier in the
  Selection section (line ~250) is removed too.
- Found in the same read: `ActorSelectionHighlight` (a THIRD, previously undocumented variant) lights
  up a selected non-brush mesh actor with the multiplicative tint from `GUI-PARITY.md`'s "Selection
  highlight rendering" -- added as a new bullet since it was missing from GUI.md entirely.

`dev/docs/GUI.md` updated accordingly.
