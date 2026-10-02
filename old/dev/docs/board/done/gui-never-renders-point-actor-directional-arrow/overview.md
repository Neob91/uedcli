+++
priority = "p1"
kind = "implement"
summary = "GUI never renders point-actor directional arrow gizmo (C_ActorArrow)"
+++

# GUI never renders point-actor directional arrow gizmo (C_ActorArrow)

Owner-flagged (2026-09-16, p1). `C_ActorArrow` (RGB `(163,0,0)`, `GUI-PARITY.md` "Radii overlay
colors") is UED22's color for a per-actor directional-facing ARROW gizmo in the 3D viewport, reused
separately for the collision/light radii circles (already implemented). This GUI has no equivalent:
`web/src/scene/SelectionMarkers.tsx` draws vertex dots + a pivot marker for a selected BRUSH only;
point actors get their class-icon sprite (`PointActorMarker.tsx`) and nothing else.

## Geometry and gating — ✅ source-confirmed (`UnEdCam.cpp`, `fgsfdsfgs/UE1`, "// Direction arrow.")

```cpp
if (Viewport->IsOrtho() && Actor->bDirectional && (Actor->IsA(ACamera::StaticClass) || Actor->bSelected))
{
    FVector V = Actor->Location;
    FCoords C = GMath.UnitCoords / Actor->Rotation;   // the actor's own rotated local basis
    Draw3DLine(C_ActorArrow, V + C.XAxis*48, V);                              // shaft
    Draw3DLine(C_ActorArrow, V + C.XAxis*48, V + C.XAxis*16 + C.YAxis*16);    // fin
    Draw3DLine(C_ActorArrow, V + C.XAxis*48, V + C.XAxis*16 - C.YAxis*16);    // fin
    Draw3DLine(C_ActorArrow, V + C.XAxis*48, V + C.XAxis*16 + C.ZAxis*16);    // fin
    Draw3DLine(C_ActorArrow, V + C.XAxis*48, V + C.XAxis*16 - C.ZAxis*16);    // fin
}
```

A 5-segment dart: a 48uu shaft along the actor's local +X (facing) axis, four 16uu fins splayed
±16uu in local Y and Z from a point 16uu back from the tip. Color `C_ActorArrow` = `(163,0,0)`
(already in this codebase, `RadiiOverlays.tsx`'s `RADII_COLOR`).

**Gating, not always-on:**
- Only actors with `bDirectional = true` (not every actor class sets this — need to check which DX
  classes do; `Camera`/lights/triggers/patrol points are likely candidates, not, say, a static prop).
- `ACamera` actors always show it; every other `bDirectional` actor only when **selected**.
- Gated `Viewport->IsOrtho()` — v200 draws this ONLY in the ortho panes, same gate the radii overlay
  had in v200 before a later UT patch added a perspective-pane version (`GUI-PARITY.md` "Radii
  perspective cylinder"). Whether the same later-patch pattern applies here (an owner-confirmed
  perspective arrow in the actual DeusEx-era build) is UNCONFIRMED — worth checking with the owner
  the same way the radii cylinder's perspective question was settled, not assumed either way.

## Open before implementing

- Which DX/Engine actor classes actually set `bDirectional = true`? Not checked.
- Does this project's DeusEx-customized `Editor.dll` show it in perspective too (like radii ended up
  needing)? Not confirmed — ask the owner rather than guess, same as the radii precedent.

## Outcome (2026-09-19) — closed, implemented

Redone entirely from our own `uned/UED22/Editor.dll`/`Engine.dll` (the geometry/gating above was
explicitly third-party-sourced and banned as evidence, 2026-09-18 ruling). Full disassembly + class-
default findings in `GUI-PARITY.md`'s "Directional arrow gizmo" section — summary:

- **Not a radii-view feature.** The block sits right after the radii draws in the same per-actor
  `UEditorEngine::Draw` loop, but is reached even when "Show Radii" is off and the actor isn't
  selected — its own three-term gate is the only thing that matters.
- **Gate**: `bDirectional && (IsA(ACamera) ? actor != Viewport->Actor : bSelected)` — confirmed
  exactly, including that the Camera exclusion is "not the viewport's own possessed actor" (never
  fires in this GUI, whose viewports never possess a level actor — so a Camera's arrow always shows
  here).
- **No ortho gate at all** — renders in every pane, contradicting the board item's `IsOrtho()`
  guess.
- **Real geometry**: shaft `38.0` (not `48`), fin-back `16.0`, fin-spread `12.0` — read directly out
  of the constant pool, not assumed.
- **`bDirectional=True` classes**, decoded from real compiled class defaults (a from-scratch minimal
  `.u` reader, `harness/upkg_min.py` — this sandbox's docker cannot build `uedcli_native`):
  `Engine.Pawn` (inherited by Camera + every Pawn/NPC), `InterpolationPoint`, `Projectile`,
  `Teleporter`, `PlayerStart`, `PatrolPoint`, `Spotlight`, `AmbushPoint` (Engine.u); `DeusExMover`,
  `ParticleGenerator`, `PawnGenerator`, `WanderPoint`, `SecurityCamera`, `HidePoint`,
  `ElectricityEmitter`, `DirectionalTrigger`, `LaserTrigger`, `ProjectileGenerator`, `SpawnPoint`,
  `TrashGenerator`, `BeamTrigger` (DeusEx.u). No `IsBrush` gate exists — a selected `DeusExMover`
  really does get an arrow.

Implemented: `uedcli/serve/scene.py`'s `DirectionalArrow`/`_actor_directional_arrow`/
`_directional_arrow_lines` (server-resolved, every actor including brushes) +
`web/src/scene/DirectionalArrows.tsx` (client draw, gated only on `require_selection` vs. the
current selection). Verified at the computed-geometry/unit-test tier (`DirectionalArrows.test.tsx`,
5 new `test_serve_scene.py` cases including one against real `uned/UED22/Engine.u` class defaults)
— no live pixel A/B (this sandbox has neither a runnable headless browser nor a docker daemon that
can mount the repo for a live UED22 capture).
