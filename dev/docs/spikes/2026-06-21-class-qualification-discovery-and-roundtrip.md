# Class-qualification discovery + materialize round-trip spike (2026-06-21)

**Question.** The 2026-06-19 class-package-collision spike proved `Class=Package.ClassName`
is honored by the *importer* under a true collision, but never checked (a) whether a *read*
mechanism can attribute each actor's resolved class back to a specific package the way
`qualify_level_textures` attributes each poly's texture, or (b) whether a qualified binding
survives the FULL `level apply` cycle (`MAP SAVE` → editor torn down and recreated → fresh
`MAP LOAD`), not just a one-shot import. Both block writing `qualify_level_classes`.

## Verdict

| Question | Verdict |
|---|---|
| Does a qualified `Class=` binding survive `MAP SAVE` → fresh editor → `MAP LOAD`? | **YES** — confirmed live, exact package preserved |
| Does `OBJ DEPENDENCIES PACKAGE=MyLevel`'s per-actor block order match `level.order` (the way it does for per-poly `Texture=` within an `Engine.Polys` block)? | **NO** — disproven by direct counter-example; order is unpredictable, not usable for positional correlation |
| Can `qualify_level_classes` mirror `qualify_level_textures`'s design (zip blocks to actors by position)? | **NO** — must use a different mechanism (see below) |
| Is there a SIMPLER mechanism that covers the common (non-colliding) case without per-actor reflection at all? | **YES** — `OBJ LIST CLASS=Class` (already used elsewhere as the flush-filler) enumerates every loaded class fully qualified; a bare name maps to a unique qualified form whenever no collision exists |
| What about the rare true-collision case? | **Open / out of scope for this pass** — no reliable read-back exists to attribute a *specific* actor instance to *which* colliding package's class it bound to; the safe behavior is to detect the ambiguity and refuse to guess, not silently qualify wrong |

## Setup

Reused the 2026-06-19 spike's recipe almost verbatim: a runtime dir (`_scratch/classspike/rt/`,
gitignored) of symlinks to the substrate `UED22/*` + copied inis with an extra absolute
`Paths=/repo/_scratch/classspike/rt/*.u` line, plus `UnrealShareDupe.u` — a byte-identical copy
of the substrate's `UnrealShare.u` (1003 bytes, `UnrealTestInfo extends TestInfo`, the smallest
package with a real placeable zero-property actor class, picked by the prior spike specifically
for zero crash risk). Driven via `docker compose run -d --name uned-classspike … uned` (never
`dx-lum-uned`), `wine_ctl.py exec`, and `qualify.dump_obj_dependencies`/`Driver` called directly
from the host (NOT nested inside another `docker exec` — `Driver` itself shells out to `docker
exec <container>`, so it must run where the `docker` CLI exists, i.e. the host, not inside the
editor container).

**Operational note (this session, not a code finding):** this work could only run from the main
`src/dx_lum` checkout, not a `klonr` worktree under `/tmp` — the Docker daemon here is itself
containerized (DinD) and its `/repo` bind mount for editor containers resolves through a
dedicated host volume tied to the main checkout; a fresh ephemeral container pointed at a
`/tmp` worktree path came up with an empty `/repo` (`entrypoint.sh: No such file or directory`).

## Test 1 — materialize round-trip: confirmed safe

A 3-actor level (`ZFirst`/`UnrealShare.UnrealTestInfo`, `MMiddleDupe`/
`UnrealShareDupe.UnrealTestInfo`, `ALast`/`UnrealShare.UnrealTestInfo` — a real TRUE collision,
both packages loaded) was imported via `MAP IMPORTADD` with qualified `Class=` on each actor,
then:
1. `MAP SAVE FILE=…roundtrip.dx` on the importing editor.
2. **Container removed entirely** (`docker rm -f`), a brand-new ephemeral editor started fresh
   (mirrors `export_and_qualify`'s unconditional stop-then-`ensure_editor`, never a reused one).
3. Both packages `OBJ LOAD`ed again, then `MAP LOAD FILE=…roundtrip.dx`.
4. `OBJ DEPENDENCIES PACKAGE=MyLevel` re-run on this fresh editor.

Result: **`Class UnrealShareDupe.UnrealTestInfo` appears exactly 3 times** (matching
`MMiddleDupe`'s one-actor reference shape from the live-collision spike) and
**`Class UnrealShare.UnrealTestInfo` appears exactly 6 times** (`ZFirst` + `ALast`, 3 each) —
the package binding survived `MAP SAVE` and a totally fresh `MAP LOAD` unchanged. This matches
the expectation that a resolved `UClass` reference is a real object-graph link serialized into
the `.dx`'s binary import table, not a text re-resolution — once import binds the right package
(already proven by the 2026-06-19 spike), persistence is structural, not text-dependent. **No
further round-trip risk exists**; `materialize.py`'s FULL RE-IMPORT → `MAP SAVE` → H3
post-verify (itself another `export_and_qualify` pass, same mechanism) carries a qualified
`Class=` correctly end to end.

## Test 2 — per-actor block order does NOT match level order

Two independent imports were dumped via `OBJ DEPENDENCIES PACKAGE=MyLevel` and compared against
each level's own `MAP EXPORT` actor order:

- **2-actor level** (`level.order`: `LevelInfo, ClsSpikeCube[brush], ClsSpikeOrig[UnrealShare],
  ClsSpikeDupe[UnrealShareDupe]`): dump's actor-relevant tail came back
  **`Dupe, Orig, Brush(actor), …, LevelInfo`** — the exact REVERSE of level order.
- **3-actor level** (`level.order`: `LevelInfo, Brush1[auto], ZFirst[UnrealShare],
  MMiddleDupe[UnrealShareDupe], ALast[UnrealShare]`): dump's actor-relevant tail came back
  **`Brush(actor), LevelInfo, …, UnrealShare(ZFirst), UnrealShareDupe(Middle),
  UnrealShare(ALast)`** — `Brush`/`LevelInfo` reversed relative to each other (consistent with
  "reverse" for that pair) **but the three class-actor blocks came back in FORWARD level order**,
  contradicting the first test's reversed result for an equivalent-shaped pair.

Two tests, two different orderings for structurally similar inputs — there is no consistent
forward/reverse/alphabetical rule. (Camera/viewport reference blocks for the editor's own UI —
not in `MAP EXPORT` at all — are also interleaved unpredictably among the level's actual actor
blocks, confirming the walk order is driven by something object-table/hash-related, not anything
that maps to authored level structure.) **This directly disproves the assumption a
`qualify_level_classes` mirroring `qualify_level_textures`'s zip-by-position design would have
relied on.** The texture case is NOT analogous: its positional guarantee is *within* a single
`Engine.Polys` block (poly-order inside one brush's own PolyList, confirmed by the 2026-06-19
read-surface-texture-package spike), a much narrower claim than "blocks across the whole package
appear in level order" — which this spike shows is false.

## Test 3 — the common case needs no per-actor reflection at all

`OBJ LIST CLASS=Class` (already in use elsewhere in `qualify.py` as `_FLUSH_FILLER_CMD`, since
it's guaranteed-verbose) lists **every currently loaded class, always fully package-qualified**
— confirmed in every dump in this and the prior spike (`UnrealShare.UnrealTestInfo` and
`UnrealShareDupe.UnrealTestInfo` both appear as their own lines regardless of which level is
loaded, since this reflects loaded PACKAGES, not the level's object graph). Grouping this list by
the part after the last `.` gives, for any bare class name, the complete set of currently-loaded
packages that could be its true binding:

- **Exactly one candidate** (the overwhelming common case — most class names aren't duplicated
  across a typical package set): the binding is unambiguous *without reading the level at all*.
  `qualify_level_classes` can set `cls = f"{package}.{bare_name}"` directly from this list, with
  zero per-actor reflection cost.
- **Zero candidates**: the class isn't currently loaded/resolvable — same failure shape as an
  unresolvable texture/mesh package elsewhere in this codebase (`packages.ensure_load_message`);
  surfacing this as a fail-fast error (not a silent bare pass-through) is consistent with the
  rest of the package-resolution code.
- **Two or more candidates** (genuine collision): **no implementable solution found this
  session.** Test 2 shows the only candidate read-back mechanism (`OBJ DEPENDENCIES`) can't
  attribute a *specific actor instance* to *which* colliding package it bound to, since block
  order carries no positional guarantee. The safe behavior is to **detect** the ambiguity (the
  bare name has 2+ loaded candidates) and **refuse to silently qualify** rather than guess —
  this is the existing pattern in this codebase for irreducible ambiguity (`select_by_name`
  raises on under-selection rather than guessing which actor was meant; `qualify_level_textures`
  raises on any count mismatch rather than mis-binding). A true collision is also self-correcting
  in the immediate term: the bare `Class=` already round-trips correctly through `apply` AS LONG
  AS only one of the colliding packages is ever loaded in the working set at a time (the common
  case in practice — accidental cross-package class-name collisions are rare, unlike textures,
  where content packages routinely reuse names like "Wall01").

## Implication for the design

`qualify_level_classes` should NOT mirror `qualify_level_textures`'s OBJ-DEPENDENCIES-block-zip
shape. Instead:
1. Read `OBJ LIST CLASS=Class` once (reusing the existing dump/parse machinery's connection, a
   cheap addition to the same already-required editor session).
2. Build `bare_name -> {qualified candidates}`.
3. For each actor in `level.order` whose `cls` has no `.` (still bare): exactly one candidate →
   qualify; zero → raise (unresolvable); 2+ → raise (ambiguous, can't safely auto-qualify — name
   the actor and the candidate set in the error so a human can resolve it, e.g. by renaming one
   of the colliding packages or by hand-qualifying the actor's `Class=` before the next import).
4. No round-trip risk once qualified — Test 1 closes that question definitively.

## Artifacts (`_scratch/classspike/`, gitignored)

`rt/` (runtime dir + `UnrealShareDupe.u`), `mixed_import.t3d`/`after_import.t3d` (2-actor +
brush test), `three_actors.t3d`/`three_after.t3d`/`roundtrip.dx`/`roundtrip_export.t3d` (3-actor
collision + round-trip test).

## Cross-links

- [Class-package collision spike](2026-06-19-class-package-collision.md) — the import-honors-
  qualifier finding this spike builds on; that spike's "EXPORT is still always bare" finding is
  unaffected.
- [`qualify.py`](../../../uedcli/qualify.py) — `qualify_level_textures`/`dump_obj_dependencies`, the
  existing texture-side implementation this spike found does NOT generalize to classes as-is.
- `../board/to-spec.md` — Class-package autoload for apply.
