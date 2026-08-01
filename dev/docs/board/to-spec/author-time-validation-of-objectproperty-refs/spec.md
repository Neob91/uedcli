# Spec — author-time validation of ObjectProperty refs

Status: DRAFT for owner review. Blocking forks in `questions/`.

## Goal

Catch a typo'd object-valued property ref (`AmbientSound=Sound'X.Y'`, `Song=Music'X.Y'`,
`OpeningSound`, a mesh ref, …) at author time, the way class and texture refs are already caught, so
a broken ref exits 2 naming it instead of exiting 0 and shipping a silently-broken level.

## Current state

- The shared author-time gate is `ingest.validate_ingest_actors` (`uedcli/cli/ingest.py:42`), run by
  every T3D ingest/emit seam (actor add, stash capture/apply/promote, prefab apply, the generators).
  It today validates exactly two ref kinds:
  - **class** — `ClassIndex.qualify_and_validate` (`classindex.py:317`): bare→FQCN + existence;
  - **texture** — per brush poly, `utexture.TextureResolver.exists(ref)` (`ingest.py:62`,
    `utexture.py:886`).
- **Object-valued actor properties are not checked at all.** They live in `a.props` as text like
  `AmbientSound=Sound'AmbientSounds.Machine1'`. A typo exits 0.
- The schema already knows which props are object-typed: `classdefaults` maps `ObjectProperty` and
  `ClassProperty` to `typedprops.OBJECT` (`classdefaults.py:42`), and `ClassInfo.field(name)`
  (`classdefaults.py:68`) returns that kind. So "which props are refs" is answerable offline from the
  class schema, per-actor.
- **No generic object enumerator exists yet** — only `TextureResolver` (Texture-classed exports) and
  `ClassIndex` (classes). There is NO Sound/Music/Mesh resolver. BUT the primitive that makes one
  trivial already exists: `pkg.class_of_export(i)` (used by `utexture.textures`,
  `utexture.py:339`) returns any export's class name. `TextureResolver._exists_uncached`
  (`utexture.py:908`) is the exact scan pattern, specialised to `class == "Texture"`; generalising it
  to any class token is a few lines.
- The overview points at the unified-asset-catalog ENUMERATION layer (spec §8) as the reference-set
  source. That layer is unbuilt (only the legacy `texture_catalog.py` exists). Finding: existence
  does **not** need the catalog — it needs only `class_of_export` scanning, already present.

## Design

### The ref set to validate (fork — `questions/schema-driven-vs-curated.md`)

An object ref carries its kind in its class token: `Sound'A.B'`, `Music'A.B'`, `StaticMesh'A.B'`,
`Texture'A.B'`. Two ways to decide which property values to check:

- **Schema-driven (recommended).** For each actor, resolve its `ClassInfo` and validate every
  property whose `field.kind == OBJECT`. Principled, substrate-agnostic ("the tool does not infer"),
  and future-proof (a new object prop is covered for free). Cost: the ingest gate gains a per-class
  schema resolve — the same cost the class/texture gate and the mover gate already accept for a
  resolvable path. `ClassDefaults` memoises per class, so it is per-class not per-actor.
- **Curated name list.** Hardcode `AmbientSound`, `Song`, `OpeningSound`, `Mesh`, … Cheaper, but it
  is exactly the per-substrate hardcoded knowledge `conventions.md` rejects, and it silently misses
  any prop not on the list.

Recommendation: **schema-driven**.

### The resolver

Add a generic `ObjectResolver` (new, model-side, over the composed package files — same input as
`TextureResolver`), with `exists(ref, *, expect_class=None) -> bool` scanning exports via
`pkg.class_of_export`. It subsumes texture existence (a `TextureResolver` becomes
`ObjectResolver` filtered to `Texture`), so the two do not diverge. Existence keys off the **ref's
own class token** (`Sound'A.B'` → a `Sound`-classed export named `A.B` on the path), which also lets
the check confirm the ref's declared kind, not just that *something* of that name exists.

Wire it into `validate_ingest_actors` after the class/texture passes: for each actor, for each
OBJECT-typed stated property, parse the ref and call `resolver.exists`. All-or-nothing, collecting
every miss (batch rule, `conventions.md`).

### What is skipped, not failed

- **Null / unset** — `None`, `""`, `Sound'None'` → skip (an unset ref is legitimate).
- **`MyLevel.*` / embedded refs** — not offline-checkable and not materializable as external refs
  (`surface.parse_texture_ref` already rejects `MyLevel.*` for textures, `surface.py:103`); skip with
  no error, since some sound/mesh refs into the level's own embedded resources are legitimate. (Fork
  `questions/unresolvable-ref-disposition.md` covers whether a bare/unqualified or unresolvable-kind
  ref is an error or a skip.)
- **Structural self-refs** (`Brush=Model'MyLevel.…'`, `Level=…`) — these are computed/self fields,
  not authored object refs; the OBJECT-field filter plus the `MyLevel` skip already excludes them.

## Edge cases & errors

- Unknown ref → collected; the batch exits 2 naming every missing ref (mirrors the texture message,
  `ingest.py:63`), never a traceback.
- Class will not resolve (no schema for the actor) → the class pass already errors first
  (`qualify_and_validate`), so the object pass never runs on an unresolved class.
- Corrupt package on the path → `ObjectResolver` swallows per-package parse errors like
  `TextureResolver.exists` does (`utexture.py:898`), contributing nothing rather than false-rejecting.
- Empty package path → the existing `package_path_or_exit` canonical error (`resources.py:250`).
- A ref to a class kind with no exports of that name anywhere → miss → exit 2 (correct: that is the
  typo case).

## Tests

- A typo'd `AmbientSound` ref exits 2 naming it; a correct one passes (offline, patched resolver).
- `Song`/`OpeningSound`/a mesh ref covered the same way.
- Null / `MyLevel.*` refs pass without error.
- `ObjectResolver.exists` matches on class token (a `Sound` named `X` does not satisfy a `Music'X'`
  ref).
- Batch reports ALL misses across several actors, not just the first.
- Regression: a corrupt package on the path does not crash the gate or false-reject a good ref.

## Open questions

- `questions/schema-driven-vs-curated.md` — validate every schema-OBJECT-typed prop, or a curated
  name list.
- `questions/unresolvable-ref-disposition.md` — a bare/unqualified object ref, or a ref whose kind
  cannot be checked: exit 2 (house rule) or skip.

Note on sequencing: this item is **not** blocked on the unified-asset-catalog enumeration layer —
existence needs only `pkg.class_of_export`. If the owner prefers to build `ObjectResolver` as the
catalog's enumeration primitive so the two share one implementation, that is a coordination call, not
a dependency (recommend building it here and having the catalog consume it later).
