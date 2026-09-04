+++
priority = "p1"
kind = "debug"
summary = "N=1 built parity blocked by MAP REBUILD object/actor lifecycle (export order, Polys counter names, Actors None-holes)"
+++

# N=1 built parity blocked by MAP REBUILD object/actor lifecycle

Incremental lockstep ladder, N=1 on `03_NYC_UNATCOHQ` (LevelInfo only + synthesized builder).
`native_N1.dx` vs `ref_N1.dx` (`_scratch/actor-parity/03_nyc_unatcohq/`). Headers MATCH
(55 names / 10 imports / 14 exports); world Model empty both. Diagnosis of every remaining
divergence below, with cause and fix-class (a = body, b = order/omission, c = rebuild lifecycle).

## Bodies are essentially correct (not the cause)

`canon_diff` (index-remapped) shows the LevelInfo/Camera/Model bodies are byte-identical modulo:
- the package-name artifact (`native_N1` vs `ref_N1` — a test-fixture naming difference, not real);
- masked fields (LevelInfo `AIProfile`/`TimeSeconds` — inside the exclusion mask);
- ONE genuine gap (below).

So the prompt's hypothesis (order diffs caused by wrong/missing post-rebuild body props) is
DISPROVEN as the primary cause. The order diffs are lifecycle, not body.

## (a) Builder `DefaultBrush` body missing spawn-stamps — CLEAN FIX

native body = `[Level, Brush]` (ssize 22); editor ref = `[Level, Tag=Brush, Region, Brush]`
(ssize 35). The editor spawn-stamps `Tag=Brush` (class-default Tag of a Brush actor) and
`Region=(Zone=LevelInfo0,iLeaf=-1,ZoneNumber=0)` on the dummy builder at import — same stamp
`_trunk_to_actorspecs` already applies to every content actor (`materialize.py:96-102`). The
synthesized builder in `unbuilt.py` bypasses that path (`builder` list, props `[Level, Brush]`),
so it misses both. This also explains the name-refcount gap driving name-table order:
native PointRegion=19/Region=7/Tag=7 vs ref 20/8/8.

Fix: give the synthesized builder `Tag=Brush` + `Region` (zone = LevelInfo). Engine fact to pin:
UED22 spawn-stamps `Tag=<class>` + `Region` on the Actors[1] dummy builder.

## (b) Built path skips SavePackage's refcount qsort — CLEAN FIX (imports)

`native_N1` is built by the materialize/`world_model` path, which `assemble_unbuilt` runs
SINGLE-PASS with insertion-order tables (deliberately — see the `world_model` branch comment).
The editor's `UObject::SavePackage` ALWAYS qsorts both tables count-descending. So native's
import table is Engine,LevelInfo,Polys,Model,Brush,Camera,... (insertion) while ref is
Engine,Camera,LevelInfo,Brush,Polys,Model,... (count-desc). Sorting native's imports
count-desc with the editor's creation-order permutation reproduces ref's import order exactly
(Engine 30, Camera 18, LevelInfo 3, Brush 3, Polys 2, Model 2, LevelSummary 1, Level 1, ...).
Name table likewise becomes count-desc; it needs the (a) refcount fix + the (c) name set/tie
order to match fully.

Fix: route the built path through `saveorder.compute_tables` (as the unbuilt two-pass already
does). Caveat in the existing comment: this path's table order "was never validated against a
built golden" — this is that validation.

## (c) THE WALL — MAP REBUILD + LIGHT APPLY object/actor lifecycle

The remaining divergences are all products of the editor's rebuild lifecycle, which native's
unbuilt closed form does not model. Native reproduces the NO-rebuild import-save layout; the
reference is rebuilt.

1. **Export table order.** ref = LevelInfo0, Camera6, Camera7, Model2, LevelSummary,
   DefaultBrush, Brush, Camera11, Polys7, Polys6, Camera8, Camera9, Camera10, MyLevel.
   native = LevelInfo0, Polys4, Brush, DefaultBrush, Polys3, Camera6, Camera7, Model2,
   LevelSummary, Camera11, Camera8, Camera9, Camera10, MyLevel.
   The export table is GObjObjects (creation) order of surviving RF_TagExp objects. The
   cameras are NON-contiguous in ref (6,7 … 11 … 8,9,10) — proof of destroyed/recreated objects
   reusing freed slots during rebuild. Not a simple rule.

2. **Polys counter names Polys3/Polys4 → Polys6/Polys7.** MAP REBUILD destroys the world
   Model's Polys and the builder shape's Polys and recreates them, advancing the global Polys
   auto-number past the no-rebuild values (3,4) to (6,7). Reproducing requires knowing how many
   intermediate Polys the rebuild creates/frees.

3. **Level `Actors` array None-holes.** ref = [LevelInfo0, DefaultBrush, None, None, Camera6..11]
   (10 entries); native = [LevelInfo0, DefaultBrush, Camera6..11] (8, no holes). The 2 holes are
   freed actor slots from the import/rebuild lifecycle. (This is the Level body ssize 71→73.)

All three are the same root: the editor's object/actor allocation lifecycle across
`MAP IMPORT → MAP REBUILD → LIGHT APPLY → MAP SAVE`. The unbuilt spike (2026-09-02) derived the
NO-rebuild lifecycle only after gdb traces + `SavePackage` disasm. The rebuild lifecycle is a
comparable reverse-engineering effort: either empirical multi-N derivation (bounded editor
builds, characterize the create/destroy sequence per added actor) or disasm of the rebuild
object-lifecycle path (`UEditorEngine::csgRebuild` / `bspBuild` allocation + GC).

## Owner-ruling tension (needs a yes)

The 2026-09-03 ruling fixes the synthesized builder's Polys as **`Polys4`** and the layout as an
UNBUILT import-save shape. Built parity needs the builder's Polys to be **`Polys6`** and the
export/actor order to be the rebuilt shape. So even the (a) builder-body fix cannot reach byte
parity without changing the ruled counter name — the built path diverges from the unbuilt ruling.
This is a question for the owner, not a silent deviation.

## Status

No code changed. `native_N1`/`ref_N1` cached under `_scratch/actor-parity/03_nyc_unatcohq/`.
Pre-existing test red unrelated to this: `test_doc_links` (a superpowers spec anchor).

## Owner ruling 2026-09-04 — exclude the rebuild-GC bookkeeping (opus-confirmed pending)

The editor's MAP REBUILD object-table GC bookkeeping is EXCLUDED from the native byte-parity bar
(owner chose this over cracking the rebuild lifecycle; an opus reviewer confirms render-inconsequence):
- object auto-counter NAMES (`Polys4` vs `Polys6`),
- Level `Actors` array `None`-holes,
- export-table ORDER / freed-slot reuse.
Everything else stays byte-exact: all object BODIES, geometry, lighting, name/import CONTENT+order,
and the builder's stamped body. The built path may therefore DIVERGE from the 2026-09-03 unbuilt
builder ruling (Polys4/unbuilt shape → built needs Polys6 + Tag/Region stamp + rebuilt order) — this
divergence is owner-approved. Fixes (a) builder Tag/Region stamp + (b) route built path through
`saveorder.compute_tables` are being landed; an exclusion-aware parity gate encodes the 3 exclusions.

### Opus review verdict (2026-09-04): all three CONFIRMED render-inconsequential

Corpus-grounded (not native-code inference): shipped retail maps normally carry 29–329 `Actors`
`None`-holes (`00_Intro` 329, `02_NYC_Street` 134) and export-order≠actor-order — the game loads them
fine. Every intra-package ref is a signed export index resolved by identity; only the level object
(`MyLevel`) and cross-package imports resolve by name, both unchanged. SOUNDNESS CONDITION on the
gate: the comparison must be IDENTITY/permutation-based, not raw-byte-skip — resolve every ObjRef
(Actors entries, Base/Owner/Level/Region, UModel refs) by class+outer-chain and remap across the two
export orders; still assert the surviving (non-None) Actors set AND order match (Actors order = CSG
precedence, gameplay-load-bearing), and `MyLevel` + all import names unchanged. Only then are the raw
export order / counter names / null slots safe to ignore.

### Opus review #2 (2026-09-04): also inconsequential to GAMEPLAY, RUNTIME, SAVEGAMES

Grounded in the package format + retail corpus + compiled scripts. Polys names never script-visible
(gameplay resolves by class+Tag or qualified DynamicLoadObject; no FindObject on map-local BSP).
`Actors` array is not script-indexable (no `Level.Actors[N]`); iterators skip None and follow Actors
ORDER; inter-actor refs are export indices, not array positions. Export order: the savegame
counterexample FAILS — Deus Ex `SaveGame` writes a full self-contained `.dxs` package re-serialized
from memory with its own tables (the shipped `.dx` order/holes/names are never persisted from the
file; the `.dxs` resolves against itself); NetIndex is runtime-assigned. Same soundness condition
(identity/permutation gate; surviving Actors set+order asserted). Residual assumption (corpus-backed):
no engine path depends on a specific inter-object PostLoad/creation order.
