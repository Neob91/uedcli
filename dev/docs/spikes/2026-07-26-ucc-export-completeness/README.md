# Spike — is UCC's offline `.dx` export content-complete? (Yes.)

**Date:** 2026-07-26, live against `dx-lum-uned:latest` with the retail Deus Ex install mounted.
**Question (owner):** the post-build verify could stop using a live editor entirely and read the
built map with `UCC.exe batchexport` — a plain command-line tool. *"Using UCC would be great, BUT
verify, because I'm not sure if it contains everything — compare with UnrealEd on OG DeusEx
levels."*

**Answer: UCC's export is content-complete, and it is never weaker than UnrealEd's.** Across five
retail maps up to 3653 actors, UCC's export and UnrealEd's own export of the same file agree on
every actor, every class, every brush and every property VALUE. The only differences are the
letter-case of names, which UE1 treats as insignificant — and on that point UCC is the more faithful
of the two, because it reports what the package stores while the editor reports what its own name
table holds. UCC is also 4–40× faster.

Harness: [`harness/compare_exports.py`](harness/compare_exports.py) (the two-phase sweep),
[`harness/name_case_probe.py`](harness/name_case_probe.py) (the name-case follow-up).

## Why the existing evidence was not enough

`2026-06-18-ucc-level-export.md` already concluded that UCC `batchexport` is "content-equivalent to
`MAP EXPORT`". It established that on **one synthetic level: four actors, 8693 bytes**, hand-built
for that probe — `LevelInfo0`, a builder brush, a `Light` and one subtract brush. Nothing about a
four-actor fixture speaks for a 3653-actor retail map full of movers, conversations, scripted pawns
and game-specific classes. Since the whole point of the post-build verify is to catch a build that
is silently wrong, resting it on that sample was not defensible.

## Method

Two phases, one editor container with the retail install mounted read-only.

**Phase 1 — can UCC read the shipped corpus at all?** Run `UCC.exe batchexport <map> Level T3D` over
all **120** `.dx` files in `DX/Maps`. Cheap (~2–6 s each), no editor involved.

**Phase 2 — does UnrealEd's own export differ?** For a sample, additionally drive the live editor
`MAP NEW` → `MAP LOAD FILE=<map>` → `MAP EXPORT`, and diff the two texts. Both sides go through
uedcli's own seam (`parse_t3d` → `level_order` → `normalize_level`), so a difference reported here
is one the verify would actually act on. Two known-contextual differences are folded first, both
already handled in production: the self-referential package prefix (in memory the level lives in
package `MyLevel`, on disk it is the file stem) and the editor-computed props in
`normalize.COMPUTED_PROPS`.

The sample is the four largest maps UCC read, plus the named diversity picks, **plus a control that
matters more than any of them**: maps UCC could *not* read are also put through the editor. A map
UCC cannot read only counts against UCC if the editor can read it.

### One methodological trap, hit and fixed — worth reading

The control initially reported that UnrealEd could read all three maps UCC had rejected. It was
wrong, and the way it was wrong is a live demonstration of a hazard that matters for any
script-driven editor work:

> `EXEC` does **not** abort on a failing line. When `MAP LOAD` failed, the editor simply kept the
> level it already had, and the very next `MAP EXPORT` wrote **that** — a full, healthy-looking
> 1304-actor export of the *previous* map. Three different maps each "exported successfully" as
> byte-identical copies of the map before them.

The tell was the identical file sizes. The fix is `MAP NEW` before `MAP LOAD`, so a failed load
leaves an unmistakably tiny empty level rather than a plausible wrong one, plus an actor-count floor
on the result. **A completion marker proves a script RAN, never that it did what it was asked** —
which is exactly why a build drive's success cannot be judged by its marker file alone.

(Incidental confirmation from the same mistake: exporting one unchanged level twice from one editor
gave byte-identical output apart from `TimeSeconds` and `AIProfile`, both already stripped by
`normalize`. `MAP EXPORT` is deterministic.)

## Results

### Phase 1 — UCC read 112 of 120 shipped maps

The 8 failures are all the same shape, and none is about export at all — the package will not
*load*:

| Maps | Failure |
|-------------------------------------------|---
| `00_Intro`, `99_Endgame1`–`99_Endgame4`   | `Can't find Class in file 'Class Engine.CameraPoint'`
| `NativeCatacombs`, `NativeHKMarket`       | `Can't find Class in file 'Class Engine.BreakableGlass'`
| `NativeUnatcoNoMov`                       | `Can't find Class in file 'Class Engine.ATM'`

**The control settles what this means: UnrealEd cannot read those maps either.** All four tested
(one per distinct missing class) produced an empty level in the editor too. So this is not a UCC
limitation — it is the UED22 substrate's v69 `Engine.u` lacking classes the game's own v68 `Engine`
package declares. Both readers sit behind the same `[Core.System] Paths` and both fail identically.

It also does not touch the verify's job. The verify re-reads a map **uedcli just built**, in a
substrate that had to load those classes to build it. A map referencing a class this substrate
cannot resolve could never have been built here in the first place.

### Phase 2 — zero content differences, on maps up to 3653 actors

| Map | actors (UCC / UnrealEd) | missing | class diffs | value diffs | brush diffs | UCC | UnrealEd |
|--------------------------|-------------|----|----|----|----|-------|---
| `01_NYC_UNATCOIsland.dx` | 3653 / 3653 | 0  | 0  | 0  | 0  | 3.2 s | 128.5 s
| `15_Area51_Page.dx`      | 3533 / 3533 | 0* | 0  | 0  | 0  | 5.6 s | 84.0 s
| `12_Vandenberg_Cmd.dx`   | 3361 / 3361 | 0* | 0  | 0  | 0  | 3.7 s | 88.5 s
| `10_Paris_Metro.dx`      | 3178 / 3178 | 0  | 0  | 0  | 0  | 3.1 s | 117.4 s
| `00_Training.dx`         | 1304 / 1304 | 0  | 0  | 0  | 0  | 2.7 s | 11.1 s

\* one actor differs in the CASE of its name only (`light1` vs `Light1`) — the same actor, same
line, same everything else. See below.

**Nothing is lost.** No actor, class, brush, polygon or property value differs on any map. The only
differences of any kind are letter-case, in two forms: property names (`MaxRange`/`maxRange`,
`UserList(0)`/`userList(0)`, `SeqNum`/`seqnum` — 10–17 per map) and, on two maps, one actor name.

**Property-name case is already a non-issue in production.** uedcli's compare casefolds property
keys and class names (`typedprops.key_text`, `normalize._actor_values`) precisely because UE1
`FName`s are case-insensitive. Those 10–17 differences per map are visible to this probe's stricter
raw-text diff and invisible to the verify.

### Where the name case comes from — and why UCC is the better witness

Reading the maps' own name tables offline explains every case difference, 5 maps out of 5:

| Map | package stores | UCC wrote | UnrealEd wrote |
|--------------------------|----------|----------|---
| `01_NYC_UNATCOIsland.dx` | `Light1` | `Light1` | `Light1`
| `15_Area51_Page.dx`      | `light1` | `light1` | **`Light1`**
| `12_Vandenberg_Cmd.dx`   | `light1` | `light1` | **`Light1`**
| `10_Paris_Metro.dx`      | `Light1` | `Light1` | `Light1`
| `00_Training.dx`         | `Light1` | `Light1` | `Light1`

**UCC emits the spelling the package stores. The editor emits its own, whatever the package says.**
That follows from how UE1 names work: `FName`s live in one process-global table and are matched
case-insensitively, so the first spelling registered wins for every later lookup in that process.

This is not a wash between two arbitrary conventions. **uedcli's compare keys actors by verbatim
name** — only property keys and class names are casefolded, actor names are not
(`normalize.compare_view`). So the exporter that is authoritative on name case is the one the verify
should be reading, and that is UCC: its answer is a pure function of the file, while the editor's is
a function of the editor's process state.

### It IS session history — but it does NOT reach the build path

Two follow-up probes, because "the editor's export depends on its process state" is only alarming if
that state actually moves.

**`name_case_probe.py` — a FRESH editor preserves the package's spelling.** Loading
`15_Area51_Page` (whose table stores `light1`) as the *first* map in a brand-new editor exported
`light1`, all 3533 actors intact. So the capitalised form the sweep saw was not a constant
re-casing: it came from a name registered **earlier in that session**, by a previously loaded map.
A reused editor's `MAP LOAD` exports really do drift with what it loaded before.

**`name_drift_probe.py` — but successive uedcli BUILDS in one editor do not drift.** Three rounds in
one editor, using only uedcli-authored content on the production add path
(`MAP NEW` → `EDIT PASTE` → `MAP EXPORT`):

| Round | authored | editor wrote |
|-------|-----------------|---
| 1 | `probelight1`   | `probelight1`
| 2 | `ProbeLight1`   | `ProbeLight1`
| 3 | `probelight1`   | `probelight1`  ← **no drift**

Round 3 authored the lowercase name *after* round 2 had registered the capitalised one, and got the
lowercase name back. So whatever re-cases a name on `MAP LOAD` does not reach actors introduced by
`EDIT PASTE`, and **the hypothesis that a warm editor would rewrite a later build's actor names to
an earlier build's casing is FALSIFIED.** That mattered enough to test: the compare is
case-sensitive on actor names, so it would have been an intermittent verify failure on correct
builds, of exactly the kind that is near-impossible to diagnose from the outside.

The mechanism behind the asymmetry is **not established here** — the global-first-wins model
explains the `MAP LOAD` result and is contradicted by round 3, so something about T3D import differs
and this spike did not chase it. What is measured is the boundary: **`MAP LOAD` into a reused editor
re-cases; `EDIT PASTE` into a reused editor does not.**

The practical consequence lands on the verify, not on the build. `level materialize` never `MAP
LOAD`s a package — it does `MAP NEW`, adds actors, rebuilds and saves — so the build path is on the
safe side of that boundary. A verify that re-opened the built map **in a reused editor** would be on
the wrong side of it. A verify that reads the file with UCC is not on the boundary at all.

## What this means for the design

1. **The no-editor verify is sound on completeness.** The question the owner asked is answered:
   UCC does contain everything, measured against UnrealEd on the shipped levels rather than on a
   four-actor fixture.
2. **UCC is never the weaker reader.** Every map it cannot read, the editor cannot read either, for
   a reason that belongs to the substrate and cannot arise for a map uedcli itself just built.
3. **UCC is deterministic where the editor is not.** The editor's export depends on its own name
   table; UCC's depends only on the bytes. For a check whose entire job is deciding whether a build
   is wrong, "a pure function of the file under test" is the property that matters.
4. **Speed, measured rather than assumed:** 2.7–5.6 s against 11–128 s on the same maps, in the
   same container.
5. **A reused editor is measurably less faithful than a fresh one for `MAP LOAD`** — which is an
   argument against ever putting the verify's re-read into the warm editor, independent of the
   `MAP SAVE` blocker SP-E found. The build path itself is unaffected (it never `MAP LOAD`s).

## What is NOT established here

- **The qualification half.** This spike measures the EXPORT (`.dx` → T3D text). The verify also
  has to resolve bare class and texture names to their packages, which today it does by typing
  `OBJ DEPENDENCIES` / `OBJ LIST` into a live editor. Whether that can be replaced by reading the
  map's own import table is a separate question, designed in
  `specs/2026-06-27-uedcli-native-dx-read-design.md` and not built. Nothing here settles it.
- **Anything about maps this substrate cannot load.** 8 of 120 are simply outside what either
  reader can open here.
- **Why `MAP LOAD` re-cases a name and `EDIT PASTE` does not.** The boundary is measured; the
  mechanism is not. A global first-wins `FName` table explains the first result and is contradicted
  by the second, so the real story is more specific than that and this spike did not pursue it.
- **The 112 maps UCC read were not all diffed against the editor** — 5 were, chosen as the largest
  plus the diversity picks. The editor leg costs 11–128 s per map, so a full 112-map diff was not
  run. Nothing suggests the remainder differ, but they were not checked.
