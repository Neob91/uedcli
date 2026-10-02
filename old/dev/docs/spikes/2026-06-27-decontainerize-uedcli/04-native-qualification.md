# Spike 4 — native qualification (replace `OBJ DEPENDENCIES` / `OBJ LIST CLASS`)

**Status: RESOLVED — native qualification works, at parity with the editor and often
trivially.** Harness: [`harness/qualify_native.py`](harness/qualify_native.py).

## Question

`qualify.export_and_qualify` spins a fresh editor, `MAP LOAD`s the `.dx`, and runs
`OBJ DEPENDENCIES PACKAGE=MyLevel` (per-poly texture → package) + `OBJ LIST
CLASS=Class` (bare actor class → package) because T3D carries only **bare** names.
This is a whole live-editor leg. Can we qualify natively?

## Answer: yes — and for the common case it's free

**Case A — reading an existing `.dx`: the import table IS the qualification.** An
Unreal package's import table names every external object fully qualified
(package + class + object name). Parsing it natively (`dxpkg`/`package_rw`) yields
exactly what `OBJ DEPENDENCIES` recovers. On `00_Intro.dx` (355 imports), with no
editor: **143 Textures, 112 Classes, 24 Sounds, 1 Music**, all qualified —
`CoreTexMetal.Heli_LiftMetl_A`, `Engine.Light`, `MoverSFX.SlideDoorOpen`, … This
removes the entire fresh-editor + `MAP LOAD` + `OBJ DEPENDENCIES` dance for every
"read a `.dx` into the model" path (`session start <dx>`, apply THEIRS, H3 verify).

**Case B — authored-from-scratch / T3D (only bare names): resolve against the
manifest.** Build a `name → {packages}` index from the export tables of the level's
manifest packages; unique → qualify, collision → report all candidates (the editor's
own contract — it can only resolve within loaded packages and raises on ambiguity).
Over the **entire** install (74 packages): 4219 distinct texture names, **4144 unique,
only 75 (1.8%) collide**. Per level the manifest is ~6–65 packages (not all 74), so
collisions are rarer still and scoped exactly as the editor sees them. Same for
classes: over the 17 code packages, **1301 class names, 0 collisions**.

Native is at least at parity and arguably better: it can enumerate *every* candidate
package for a colliding name (the editor's `OBJ LIST` does too, but offline we already
hold them), enabling a deterministic disambiguation policy (e.g. prefer the manifest
package nearest in load order, or the one the import table already pinned).

## Why this matters

`OBJ DEPENDENCIES`/`OBJ LIST CLASS` are two of the editor-only operations in the
materialize/qualify path. Both fall to native package parsing:
- the read-`.dx` path needs **no** name→package search at all (import table is exact);
- the authored path needs a pure-Python manifest index, no editor.

Combined with Spikes 1–3 this removes another editor leg; what remains editor-shaped
is only the BSP build (D2) and lighting/paths (Spike 5).

## Deferred
- A deterministic collision policy for Case B (manifest load-order precedence) +
  unit tests — small, on the roadmap.
- Wire into `qualify.py`: replace `dump_obj_dependencies`/`qualify_level_classes`
  with import-table read (Case A) and the manifest index (Case B).
