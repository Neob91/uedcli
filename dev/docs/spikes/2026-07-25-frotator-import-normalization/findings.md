# Spike — does T3D import normalize FRotator mod 65536?

**Date:** 2026-07-25 · **Verdict: NO — UnrealEd preserves an FRotator field VERBATIM on every leg.**
**Harness:** [`probe.py`](probe.py) (point actors, `MAP IMPORTADD`), [`probe_brush.py`](probe_brush.py)
(brushes, `EDIT PASTE`). Raw output was written to the gitignored `_scratch/rotprobe_*`.

## The question

UE1 stores rotations as FRotator integers (65536 = 360°). Committed editor-exported `.t3d` files
contain out-of-range values — `Yaw=-131072` (two full turns), `Yaw=-65536`, `Yaw=-81920` — apparently
preserved verbatim. But two committed docstrings in `uedctl/rotation.py` contradicted each other:

- `compose_uu` claimed *"a materialize import normalizes mod 65536 anyway"*.
- `emit_frotator` / the compare-side fold require that values are **never** reduced.

This is load-bearing. `level materialize` imports the T3D trunk into UnrealEd, saves, re-exports, and
text-compares against what it intended (the H3 post-verify). **If import normalized mod 65536**, an
actor authored `Rotation=(Yaw=-131072)` would come back as `Yaw=0` — and since zero equals the class
default, the whole `Rotation=` line would vanish. Post-verify could then NEVER pass for any ingested
retail actor with an over-range rotation. 20,109 of the 23,960 `Rotation` components in the committed
corpus are out of range, so this would have been catastrophic rather than marginal.

## Method

A fresh ephemeral `dx-lum-uned` editor, driven twice (once for point actors, once for brushes). Each
authored value was read back on **three independent legs**, so no single leg could hide a change:

- **A** — `MAP EXPORT` immediately after import (what the editor holds in memory).
- **B** — `MAP SAVE` to `.dx`, then an **offline UCC `batchexport`** — this is the exact artifact the
  H3 post-verify actually reads.
- **C** — `MAP LOAD` of the saved `.dx`, then `MAP EXPORT` (binary round-trip).

## Result — every value byte-identical on A, B and C

| authored | A (post-import) | B (save → UCC) | C (reload) |
|---|---|---|---|
| `(Yaw=-131072)` | `(Yaw=-131072)` | `(Yaw=-131072)` | `(Yaw=-131072)` |
| `(Yaw=-65536)` | `(Yaw=-65536)` | `(Yaw=-65536)` | `(Yaw=-65536)` |
| `(Yaw=65536)` | `(Yaw=65536)` | `(Yaw=65536)` | `(Yaw=65536)` |
| `(Yaw=-81920)` | `(Yaw=-81920)` | `(Yaw=-81920)` | `(Yaw=-81920)` |
| `(Yaw=-16384)` | `(Yaw=-16384)` | `(Yaw=-16384)` | `(Yaw=-16384)` |
| `(Yaw=16384)` (control) | `(Yaw=16384)` | `(Yaw=16384)` | `(Yaw=16384)` |
| `(Pitch=-65536,Roll=-131072)` | identical | identical | identical |

Brushes pasted via `EDIT PASTE` (plus a `MAP REBUILD`) behaved identically for `(Yaw=-131072)` and
`(Yaw=16384)`.

## What follows

1. **No leg normalizes.** Not import, not `MAP SAVE`, not the binary round-trip, not the UCC
   re-export. There is no "the save step fixes it up" escape hatch.
2. **Negatives are not wrapped either** — `(Yaw=-16384)` stays `-16384`, it does not become `49152`.
   The field is a plain signed integer.
3. **Export default-diffing compares the RAW INTEGER, not the reduced angle.** `(Yaw=65536)` is
   orientation-identical to zero, yet the `Rotation=` line is still emitted — so a full-turn rotator
   counts as a non-default value on export, and post-verify sees it on both sides.
4. The feared permanent-abort failure mode **cannot occur**.

## Rulings

- **Never reducing a stored FRotator component is CORRECT** and now rests on live evidence rather
  than corpus inference. (The fold this ruling was written against, `rotation.
  canonical_rotation_value`, was deleted on 2026-07-25 02:15 UTC when the compare became typed; the
  RULE moved with it — `typedprops` decodes an FRotator component as a VERBATIM `IntProperty` int,
  pinned by `test_engine_facts.test_over_range_frotator_components_are_never_reduced_mod_65536` and
  end-to-end by `test_normalize.test_over_range_rotation_components_are_never_reduced_mod_65536`.
  Reducing would now make an over-range rotator compare EQUAL to an unrotated actor —
  `-131072 % 65536 == 0` — i.e. a false pass, not merely a spurious abort.)
- **`compose_uu`'s claim was FALSE and is superseded** (`rotation.py`, 2026-07-25). Its own mod
  reduction is harmless — uedctl writes the reduced value to the trunk, so both compare sides agree —
  but the justification was wrong, and wrong justifications license real bugs.
- **Reducing mod 65536 is fine for MEASURING orientation** (`actor_rotation_uu`, `is_identity_uu`),
  **never for anything written or compared as text.**

## Pinned by

- `tests/test_engine_facts.py::test_over_range_frotator_components_are_never_reduced_mod_65536`
  (offline — guards *our* code, runs in the default suite).
- `tests/test_driver_integration.py::test_editor_preserves_an_over_range_frotator_verbatim`
  (`@pytest.mark.integration` — guards the *substrate*, trips if UED22 is ever swapped or rebuilt).
