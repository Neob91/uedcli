# How do movers / semisolids / non-solids / point actors render under the world solve?

## Context

A CSG-solved world render only contains what the BSP world contains. A **mover** carries no CsgOper
and is not part of the world BSP (UnrealEd draws it as a separate actor) — draw it as a textured
overlay on top of the solved world, or omit it? **Semisolid** adds faces without splitting the world;
**non-solid** (sheets) likewise. **Point actors** (lights, playerstarts) have no geometry — keep the
existing marker/sprite overlay, or drop them in world mode for viewport fidelity? Needs a per-kind
ruling so the render is honest rather than silently dropping a kind.

## Answer

<!-- Empty = open. -->
