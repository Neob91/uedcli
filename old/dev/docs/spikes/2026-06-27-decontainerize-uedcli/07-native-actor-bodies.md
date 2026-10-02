# Spike 7 — native actor object bodies (read + write), characterized & validated

**Status: RESOLVED — the actor-body format is characterized; the reader parses 3736/3736
real objects with ZERO errors; a property writer round-trips all common types.** This
closes the review-flagged "actor bodies are an unproven inverse" gap. Harness:
[`harness/prop_writer.py`](harness/prop_writer.py).

## The gap (from the cold review)

Spike 3 claimed actor bodies are "the easy inverse of the texture reader." A reviewer
correctly noted the reader was only validated to EOF on textures/palettes, and that real
actor property lists mostly did NOT parse cleanly — so the claim was unproven.

## Finding 1 — actor bodies start with an optional `StateFrame`

A UE1 object's serial body is `[StateFrame?] + tagged-property-list + [class-specific
trailing]`. The `StateFrame` is present iff the export's ObjectFlags has
**`RF_HasStack = 0x02000000`** — true for **Actors** (they carry a script execution
stack), false for **Textures/Palettes** (no script state), which is exactly why textures
parsed directly and actors did not. Layout:
```
if flags & RF_HasStack:
    Node       : ci (object ref)
    StateNode  : ci (object ref)
    ProbeMask  : u64 (8 bytes)
    LatentAction: u32 (4 bytes)
    if Node != 0: Offset : ci   (bytecode offset)
then: tagged property list (terminated by None)
then: class-specific trailing data (brush Model geometry, etc. — for non-point classes)
```
With the StateFrame skip, real `Light` bodies parse cleanly to EOF — 11 props each
(`Location`, `Tag`, `Region`, `LightBrightness`, …).

## Finding 2 — reader validated across a whole real map (0 errors)

Parsing **every** export with a serial body in retail `00_Intro.dx` (v68) — StateFrame
skip (when `RF_HasStack`) then the property list:

```
3736 objects: 0 errors.  1838 (49%) consume cleanly to EOF; 1898 have class-specific
trailing data after the property list (expected).
```
Clean-EOF classes are the point actors and brush *actors*: `Brush` 920 (a brush actor's
body is just properties — the geometry is a SEPARATE `Engine.Model` export it references),
`Light` 458, `PathNode` 196, `CameraPoint`, `DeusExMover`, `AmbientSound`, decorations… So
the property reader is robust on real authored content, not just textures.

## Finding 3 — the property WRITER round-trips

`prop_writer.py` emits a valid `FPropertyTag` list (the inverse of the reader) and a
write→read round-trip passes for every common type — `Byte`, `Bool`, `Int`, `Float`,
`Name` (name-table index), `Object` (ref), `Struct` (e.g. `Vector` raw bytes) — with the
body terminating exactly at EOF. The writer controls the encoding (the loader accepts any
valid tag encoding; byte-match with the editor is not required).

## Net effect on the roadmap

Writing a **point actor** natively now decomposes into proven/characterized pieces:
1. emit the `StateFrame` (or clear `RF_HasStack` for a stackless actor — TBD which the
   game requires; point actors in retail maps DO carry a stack),
2. emit the property list (`prop_writer`, proven),
3. no class-specific trailing for a point actor.
Brush actors additionally need a separate `Engine.Model` export for their shape (a brush
Model, distinct from the built level Model) — its body is the brush `PolyList`, writable
with the same primitives.

## Deferred
- Confirm whether the game accepts a point actor with `RF_HasStack` cleared (simpler
  write) or requires a populated `StateFrame`; if required, define the canonical empty
  StateFrame to emit (`Node=StateNode=0, ProbeMask=0, LatentAction=0`).
- Name-table management in the writer (every `Name`/class/struct/object name referenced
  must be present in the package name table) — mechanical, part of the package writer.
- The brush-actor `Engine.Model` (shape PolyList) body writer + a round-trip.
