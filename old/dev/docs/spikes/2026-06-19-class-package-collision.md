# Class-package collision spike (2026-06-19)

**Question.** The [T3D package qualification
spike](2026-06-19-t3d-package-qualification.md) found `Class=` resolves by
**global class name**, ignoring the package qualifier — but admitted it never
tested a TRUE collision (the substrate's 308 loaded classes have zero
name collisions; its `Class=Editor.Light` vs `Class=Engine.Light` test only
proved the wrong qualifier isn't *rejected*, not how a real collision
resolves). Does duplicating a `.u` class package under a new filename
manufacture a genuine same-name-different-package class collision, the way
duplicating a `.utx` did for textures? If so, does `Class=Package.ClassName`
actually disambiguate under TRUE collision, or was the "ignored" verdict
right?

## Verdict

| Question | Verdict |
|---|---|
| Does duplicating a `.u` file produce a genuine class-name collision? | **YES** — same mechanism as the texture spike |
| Does the duplicate need any internal patching (embedded package name)? | **NO** — the package name comes from the **filename** at `OBJ LOAD`/`Paths` time; the `.u`'s internal name-table copy of its own name is informational, not authoritative |
| Under TRUE collision, is `Class=Package.ClassName` honored? | **YES — REVERSES the prior weak-test verdict.** Each actor binds to the class from the **named package**, not a single global pick |
| Does EXPORT qualify `Class=` under collision? | **NO** — still always bare, same as the unqualified case |
| Any caveats? | A **large/complex** package (`Engine.u`, 1.2 MB) **crashes** the editor on duplicate-load (`Palette …: Serial size mismatch`) — collision-by-duplication is reliable only for small, simple packages |

**Bottom line:** the prior spike's "package ignored" conclusion was an
artifact of having no real collision to test — under a genuine collision the
package **is** honored, just like `Texture=`. This **changes** (overturns)
item 5 of the qualification spike's recommendation for `Class=`, but does
**not** change the surface-texturing spec's bottom line, because `Class=`
still doesn't round-trip through **export** (still bare) — so the same
"package is authored data, store it, can't recover it from a plain export"
conclusion holds for actor classes, just for a different underlying reason
(export strips it; it's not that import can't use it).

## Setup

Ephemeral editor (never `dx-lum-uned`), same recipe as the qualification
spike: a runtime dir `_scratch/classdupe/rt/` of symlinks to the substrate
`Tools/uedcli/uned/UED22/*` (container-relative symlink targets,
`/repo/Tools/uedcli/uned/UED22/<name>`, since the bind mount path differs
from the host path used to build the runtime dir) + copied inis, `[Core.
System] Paths` rewritten to absolute substrate + an extra
`Paths=/repo/_scratch/classdupe/rt/*.u` line so a `*Dupe.u` file dropped into
`rt/` is discoverable.

```
docker compose run -d --name uned-classdupe \
  --entrypoint "/usr/bin/tini -- bash /repo/Tools/uedcli/uned/entrypoint.sh" \
  -e UED_DIR=/repo/_scratch/classdupe/rt \
  -v uned-wp-classdupe:/wineprefix uned
```

Driven via `docker exec uned-classdupe python3 /repo/Tools/uedcli/uned/wine_ctl.py exec "<VERB>"`.

## Picking a package to duplicate

The substrate's `.u` files were checked for a small, self-contained
candidate (name table extracted per `extracting-from-dll.md`'s ASCII-string
recipe — **`.u` package name tables are ANSI/Latin-1, length-prefixed, NOT
UTF-16LE** like the engine DLLs; the wide-string recipe finds nothing in a
`.u`):

- **`CaroneElevatorSet.u`** (16 KB, defines `CaroneElevator expands Mover` —
  a real placeable actor class) — **rejected**: its `CEDoorButton` class has
  an `ObjectProperty`/`ClassProperty` dependency on a package literally named
  **`Effects`**, which doesn't exist in this substrate (not the `Engine.
  Effects` *class* — a distinct `Effects` *package* the linker demands at
  full load). `OBJ LOAD FILE=…CaroneElevatorSet.u` (the **original**, not
  even the dupe) fails: `Warning: Failed to load 'Effects': Can't find file
  for package 'Effects'` — confirming this is a substrate-completeness gap,
  not a dupe-specific issue.
- **`Engine.u`** (1.2 MB) — **rejected**, but informatively: duplicating and
  loading it **crashed the editor** (`Critical: appError called: Palette
  EngineDupe.Palette3: Serial size mismatch: Got 1, Expected 1027`). A big,
  structurally-complex package (native classes, many embedded sub-objects
  like `Palette`s) does not survive being loaded twice under two names —
  this is a real **limit** on the duplication trick, not just caution.
  Recovered by tearing down and recreating the container (the documented
  crash-recovery pattern in `quirks.md`).
- **`FrameBuilder.u`** (6.6 KB, `class FrameBuilder expands Editor.
  BrushBuilder`) — loads cleanly under a dupe name (`FrameBuilderDupe.u`,
  confirmed coexisting as `FrameBuilder.FrameBuilder` +
  `FrameBuilderDupe.FrameBuilder` via `OBJ LIST CLASS=Class`), but
  `BrushBuilder` is **not** an `Actor` subclass — can't `MAP IMPORTADD` it as
  a placeable actor, so it can't drive the import-side test.
- **`UnrealShare.u`** (1003 bytes! — the smallest substrate `.u`) — **used**.
  Defines `class UnrealTestInfo extends TestInfo` (`TestInfo` → `Info` →
  `Actor`, a real placeable, zero-property actor class), deps only `Core`/
  `Engine` (always resident). Loads and duplicates cleanly with **zero**
  crash risk.

## Internal package-name string: present, but not load-bearing

Per-byte inspection of `CaroneElevatorSet.u` confirms the `.u` format's name
table (length-prefixed ASCII, e.g. `\x12CaroneElevatorSet\x00` — `0x12`=18=
strlen+1) includes a copy of **the package's own name** as entry #5 (after
`None`/class names). This looks like it might need patching when the file
is renamed, but it does **not**: copying `UnrealShare.u` byte-for-byte to
`UnrealShareDupe.u` (confirmed identical `md5sum`, **no bytes changed**) and
loading it produces a class genuinely named `UnrealShareDupe.UnrealTestInfo`
— the editor derives the package's `FName` from the **file's name at load
time** (`OBJ LOAD FILE=`/`Paths=` discovery), not from this embedded string.
The embedded copy is the package's own self-reference (used internally for
its own `Outer` chain when *that* package was originally compiled/saved),
irrelevant to how a *freshly loaded* copy under a new filename is named.
This matches the texture-package finding (no internal rename needed) and
generalizes it to code packages.

## Test 1 — manufacturing the collision: confirmed, durable

```
cp UnrealShare.u UnrealShareDupe.u        # byte-identical, md5 matches
OBJ LOAD FILE=Z:\…\UnrealShare.u          # original (boot doesn't load it; EditPackages omits it)
OBJ LOAD FILE=Z:\…\rt\UnrealShareDupe.u   # the duplicate
OBJ LIST CLASS=Class
```

Both loaded without error or rename. `OBJ LIST CLASS=Class` (after the
log's flush lag, confirmed via a follow-up noisy command) shows, stably,
across repeated clean per-package queries (`OBJ LIST CLASS=Class
PACKAGE=UnrealShare` / `PACKAGE=UnrealShareDupe`):

```
Log: Class UnrealShare.UnrealTestInfo                                                     1920       1920
Log: Class UnrealShareDupe.UnrealTestInfo                                                 1920       1920
```

Two distinct `UClass` objects, identical class name (`UnrealTestInfo`),
different package — the exact shape of the texture spike's
`Area51Wall_A` collision, now for code. A third copy
(`UnrealShareDupe2.u`) was added later for the 3-way disambiguation test
(below) and loaded the same way with the same result.

## Test 2 — actor import under TRUE collision: package IS honored

`UnrealTestInfo` has no own properties (just two `state` blocks), so there's
no default-property discriminator — the only way to tell which package's
class got bound is to read back the resolved reference, not guess from
visible behavior. `OBJ LIST`/`MAP EXPORT` print only the **bare** class name
for an instance, so a different command was needed:

**`OBJ DEPENDENCIES PACKAGE=MyLevel`** (the same verb the read-surface-
texture-package spike found for textures) walks the level's object graph
and, for each referencing actor, prints a `Package MyLevel references: …
Class <Package>.<ClassName>` block **in level order**, fully qualified. This
is the load-bearing read for this whole spike — `MAP EXPORT`/`OBJ LIST` are
not enough to see which package an actor's `Class=` actually resolved to.

Clean single-shot test, three packages loaded (`UnrealShare`,
`UnrealShareDupe`, `UnrealShareDupe2`, all defining `UnrealTestInfo`), one
`MAP IMPORTADD` of three actors:

```
Begin Actor Class=UnrealShare.UnrealTestInfo Name=Carrier500       Location=(X=500)
Begin Actor Class=UnrealShareDupe.UnrealTestInfo Name=Carrier600   Location=(X=600)
Begin Actor Class=UnrealShareDupe2.UnrealTestInfo Name=Carrier700  Location=(X=700)
```

All three imported (`MAP EXPORT` confirms `Carrier500/600/700` present, bare
`Class=UnrealTestInfo` for all — **export is bare even under TRUE
collision**, same as textures). `OBJ DEPENDENCIES PACKAGE=MyLevel`, run once
on this clean level, printed the three actors' reference blocks **in level
order**, matching the requested qualifiers exactly:

```
Log:    Package MyLevel references:
Log:       Package MyLevel
Log:       Class UnrealShare.UnrealTestInfo        # ← Carrier500, requested UnrealShare ✓
Log:       Class UnrealShare.UnrealTestInfo
Log:       Class UnrealShare.UnrealTestInfo
Log:       Texture Engine.S_Actor
Log:    Package MyLevel references:
Log:       Package MyLevel
Log:       Class UnrealShareDupe.UnrealTestInfo     # ← Carrier600, requested UnrealShareDupe ✓
Log:       Class UnrealShareDupe.UnrealTestInfo
Log:       Class UnrealShareDupe.UnrealTestInfo
Log:       Texture Engine.S_Actor
Log:    Package MyLevel references:
Log:       Package MyLevel
Log:       Class UnrealShareDupe2.UnrealTestInfo    # ← Carrier700, requested UnrealShareDupe2 ✓
Log:       Class UnrealShareDupe2.UnrealTestInfo
Log:       Class UnrealShareDupe2.UnrealTestInfo
Log:       Texture Engine.S_Actor
```

**Each actor bound to the class from the package it was qualified with —
not a single global pick, not load order, not the first/last loaded.** A
2-way order-swap control (`UnrealShareDupe.UnrealTestInfo` imported
*before* `UnrealShare.UnrealTestInfo`, reversing the qualification spike's
ordering) gave the same per-actor result, ruling out "whichever loaded
first" as an alternative explanation (full transcript: `after_swap.t3d` +
the corresponding `OBJ DEPENDENCIES` dump in the session log, reproduced
cleanly in the final 3-way single-shot run above which removed all
ambiguity from accumulated prior state).

This **directly contradicts** the prior spike's `Class=Editor.Light` test,
which — with no real collision available — could only show the wrong
qualifier wasn't *rejected*. With a real collision, the qualifier is not
ignored: it is the correct, sole determinant of which package's class an
actor instantiates.

## What does NOT change

- **EXPORT is still always bare** — `Class=UnrealTestInfo`, never
  `Class=UnrealShareDupe.UnrealTestInfo`, even reading back an actor from a
  package that only exists as the non-default one. Confirmed in every test
  above. This matches `Texture=`'s export behavior exactly.
- **A raw `.t3d` without its `.dx`/session still carries no package
  information** for `Class=`, same as for `Texture=`. The qualification
  spike's merge implication (item 4) is unaffected.
- **The actor's class package still can't be *read back* from a plain
  export or `OBJ LIST`** — recovering it after the fact needs the heavier
  `OBJ DEPENDENCIES PACKAGE=MyLevel` reflection (or, for uedcli's own
  purposes, simply never losing it — see below).

## What DOES change — surface-texturing spec implication

The qualification spike's item 5 said: *"`Class=` is a non-issue for
surface texturing but confirms the known gap: the actor's class package
can't be derived from `Class=` (export bare; import ignores the
qualifier)."* The **"import ignores the qualifier"** half is now disproven
under a true collision — import **honors** it, exactly like `Texture=`.

This means uedcli's actor-class package handling is symmetric with the
texture-package design (already recommended in the qualification spike):

1. **The package is still authored data uedcli must own** — unchanged,
   because EXPORT still strips it. No read of a `.dx`/T3D recovers an
   actor's class package, regardless of whether a real collision exists in
   the loaded package set today.
2. **But the materialize-time qualified emit is now confirmed to matter
   for correctness, not just to be safely ignorable.** If uedcli ever emits
   actors whose class lives in a package that collides by name with another
   loaded package (plausible for DeusEx mod content — many LUM/community
   `.u` files reuse common class names), emitting **bare** `Class=` risks
   the editor binding the **wrong package's class** under ambiguity
   (whichever loads first/last — not pinned down here, and not needed: the
   fix is to never rely on it). uedcli should emit the **qualified**
   `Class=Package.ClassName` at materialize (the same `packages` manifest
   that already tracks the actor's declared package, mirroring the
   `texture_package` design) whenever the package is known, exactly as
   recommended for `Texture=`.
3. **No regression risk from doing so today**: the qualified form was
   accepted and correctly bound in every test here, including the
   already-`Class=Engine.Light`-qualified case from the original
   qualification spike (which "worked" only because no collision existed to
   expose the difference) — qualifying is strictly safer, never worse, than
   bare.

## Caveats / scope limits

- **Collision-by-duplication is reliable only for small, dependency-light
  packages.** `Engine.u` crashed the editor outright; a package with
  external soft-dependencies that aren't on the load path (`Effects` for
  `CaroneElevatorSet.u`) fails to load at all (not specific to duplication —
  the *original* failed identically). This is a tooling/test-rig limit on
  *how to manufacture* a collision live, not a finding about the collision
  behavior itself — once a clean small package loads twice, the behavior
  above held with no exceptions across 3 independent test rounds (2-way,
  2-way swapped, 3-way single-shot).
- **No default-property discriminator was available** on `UnrealTestInfo`
  (it has none) — discrimination relied entirely on `OBJ DEPENDENCIES`'s
  package-qualified reflection output, not on observed actor behavior. A
  follow-up could pick/author a class with a distinguishing default value
  to additionally confirm via `GETPROPERTIES`-style readback if a console
  path for that is ever found, but `OBJ DEPENDENCIES` already gives a
  decisive, repeatable signal.
- **`OBJ DEPENDENCIES PACKAGE=MyLevel` dumps in *level actor order*, not
  alphabetical/random** — confirmed by cross-referencing against `MAP
  EXPORT`'s actor order in every run; this ordering is what makes per-actor
  attribution unambiguous without needing a property discriminator.

## Artifacts (`_scratch/classdupe/`, gitignored)

- `rt/` — the writable runtime dir (substrate symlinks + copied inis with
  absolute `Paths=` + `UnrealShareDupe.u`/`UnrealShareDupe2.u`/
  `FrameBuilderDupe.u`/`CaroneElevatorSetDupe.u`).
- `import_collision.t3d` / `import_collision_swap.t3d` / `import_three.t3d`
  — the import probes (2-way, 2-way swapped, 3-way).
- `after_import.t3d` / `after_swap.t3d` / `after_three_clean.t3d` — the
  captured `MAP EXPORT` bytes confirming successful import + bare `Class=`.
- `baseline.t3d` — empty-level control export.

## Cross-links

- [T3D package qualification spike](2026-06-19-t3d-package-qualification.md)
  — the texture-side original finding + the weak `Class=` test this spike
  supersedes for the collision question (its `Texture=` findings are
  unaffected and still the model).
- [`commands.md`](../unrealed/commands.md) "Objects / packages / assets" —
  `OBJ DEPENDENCIES PACKAGE=MyLevel`'s doc entry (added by the parallel
  read-surface-texture-package spike; load-bearing for this spike's actor
  read-back).
- [`extracting-from-dll.md`](../unrealed/extracting-from-dll.md) — the
  string-extraction method; note its UTF-16LE assumption is for the
  **engine DLLs**, not `.u` asset/code packages (ANSI name tables).
- Surface texturing design (package-binding consumer):
  `2026-06-19-uedcli-surface-flags-texturing-design.md` (if/when written) —
  this spike's actor-class-package finding generalizes the texture-package
  recommendation to `Class=`.
