+++
priority = "p3"
kind = "unknown"
summary = "UED22 still draws a selected non-colliding actor's collision shape, in a hard-coded light blue; serve/scene.py sends no collision_radius at all for one, so the GUI draws nothing"
+++

# A non-colliding selected actor gets no collision overlay at all

Found disassembling the radii block for `radii-overlay-color-hardly-visible-disassemble`
(2026-09-18), and surfaced by that change's review. Not fixed — that item was scoped to the COLOUR,
and this is a server-side data question.

`uned/UED22/Editor.dll`'s radii block tests `bCollideActors` (`[actor+0x198] & 1`) at `0x1003d4e2`
(perspective) and `0x1003d556` (ortho) only to choose the COLOUR. Both arms reach the same
`DrawCylinder`/`DrawCircle`/`DrawBox` call: set → `C_ActorArrow`/`C_BrushWire`; clear → a hard-coded
`FPlane(0.3, 0.6, 1.0, 1.0)` (light blue) at `0x100deae0`, used at `0x1003d527`, `0x1003d6cc` and
`0x1003d7b9`. So UED22 draws the cylinder either way.

`uedcli/serve/scene.py`'s `_actor_radii` instead fills `collision_radius` only when
`bCollideActors == "True"`, so a selected non-colliding actor reaches the client with no collision
radius and the GUI draws nothing for it. Whether that is wanted is a real question — a
non-colliding actor still HAS a `CollisionRadius`/`CollisionHeight`, and UED22 shows it.

Deciding it needs the owner: reproduce UED22 (always send the radius; add the light-blue colour
client-side), or keep the current filter as a deliberate departure and record it.
`uedcli/preview.py`'s `actor diagram --show collision` applies its own gate and would need the same
ruling.

## Outcome (2026-09-18)

Owner declined -- out of scope. No fix.
