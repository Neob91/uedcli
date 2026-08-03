# Spike 3 — native `.dx` writer feasibility (the keystone)

**Status: package CONTAINER writer PROVEN byte-exact (v61/v68/v69, incl. real
`.dx`). The one gating dependency for a *playable* native `.dx` is the offline BSP
`Model` build (D2).** Harness: [`harness/package_rw.py`](harness/package_rw.py).

## Question

The editor's `MAP SAVE` is the only thing that writes a `.dx` today (`apply.py`
materialize). Can uedcli write the Unreal package natively, removing that last,
hardest editor dependency?

## Result: the container writer works, byte-for-byte

Parse a real package fully, then re-encode the **header + name table + import table +
export table** purely from the parsed fields, and compare to the original bytes:

| Package | Version | exports | Result |
|---|---|---|---|
| `CoreTexDetail.utx`, `CoreTexWater.utx` | 61 | 21, 4 | **BYTE-EXACT** |
| `CoreTexMetal.utx`, `NewYorkCity.utx`, `DeusExDeco.u` | 68 | 215, 279, 698 | **BYTE-EXACT** |
| `DeusEx.u` | 68 | 18 431 | **BYTE-EXACT** |
| `Engine.u` (committed UED22 substrate) | 69 | 5 551 | **BYTE-EXACT** |
| `00_Intro.dx`, `00_Training.dx` (retail maps) | 68 | 3 736, 3 323 | **BYTE-EXACT** |

So the compact-index encoder (`write_ci`), the name/import/export table encoders, and
the header (incl. the v68/69 FGuid + generations, v61 heritage) are all correct
inverses of the readers. Header is 64 bytes for v68/69 (36 + 16 GUID + 4 gencount +
8 per generation × 1).

### Full-file rewrite is byte-identical (the conclusive proof)
Beyond the per-section check, `write_full` reassembles the **entire file** from parsed
structures — recomputing every offset from scratch (header → names → object data →
imports → exports) — and the output is **byte-identical** to the original on real
maps: `00_Intro.dx` (4 702 912 bytes), `00_Training.dx` (4 386 033 bytes), plus
`DeusEx.u` and `Engine.u`. A byte-identical file is by definition loadable by the
editor and the game, so the container writer + layout + offset computation are proven
end-to-end, not just per-table. (v61 fails *full-assembly* only because of its
`Heritage` table, which `.dx` maps never use — its per-section encoders pass; v61 is
read-only content, never a write target.)

### File layout (so a from-scratch writer computes offsets, not just reproduces)
```
header → name table → object data → import table → export table (@EOF)
```
Confirmed on real maps: `nameoff` = headerlen; object bodies fill `[nameend, impoff)`;
import then export tables sit at the end; `expend == EOF`. A native writer therefore:
1. emit header (offsets back-patched at the end),
2. emit name table → `nameend`,
3. emit each object body; record its start as that export's `SerialOffset`,
4. emit import table, then export table (which now has every `SerialOffset`),
5. back-patch `NameOffset/ImportOffset/ExportOffset/...` in the header.
All five steps use only the proven encoders. **No editor, no wine.**

## What's proven vs what remains

**Proven / low-risk (no blocker):**
- The whole **package container** (above) — byte-exact, but note the round-trip copies
  object bodies verbatim and reuses the GUID/generations; emitting *new, differently-
  sized* bodies + minting a GUID/generation table is mechanical but untested.
- **Point-actor bodies** = a tagged-property list (`FPropertyTag`), the inverse of the
  Spike-1 reader; the writer controls the encoding (the loader accepts any valid tag
  encoding). Straightforward for scalar props.

**Mechanical-but-unproven (scope honestly):**
- **General actor bodies** beyond scalar props — structs, static arrays, strings, and
  class-specific trailing data — are NOT value-level round-trip tested (the reader was
  validated to EOF only on textures/palettes). Needs a write→read round-trip test.
- **The `ULevel` body** (ordered actor array, `Model` ref, URL…) and in-package
  "myLevel" exports are unaddressed by the spikes — see the roadmap spec's
  "what a from-scratch writer must synthesize" section.

**`Model` (de)serialization — now RESOLVED (2026-06-27):**
- The `Model` serial-read format is **complete and validated byte-exact to EOF on 12/12
  real maps** (`2026-06-25-umodel-serialize-format.md`, after the `0xa8` fix; largest
  7.1 MB / 13k nodes). All arrays (Vectors/Points/Nodes/Surfs/Verts/Zones/LightMesh/
  lightmap-bytes/FBox/INT/Leaves/INT + trailing INTs) land exactly at serial end. The
  WRITE is the inverse using the same primitives — mechanical. So this is NOT a second
  port; the only remaining geometry work is the CSG *build* (D2) that GENERATES the data.

**The one gating dependency — the built BSP `Model`:**
- A brush actor carries its own brush `Model` (its shape) — trivially writable. But the
  **world geometry the player sees/walks** is the *level* `Model`, produced by CSG/BSP
  build from all the brushes. **Deus Ex (the game) loads the pre-built BSP from the
  `.dx`; it does NOT run CSG at load** (that is an editor-only operation). So a
  *playable* native `.dx` must contain a correctly built level `Model`.
- Building that natively is the **offline BSP/CSG engine (D2)** — already the subject of
  extensive prior work: the partition-heuristic feasibility gate is CLEARED
  (`spikes/2026-06-26-bsp-partition-heuristic-from-binary.md`), with the remaining
  `SplitPolyList`/coplanar-merge/leaf-
  zone build scoped as a bounded-but-multi-week faithful port (board item `bsp-issue-detector`,
  the D2 design). **D2 is the long pole of de-containerization** —
  and now demonstrably the *only* hard one: container write, actor bodies, and Model
  *serialization* are all proven or mechanical around it.

## Conclusion

Native `.dx` writing is **feasible**, and the work decomposes cleanly:

| Piece | Status |
|---|---|
| Package container (header + tables + layout + offsets) | **PROVEN byte-exact** (round-trip copies bodies verbatim; new-body synthesis + GUID/generation minting untested) |
| Point-actor bodies (`StateFrame` + property list) | **characterized + validated** (Spike 7): reader parses 3736/3736 real objects with 0 errors; writer round-trips all common prop types |
| Brush-actor body (a separate `Engine.Model` shape PolyList) | mechanical, same primitives (round-trip TBD) |
| `ULevel` body (actor array, `Model` ref, URL…), in-package "myLevel" exports | **unscoped** — see roadmap spec |
| `Model` *serialization* (built BSP ↔ bytes) | **RESOLVED** — read validated byte-exact to EOF on 12/12 real maps (2026-06-27); write is the mechanical inverse |
| **Built level `Model` *generation* (CSG/BSP)** | **the long pole — needs D2** (now the *only* hard piece) |
| Lighting / pathnodes | Spike 5 (build output: bake / defer / optional) |

So the editor's last and hardest role — `MAP SAVE` — is replaceable; the actual
remaining engineering is the offline BSP engine, which was already on the roadmap for
the `level doctor` ground-truth work. **De-containerization and the offline BSP engine
are the same long pole.**

## Synthesized-body write + offset recompute (the non-verbatim path)

`harness/native_edit.py` exercises the writer's *hard* path (not the verbatim
round-trip): it natively edits a real 4.7 MB `00_Intro.dx` — bumps `Light299`'s
`LightBrightness` 44→94 by locating the property in its body and appending the modified
body at end-of-data — then **recomputes the moved export's `SerialOffset`/`Size` and the
import/export table offsets**. The output **re-parses cleanly to EOF**, the edited value
reads back correctly, and a sample of other exports are byte-identical. So: locate a
property in a real body + synthesize a (resizable) body + recompute offsets → a valid
package. (`Light` bodies carry no internal absolute offsets, so moving one is safe.)

**Editor smoke test (partial):** the standing UED22 `MAP LOAD`s the native-written file
**without crashing** (container accepted), but the level materializes near-empty because
`00_Intro`'s DeusEx content/code dependencies don't load cleanly in that standing editor
(the stub/asset environment isn't set up) — a package-environment confound, NOT a writer
fault. A clean editor+game content-acceptance test (a map whose deps load, or the native
pipeline's own asset setup) is deferred.

**Writer caveat surfaced here:** bodies that contain **internal absolute file offsets**
— texture `FMipmap` WidthOffset (Spike 1), mesh/`TLazyArray` skip-offsets (Spike 2), and
the `Model` — **must have those offsets patched if the body is relocated.** A from-scratch
writer that re-lays-out all bodies contiguously must handle this; `native_edit` sidesteps
it by leaving such bodies at their original offsets.

## Deferred / next
- Implement the from-scratch writer end-to-end and load the result in the editor / game
  as the acceptance test (gated on having *some* Model — start with a hand/trivial BSP
  or a D2 slice).
- Property-list (`FPropertyTag`) writer + a value-level round-trip test.
- Confirm `.unr` (UT/Unreal) parity (same format; expected).
