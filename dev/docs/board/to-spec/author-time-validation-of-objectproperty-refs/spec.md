# Spec — author-time validation of ObjectProperty refs

Status: decisions recorded (2026-08-04); ready for spec review.

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

### The ref set to validate (decided — see Decisions)

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
`ObjectResolver` filtered to `Texture`), so the two do not diverge. Existence is confirmed by object
**NAME** on the path (see Decisions: a class-token gate would false-reject a base-class ref that
resolves to a subclass export, e.g. `Texture'X'` → a `FireTexture`); the ref's class token routes
null and serves as a non-rejecting hint, never a hard gate.

Wire it into `validate_ingest_actors` after the class/texture passes: for each actor, for each
OBJECT-typed stated property, parse the ref and call `resolver.exists`. All-or-nothing, collecting
every miss (batch rule, `conventions.md`).

### What is skipped, not failed

- **Null / unset** — `None`, `""`, `Sound'None'` → skip (an unset ref is legitimate).
- **`MyLevel.*` / embedded refs** — not offline-checkable and not materializable as external refs
  (`surface.parse_texture_ref` already rejects `MyLevel.*` for textures, `surface.py:103`); skip with
  no error, since some sound/mesh refs into the level's own embedded resources are legitimate. (See
  Decisions (Disposition) for bare/unqualified refs.)
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

## Decisions (2026-08-04)

- **Ref set** — schema-driven: validate every property whose `field.kind == OBJECT`. No curated
  per-substrate list.
- **Coverage — BOTH loci.** (1) the `validate_ingest_actors` gate (covers `actor add`/`duplicate`,
  `actor build`/`brush build --prop`, `stash`/`prefab apply`, `level import`); AND (2) **`actor prop
  set`**, which BYPASSES that gate today (`actor/prop.py` → `propedit.plan_edit`) yet is the primary
  way these props are authored — so leaving it out would defeat the "author time, not materialize"
  premise. Add an inline spot-check there on the `brush poly set --texture` precedent
  (`brush/poly.py:42`): the schema is already resolved to type the leaf, so existence adds only a
  content-package scan, injected via a `resources` seam so tests can mock it.
- **Match strategy** — confirm existence by object **NAME**, not exact class-token equality (a
  base-class ref onto a subclass export must not false-reject). Gated on a small spike: how often do
  retail levels spell an object ref with a base-class token onto a subclassed export? (`spike:
  object-ref class-token vs export-class in retail levels`.)
- **Disposition** — mirror `TextureResolver`: a bare unqualified name = tolerant any-package
  existence; a qualified-but-absent ref = hard exit 2 naming it; `None`/`""`/`MyLevel.*` always
  skipped.

Note on sequencing: this item is **not** blocked on the unified-asset-catalog enumeration layer —
existence needs only `pkg.class_of_export`. If the owner prefers to build `ObjectResolver` as the
catalog's enumeration primitive so the two share one implementation, that is a coordination call, not
a dependency (recommend building it here and having the catalog consume it later).
