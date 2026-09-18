+++
priority = "p1"
kind = "investigate"
summary = "disassemble UED22's real surface-selection highlight color/blend technique and replicate it exactly"
+++

# Surface (poly) selection highlight color -- RE and replicate

Owner's direct ask (2026-09-18): "disassemble UED22 and check the surface selection color.
Replicate it." Per the owner's standing ruling (same session), this MUST be done via disassembly of
the actual `uned/UED22/Editor.dll`/`render.dll` this project has -- NEVER a third-party UE1/Unreal
Engine 1 source repo, however similar its lineage. See `GUI-PARITY.md`'s Method section for the
exact rule and citation format (confidence tiers, no third-party sources).

## Current state (our own code, not yet RE'd)

`web/src/scene/SelectionHighlight.tsx`: a selected poly/surface gets an ADDITIVE WHITE overlay mesh
drawn on top of the real geometry -- `HIGHLIGHT_COLOR = 0xffffff`, `HIGHLIGHT_OPACITY = 0.25`, additive
blending (a flat brightness boost, not a new hue, so it "reads correctly over any base texture/CSG
color" per its own comment). This was an INVENTED convention from the start -- no RE citation
anywhere in this file for why white/0.25/additive specifically, as opposed to any other color/blend
technique.

This is a DIFFERENT question from `GUI-PARITY.md`'s already-closed "Selection highlight rendering"
topic, which covers point-actor SPRITE and MESH ACTOR selection tinting (`DrawActorSprite`/`DrawMesh`,
already ✅ binary-confirmed against `render.dll`) -- this item is specifically about SURFACE/POLY
selection (a brush face selected via a plain tap in non-wireframe mode, `SelectionHighlight.tsx`'s
own mechanism), a separate UED22 code path (likely something in `UnEdRend.cpp`'s surface-drawing
logic, or wherever `PF_Selected` polys get their distinct rendering -- not yet located).

## What to do

1. Disassemble the real `Editor.dll`/`render.dll` (`dev/docs/unrealed/extracting-from-dll.md`'s
   method) to find the real draw call/color logic for a SELECTED SURFACE specifically (as distinct
   from a selected actor's sprite/mesh tint, already covered elsewhere). Look for whatever renders a
   BSP surf/poly differently when `PF_Selected` (or however UED22 flags surface selection) is set --
   likely in the same rendering pipeline as `DrawLevelBrush`'s wireframe logic
   (`GUI-PARITY.md`'s "Brush wireframe selection color" section, itself only 📖-tier and NOW ALSO
   built on the banned third-party source -- may be worth re-confirming via disassembly while in this
   area, though that's a separate item's scope, flag if you notice something relevant).
2. Confirm the exact color, blend mode/technique (additive? multiplicative? flat overlay? alpha-
   blended tint?), and opacity/intensity UED22 actually uses for a selected surface.
3. Mark the finding's confidence tier per `GUI-PARITY.md`'s convention (✅ verified / 🔬 live-probed /
   📖 disassembly-only) and add a new Findings section + status-table row.
4. Replicate the confirmed technique in `web/src/scene/SelectionHighlight.tsx`, replacing the
   invented additive-white-0.25 convention. If the real color/technique turns out impractical to copy
   literally (e.g. relies on a rendering split this codebase's pipeline doesn't have, similar to the
   `DrawMesh` ambient-floor-rescale case this campaign already hit and departed from on purpose), say
   so explicitly and document the departure, don't silently invent a substitute.
5. Live-verify the replicated fix in the running GUI with real screenshots/pixel checks (this
   campaign's established rigor -- a subagent's "should work now" claim without real evidence is not
   acceptable, per repeated lessons this session).

## Where to look

`web/src/scene/SelectionHighlight.tsx` (the code to change), `dev/docs/unrealed/extracting-from-dll.md`
(disassembly method), `GUI-PARITY.md` (existing findings on adjacent selection-rendering topics,
status table, confidence-tier convention).
