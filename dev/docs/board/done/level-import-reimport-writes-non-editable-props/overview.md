+++
priority = "p1"
kind = "debug"
summary = "level import/reimport writes non-editable props, breaking cross-actor refs on rebuild"
+++

# level import/reimport writes non-editable props, breaking cross-actor refs on rebuild

Owner asked for this at p0; board's priority vocab tops out at `p1` (highest), so filed there.

## Owner's input (verbatim substance)

- `MyMarker` (seen on `DeusEx.Ammo10mm` and presumably other `DeusExPickup` descendants) is **not
  editable in UnrealEd** — confirmed by the owner, who is certain of this. It must come from
  "Build Paths" (an editor build step), not designer authoring.
- Ruling: **any non-editable field should be skipped on `level import`/`level reimport`**, except
  fields already flagged as special cases — specifically mover `KeyPos`/`KeyRot` (and by the
  existing precedent below, `PrePivot`).
- Owner asked: do we already have handling for the mover-keyframe special case elsewhere? Answer
  below: yes, but only on the COMPARE side, not on import's write side (see "Current KeyPos/KeyRot
  handling").

## What triggered this

Importing an external Deus Ex mod map (`Maps/20_Downtown.dx`, `git@github.com:neob91/dx_lum.git`,
not part of this repo) via `level import`, then trying to `level materialize`/`level photo --game`
the resulting trunk: repeated `post-verify mismatch: actor 'X' is in the intended level but MISSING
from the built map`, one actor at a time, across unrelated classes (`Ammo10mm0`, `AmbientSound0`,
`AmbientSound1`, …). Root cause traced to `Ammo10mm0`'s `MyMarker=InventorySpot'20_Downtown.
InventorySpot45'` — a same-level object reference that `level import` writes out qualified with the
SOURCE map's name (a separately-documented, different known limitation of `level import`, see
`import.md`'s "References between actors keep the source map's name" caveat). When the real editor
rebuilds under the trunk's own identity, it treats `20_Downtown` as an external package to resolve
against, fails, and silently drops the whole actor — not just the one property.

`AmbientSound0`'s failure looked identical (different property, `AmbientSound=Sound'Ambient.
Ambient.TechOffice1'`, but same "actor vanishes on rebuild" symptom) — worth checking whether that
one is the SAME non-editable-property problem or a genuinely missing Sound package; not fully
confirmed, listed here as a data point, not a verified duplicate cause.

## Verified: the fix already exists in principle, just not wired to import

`uedcli/normalize.py` already has exactly this rule, described as an **owner ruling, 2026-08-24**:
"exclude non-editable properties automatically" (comment at `normalize.py:60-68`):

```python
_RETAIN_NONEDIT: frozenset[str] = frozenset({"prepivot", "keypos", "keyrot"})

def is_authored_prop(name_casefold: str, *, editable: bool | None) -> bool:
    """... True iff it is `var()`-editable (`editable`, from `ClassInfo.editable`) or a
    special-editor exception (`PrePivot`, mover `KeyPos`/`KeyRot`) ..."""
```

`editable` comes from `uedcli/classdefaults.py`'s `ClassInfo.editable` (`CPF_EDIT = 0x1`, read off
the real compiled `.u` property flags — not a guess/heuristic).

**But this is only used by materialize's post-verify COMPARE**, not by the WRITE path. `uedcli/
mapimport.py::render_actor` (the function `level import` AND `level reimport` both call — confirmed
both `_level_import`/`_level_reimport` in `uedcli/cli/commands/level.py` route through the same
`mapimport.import_map` → `render_actor`) applies **zero** filtering: it walks every tagged property
the binary serialized and renders all of it unconditionally (`mapimport.py:453-462`). That's the
gap — the already-owner-approved rule for "what counts as authored" was never applied to what gets
WRITTEN into the trunk in the first place.

## Current KeyPos/KeyRot handling (owner's question, answered)

Today, `render_actor` has no special-casing for `KeyPos`/`KeyRot` at all — they get written into
the trunk only because EVERYTHING gets written unconditionally, same treatment as `MyMarker`. The
`_RETAIN_NONEDIT` exception set exists solely in `normalize.py`, consumed only by the compare path.
`uedcli/movers.py` (the `mover key` CLI command) is unrelated — it only writes `KeyPos`/`KeyRot`
when a user explicitly sets a keyframe via the CLI, and has no connection to import/reimport.

**Consequence for the fix**: applying `is_authored_prop`/`_RETAIN_NONEDIT` filtering to
`render_actor` must reuse the SAME exception set already in `normalize.py` (not reinvent it), or
`KeyPos`/`KeyRot`/`PrePivot` would regress — silently dropped from newly-imported movers, breaking
their keyframes on the very next import/reimport.

## Fix (implemented, merged)

`render_actor` now looks up each tag's `Prop` via `schema.props(fqcn)` (existing `ImportSchema`
method, backed by the real compiled `.u` packages), derives `editable`/`owner_casefold` from it the
same way `classdefaults.ClassInfo` does for the compare side, and calls
`normalize.is_authored_prop` to decide whether to render the property at all. Dropped names are
collected per actor and, when a `notes` list is threaded through (from `import_map`, which both
`level import` and `level reimport` already print to stderr), reported as one note per actor —
never silent. The stderr-vs-silent open question above is resolved: reported, not silent.

**Blast radius, confirmed and owner-approved (2026-09-02)**: every actor-to-actor object reference
property checked in this engine (`Base`, `Owner`, `Target`, `Weapon`, `previousPath`, `MyMarker`)
is non-editable, so this drops all of them on import/reimport going forward, not just `MyMarker`.
Flagged explicitly and confirmed as intended scope before merge — see this repo's commit history
for the change (`uedcli/mapimport.py`, `uedcli/tests/test_mapimport_import.py`,
`uedcli/tests/test_native_roundtrip.py`).

Known gap (not blocking, logged for later): the test-suite edit that adjusted for this change lost
direct coverage of `render_prop`'s generic object-reference rendering path with a real non-null
object ref decoded from native bytes (the substitute assertion goes through a different, hardcoded
`Brush=` code path instead). Worth a follow-up test using a genuinely `var()`-editable
`ObjectProperty` (e.g. `Engine.Actor.Skin`/`Mesh`/`Texture`) if one is ever needed.
