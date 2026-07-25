# Spike 8 — native `.dx` → actor-list read (replaces `UCC batchexport Level T3D`)

**Status: RESOLVED — a `.dx` parses to a full actor list natively (class + properties),
0 errors on a real map.** Harness: [`harness/native_dx_actors.py`](harness/native_dx_actors.py).

## Question

`store_export.export_dx_t3d` reads a `.dx` into the model via `docker exec … wine
UCC.exe batchexport … Level T3D` (then parses the T3D). Can we read the `.dx` natively?

## Answer: yes

Combining the proven pieces — package export table (Spike 3), actor body = `StateFrame`
(`RF_HasStack`) + tagged property list (Spike 7), import-table class resolution
(Spike 4), typed property decode (Spike 1) — `native_dx_actors.py` parses every actor:

```
00_Intro.dx v68: 1837 actors (RF_HasStack), 0 parse errors
top classes: Brush 920, Light 458, PathNode 196, CameraPoint 49, DeusExMover 21, …
actors with Location: 1832; out-of-range: 0
  Light  Light299  Loc=(5108.8, -5664.8, 140.8)  …
```
Classes resolve via the import table; `Location` structs decode to finite in-range
coordinates; `Name`-typed props (`Tag`/`Group`) decode to name-table indices (resolve to
strings via the name table for display). The parse is byte-consistent (every body lands
within its serial extent; 0 errors), matching the export table's actor-class exports.

## Status of validation
- **Self-consistent: strong** — 0 parse errors over 1837 actors, sane Locations, classes
  resolve, count matches the export table.
- **Editor/UCC cross-check: deferred** — `UCC batchexport … Level T3D` in the standing
  container hit a commandlet/path-arg quirk (and the DeusEx-dependency confound), so a
  clean count/property diff vs UCC's own T3D is left for the Phase-A implementation's
  test harness (against a map whose deps load, or the native pipeline's asset setup).

## Net
This is the concrete **Phase A read path**: a `.dx` → `Level` model with actors,
classes, and properties, **no editor / no UCC / no wine**. With the texture decode
(Spike 1) and qualification (Spike 4), the whole "read a `.dx` into the model" surface
is natively covered — removing `store_export`'s and `qualify`'s editor/UCC legs. The full
typed-property decode (every property type → typed value, vs the key ones here) reuses
the `2026-06-26-uproperty-typed-decode` work for the production module.
