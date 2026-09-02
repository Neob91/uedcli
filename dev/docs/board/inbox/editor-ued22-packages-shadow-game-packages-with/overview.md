+++
priority = "p1"
kind = "debug"
summary = "Editor UED22 packages shadow game packages with different class defaults — materialize silently drops props at the editor-default (wrong in-game)"
+++

# Editor UED22 packages shadow the game's, with different defaultproperties

`materialize` writes the unbuilt `.dx` with props that differ from the GAME class default (trunk
convention), MAP LOADs it, and the editor MAP SAVEs. The editor omits any prop equal to ITS class
default. When the editor's default ≠ the game's default, the editor drops the prop, and the real
game then loads it as the GAME default — a different value. Silent fidelity loss, not just a verify
artifact.

## Root cause

The editor search path puts `uned/UED22/*.u` BEFORE `dev/games/deusex/System/*.u`. UED22 bundles its
OWN `DeusEx.u` (1.9 MB, md5 78c41f…) that SHADOWS the real game `DeusEx.u` (5.4 MB, md5 d343da…) —
a different build with different `defaultproperties`. Same for other gameplay packages likely.

## Confirmed case

`02_nyc_underground` `Barrel8` (`DeusEx.Barrel1`), `SkinColor=SC_Biohazard` (enum ordinal 0):
- game default `SkinColor = SC_Rusty` (3); editor default `SkinColor = SC_Biohazard` (0).
- writer emits `SkinColor=0` (correct); editor sees `0 == its default 0` → omits on save.
- built `.dx` has no `SkinColor`; game/verify resolves the omission to `SC_Rusty` (3).
- Post-verify: `built SkinColor omitted (class default 3)` vs `intended SC_Biohazard`. In-game the
  barrel would render Rusty, not Biohazard.

## Scope

Comparing editor-vs-game class defaults over the 79 classes in `02_nyc_underground`: thousands of
default diffs, but MOST are non-editable/runtime props the compare already drops (edit-rule). The
ones that bite are EDITABLE (`var()`) props whose authored value equals the editor default but not
the game default. `SkinColor` is one confirmed. Full impact = (editable props) ∩ (editor≠game
default) ∩ (value==editor default), per level — needs enumeration.

`02_nyc_bar` and `01_nyc_unatcohq` materialize clean (no such prop), so it is level-dependent.

Pre-existing — independent of the faithful-order / movers-in-package rework. Surfaced by testing
`underground`.

## Fix directions (owner decision)

1. Reorder editor Paths so the GAME packages win over UED22's shadowing copies; keep only UED22's
   genuinely editor-only packages (Editor.u/UnrealEd.u/brush builders). Risk: UED22 may wedge on the
   game's DeusEx.u build (version skew) — must test.
2. Enumerate exactly which UED22 `.u` are editor-only vs game-shadows; drop the shadows from Paths.
3. Scope materialize to levels without editor-default-divergent editable props (bar/unatcohq clean);
   fix later.

## Empirical blocker (2026-08-24)

Force-building a `DeusEx.u` stub from the retail v68 package FAILS at the first step — UCC
`batchexport class uc` (decompile) can't even load it:

```
Loading package /resources/r000/DeusEx.u...
Failed loading package: Can't find Function in file 'Function Core.Object.Sprintf'
```

The retail `DeusEx.u` links Deus-Ex-engine natives (`Core.Object.Sprintf`, …) that UT-lineage
`Core` lacks. The stub toolchain (v469 UCC) is UT-lineage, so it cannot decompile retail Deus Ex
code — which is exactly WHY UED22 ships its own recompiled `DeusEx.u` (rebuilt against UT `Core`,
with the divergent defaults). Generating a game-derived `DeusEx.u` stub via UCC is therefore not
possible with this toolchain.

NB uedcli's OWN offline parser (`classdefaults`/`uprops`) DOES read the retail `DeusEx.u` defaults
(that is how the verify knows `SkinColor=SC_Rusty`). So the correct defaults are available to uedcli
offline — just not via a UCC recompile. Candidate fixes: (a) model-side post-build re-inject of props
the editor dropped at its wrong default; (b) a Deus-Ex-lineage UCC; (c) native v69 stub writer using
uedcli's own package reader; (d) scope/accept.
