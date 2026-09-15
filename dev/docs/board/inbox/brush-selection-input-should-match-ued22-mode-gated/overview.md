+++
priority = "p2"
kind = "implement"
summary = "GUI: brush selection input should be Shift+LMB in non-wireframe mode, plain LMB in wireframe mode, matching real UED22; selected brushes show pivot+vertices with a thicker outline like actor diagram"
+++

# GUI: brush selection input should be Shift+LMB in non-wireframe mode, plain LMB in wireframe mode, matching real UED22; selected brushes show pivot+vertices with a thicker outline like actor diagram

Owner-raised (2026-09-15). Two parts:

1. **Selection input binding must match real UnrealEd, mode-gated**: `Shift+LMB` selects a brush in
   non-wireframe (solid/textured) mode, plain `LMB` selects in wireframe mode — check
   `dev/docs/unrealed/quirks.md`/`commands.md` for the real editor's documented click-select
   behavior per render mode before implementing; don't guess. Owner's own words: "The selection
   works good otherwise" — this is specifically about which mouse gesture triggers a brush pick in
   which shading mode, not the underlying hit-test logic.
2. **Selected brushes must show their pivot and vertices**, the same way `actor diagram` already
   does for a highlighted brush, plus a visibly thicker outline than an unselected brush's wireframe
   (actor diagram "has it sorted out good" — read `uedcli/preview.py`'s highlight-rendering code for
   the exact convention: pivot marker, vertex dots, line weight).

**Sequencing note**: this heavily overlaps files `gui-slice-2-quad-layout-ortho-views-matching`
is actively building right now (`Viewport3D.tsx`, `web/src/scene/BrushOutlines.tsx`, `selection.ts`,
`dragGesture.ts` — that item already built CSG-colored brush wireframes and a bold-vs-thin selected-
brush outline via `Line2`/`LineMaterial`, per its own Task 10). Build this AFTER that item merges,
as an incremental addition on top of what it lands, not in parallel — two agents editing the same
files concurrently risks conflicting/duplicated work.
