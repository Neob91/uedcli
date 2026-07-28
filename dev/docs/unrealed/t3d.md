# UnrealEd T3D — on-the-wire text format reference

> This doc covers the on-the-wire text format that `MAP EXPORT` writes
> and `MAP IMPORTADD` reads — a plain-text description of actors and their
> brush geometry. It does not describe the "T3D tree", the
> `{actors/, order, packages, name}` directory form used by the uedcli
> session store, documented in [`../architecture.md`](../architecture.md)
> ("Session store").
>
> Import/export behaviors that bite (grid-snap, demand-load, `Brush=`
> ordering, paste drift, …) are in [`quirks.md`](quirks.md) "T3D format",
> cross-linked below.

---

## Evidence and confidence markers

Confidence markers:
- ✅ = uedcli-used / live-verified
- 🔬 = live-probed this session
- 📖 = extracted from the binary string table (vocabulary real, semantics
  inferred)

Evidence files: `../spikes/2026-06-18-ucc-level-export.md` (UCC export
round-trip), `../spikes/2026-06-19-t3d-package-qualification.md` (texture
binding), `../spikes/2026-06-19-builder-world-geometry-parity.md` (vertex
faithfulness), `../spikes/2026-06-20-obj-dependencies-untextured-poly-correlation.md`
(texture demand-load), `../spikes/2026-06-21-class-qualification-discovery-and-roundtrip.md`
(class qualification). Real T3D examples in `../../uedcli/tests/fixtures/`.

---

## Block nesting ✅

A T3D file is a `Begin Map` / `End Map` wrapper containing zero or more
actor blocks. Each actor is:

```
Begin Map
Begin Actor Class=<Package.ClassName> Name=<ActorName>
    <actor-level properties…>
    Begin Brush Name=<ModelName>
       Begin PolyList
          Begin Polygon [Item=<item>] [Flags=<n>] [Link=<n>] [Texture=<ref>] [Pan U=<n> V=<n>]
             Origin   <X> <Y> <Z>
             Normal   <X> <Y> <Z>
             TextureU <X> <Y> <Z>
             TextureV <X> <Y> <Z>
             Vertex   <X> <Y> <Z>
             Vertex   <X> <Y> <Z>
             …
          End Polygon
          …
       End PolyList
    End Brush
    Brush=Model'MyLevel.<ModelName>'
    <remaining actor-level properties…>
    Name="<ActorName>"
End Actor
…
End Map
```

Nesting: `Map` → `Actor` → `Brush` → `PolyList` → `Polygon`. The `Brush` /
`PolyList` / `Polygon` blocks are present only for brush actors
(`Class=Brush` or a subclass). Point actors (lights, movers, pathnodes, …)
have only actor-level properties and no brush block.

Point-actor example (`tests/fixtures/add_light.t3d`):

```
Begin Actor Class=Light Name=SpikeProbeLight999
    Location=(X=12345.000000,Y=6789.000000,Z=4242.000000)
    LightBrightness=200
    Tag=SpikeProbe
    Name=SpikeProbeLight999
End Actor
```

---

## Property line forms ✅

### Scalar `Key=Value`

The most common form. The value is one of:
- A number: `LightBrightness=200`, `Location=(X=1.0,Y=2.0,Z=3.0)`
- A string literal: `Name="Brush938"`, `Group="club_entrance"`
- An unquoted identifier: `Tag=SpikeProbe`, `CsgOper=CSG_Subtract`
- A struct `(Field=Val,…)`: `Location=(X=6048.0,Y=5360.0,Z=-2240.0)`,
  `Rotation=(Yaw=-16384)`, `MainScale=(SheerAxis=SHEER_ZX)`
- An object reference `Class'Package.Name'`:
  `Level=LevelInfo'MyLevel.LevelInfo0'`, `Brush=Model'MyLevel.Model823'`
- A qualified texture ref `Texture'Package.Name'` (or bare `Package.Name`
  inline on `Begin Polygon … Texture=…`): `Texture=CoreTexMetal.Area51Wall_A`

### `Class=Package.ClassName` binds on import under a true collision; export is always bare 🔬

When two loaded packages define classes of the same name (a genuine collision — e.g. duplicating a
small `.u` under a second filename yields two distinct `UClass` objects `PkgA.Foo` and `PkgB.Foo`), a
`MAP IMPORTADD` actor's `Class=Package.ClassName` qualifier is the sole determinant of which package's
class it instantiates — per-actor, not one global pick, not load order. This reverses an earlier weak verdict that the package qualifier was "ignored" (that
test had no real collision, so it could only show a wrong qualifier wasn't *rejected*), and makes
`Class=` symmetric with `Texture=` package binding. But `MAP EXPORT` always writes the bare class name (`Class=Foo`, never
`Class=PkgB.Foo`), even when the class lives only in the non-default colliding package — so an actor's
class package is authored data uedcli owns and re-emits qualified at materialize; recovering it from a
live level needs `OBJ DEPENDENCIES PACKAGE=<level>` (prints per-actor refs fully qualified).
Collision-by-duplication works only for small dependency-light packages — duplicating a large one
(`Engine.u`) crashes the editor with `Palette …: Serial size mismatch`. (spike:
`../spikes/2026-06-19-class-package-collision.md`, live 2026-06-19)

### Indexed static-array form `Foo(N)=<value>` 🔬

UScript `var Foo[K]` array fields serialize as separate indexed lines, one
per element. The index `N` is zero-based:

```
AIProfile(0)=44831
KeyPos(1)=(Z=128.0)
KeyRot(1)=(Yaw=16384)
MultiSkins(2)=Texture'Skins.Wood'
```

The RHS is an ordinary scalar, struct `(…)`, or object ref — the same
value forms as the scalar `Key=Value` case. This form is general to every
actor class; the most common examples are `Mover` keyframe arrays
(`KeyPos(N)`/`KeyRot(N)`/`NumKeys`) and decoration skin arrays
(`MultiSkins(N)`). Confirmed in the substrate `Engine.u` name table
(2026-06-24 🔬).

> uedcli parses, emits, and normalizes these faithfully (since 2026-06-25,
> the mover-support work). `model._PROP` captures the optional `(N)` index
> as part of the property key (`KeyPos(1)`, `MultiSkins(2)`), `emit_actor`
> re-emits each indexed line verbatim via its catch-all property branch,
> and `normalize` keeps authored indexed props (only `AIProfile(N)` is
> stripped, by the computed-prefix rule). A parse → emit → parse round-trip
> is identical for all. The mover base-pose fields `BasePos`/`BaseRot` are
> editor-derived and stripped (see the authored-vs-computed taxonomy below).

---

## Winding defines the face, not `Normal` ✅

The exporter writes the polygon `Normal` field but the importer ignores it,
recomputing the normal from vertex winding order. The winding convention is
CCW-from-outside (counter-clockwise viewed from outside the solid). Wrong
winding produces an inverted or invalid solid that crashes `MAP REBUILD`
with a CSG GPF.

Evidence: verified from uedcli's own `builders.py` (faces wound CCW-from-
out pass the DEINTERSECTION parity suite live; a reversed face would
flip the solid). `spikes/2026-06-19-builder-world-geometry-parity.md`.

Vertex order is the ground truth. But `Normal` and the texture vectors
(`TextureU`/`TextureV`) behave differently across a round-trip, and the
difference is load-bearing for the materialize hash:

- `Normal` is not preserved — the engine recomputes it from winding. An
  authored normal and its re-export differ structurally, not just in
  precision (confirmed live 2026-07-14: a roof brush authored
  `Normal (0.707,0.707,0)` re-exported as the true slope `(0.541,0.541,0.643)`).
  So `normalize` drops the poly `Normal` from the compare view
  (`compare_view` → `_geometry_text`); winding (the kept vertices) is the
  authoritative face direction, so nothing authored is lost.
- `TextureU`/`TextureV` are preserved (stored FVectors, round-tripped
  through paste+rebuild — see `quirks.md` "texture vectors survive the paste
  path"). They carry real texture-alignment content, so the hash keeps them
  (only float32-quantized like every other coordinate). Do not drop them like
  `Normal`.

`Origin` is likewise a stored/preserved FVector (float32). uedcli's `emit.py`
writes all of these faithfully into the durable trunk; only the hash/compare
copy drops `Normal` and float32-quantizes coordinates.

---

## Fractional vertices are editor-native and CSG-safe ✅

UnrealEd writes and rebuilds non-integer vertex coordinates. The
`MAP EXPORT` of a real subtracted brush contains coordinates like
`Vertex -00479.999969,-00384.000031,+00192.000000`
(`tests/fixtures/brush_subtract.t3d`). The `.999969` part is floating-point
residue the editor writes without snapping.

Brushes need not have integer-grid vertices; semisolid and decorative
geometry routinely use fractional coordinates. uedcli stores all coordinates
as exact `decimal.Decimal` (not float) and only snaps a coordinate within
`CLEAN_EPS=0.001` of an integer to that integer (to kill editor noise like
`511.999969→512`). A genuine fraction (`32.5`, `70.71`) is preserved at 6
decimal places. See [`../architecture.md`](../architecture.md) "Coords" for
the full rationale.

---

## Partial struct/array property values: import is member-wise onto the class default ✅

A property value mentioning only some struct members (`RotationRate=(Yaw=1234)`) or only some
static-array elements (`InitialInventory(1)=…`) does not zero the rest on import — the unmentioned
members/elements keep the class default (import edits member-wise onto the default-initialized
object). Symmetrically, `MAP EXPORT` default-diffs member-precisely: it omits a whole property equal
to the class default and omits individual struct members equal to the default member (so the editor
re-exports a composed `Rotation=(Pitch=0,Yaw=8192,Roll=0)` as `(Yaw=8192)` — Rotation's default is
zero). Confirmed live 2026-07-18 with a partial-equal-to-default case (`DeusEx.Rat`
`RotationRate=(Pitch=4096)` → no export line at all, proving Yaw/Roll retained their non-zero
defaults): [`../spikes/2026-07-18-partial-value-import-semantics/findings.md`](../spikes/2026-07-18-partial-value-import-semantics/findings.md).
Consumed by `uedcli.propedit` (`STRUCT_FILL = "default"`): `actor prop get` fills unmentioned
members/elements from the offline-decoded class defaults, and `unset KEY.Member` reverts that member
to the class default (not zero).

Also consumed by the compare path — every property, as a typed value (`normalize.compare_view` →
`_actor_values` → `typedprops`, 2026-07-25). uedcli's producers write every property and struct
member; the editor writes only what differs from the class default, so the built map's re-export and
the trunk it was built from state the same values in different text. Rather than canonicalize the
text, the post-verify compares each actor's effective typed values: for every property, the stored
value if the actor states one, else the class default, decoded by the property's declared type. Two
actors are equal iff they would import to the same object.

Types and defaults are decoded offline from the game's own `.u`
(`uprops.resolve_class_properties` + `resolve_class_defaults`, compiled into `typedprops.Field`
trees by `classdefaults.ClassDefaults`, memoized per class over one shared package map). Case by case:

- a whole property equal to the class default is the same value as an omitted line
  (`StayOpenTime=4.0` against a `DeusEx.DeusExMover`'s default `4`; `SoundRadius=64` on an
  `Engine.AmbientSound`; `MoverGlideType=MV_GlideByTime`; `LightPeriod=32`;
  `LightEffect=LE_Spotlight` — all five measured in this repo's own trunks). A float compares
  numerically at float32, so `4.0` == `4`; an enum compares by ordinal, so a T3D enum name and a
  default decoded as a number agree;
- a struct expands member-wise against its class default — a member the text omits takes the
  corresponding default member, as the engine's importer does. `Rotation=(Yaw=8192)` ==
  `(Pitch=0,Yaw=8192,Roll=0)`; a `DeusEx.Rat`'s `RotationRate=(Yaw=1234)` means
  `(Pitch=4096,Yaw=1234,Roll=3072)`, its non-zero default members, not zero. This covers `Rotation`,
  `PrePivot`, `MainScale`/`PostScale`, `KeyPos(i)`/`KeyRot(i)` and any future struct, with no
  per-property rule;
- an omitted property with no class default takes the type's zero, from the schema — so an explicit
  `LightRadius=0` (ByteProperty) or `bHidden=False` on a class that does not default them equals an
  omitted line, while an explicit `Title="0"` (StrProperty, whose zero is `""`) stays different from
  an omitted one. Only the declared type can tell those apart: `parse_t3d` discards quoting, so the
  text never could — which is why the earlier text-based compare refused to touch zero scalars and
  aborted on them;
- an FRotator component is an `IntProperty` and compares verbatim (see the mod-65536 rule below);
- the editor's own `Tag=<bare class name>` default-stamp is dropped — but only for a class that does
  not itself default `Tag`, because `TNM.Trestkon` defaults `Tag='Player'` (5 TNM classes default
  it), where `Tag=Trestkon` is authored event-wiring content;
- a property with no declared type and no class default yields `typedprops.ABSENT`, which equals
  nothing. The compare never fabricates a zero to match an omission against — the no-fallback rule.

Two precision rules apply to both sides:

- every float compares at float32, the precision UnrealEd stores every float property and every
  coordinate at (an authored `43.552099` re-exports as `43.552097`);
- a `Location` axis passes through the trunk emit's sub-grid snap first (`emit.clean`,
  `CLEAN_EPS = 0.001`): the editor's export carries its own float32 noise (`Y=7215.999512`) where the
  trunk — snapped when the value was written — holds `Y=7216.000000`. Comparing without the snap
  fails 49 of 5125 actors on a real retail export (measured 2026-07-25, cold review). Brush geometry
  gets the same snap through `emit_brush`.

Before this, `level materialize` aborted on the H3 post-verify with nothing written for any yaw-only
actor, any of those five default-equal properties, and any explicitly-zero scalar. None of this
happens in `normalize_actor`, which feeds the durable trunk, the `MAP IMPORT` payload and
`actor show`: reducing there would rewrite authored data and make the trunk's bytes depend on which
packages are installed. The class schema + defaults are resolved before the editor container is
created, so an unresolvable class costs ~0.1 s and a clean exit 2 naming the actor, not a ~100 s build
then a failure — and there is no "assume zero" fallback (assuming zero is the bug).

Ingest keeps the absent-vs-zero distinction. Since the editor omits a `Location` axis equal to the
class default member, `Location=(X=100,Y=200)` on an `Engine.Camera` (default `(X=-500,Y=-300,Z=300)`)
means Z=300. `model.parse_t3d` is deliberately schema-free — it is also the trunk, stash, prefab and
generator-snippet reader, and a generator runs with no project context — so it keeps the 0-filled
numeric triple the geometry math needs and records the verbatim text in `Actor.location_text`, a
side-channel the compare seam expands member-wise. That text is self-invalidating: trusted only while
it still parses back to the current `location`, so any mutation falls back to "all three axes stated"
(correct, because every write path emits all three) and no mutation site has to clear it.

The identity hash (`normalize.canonical_level_hash`) is the opposite: pure, schema-free, no typing and
no defaults. It is the preview build-cache key, where folding two different levels together means
serving a map built from the other one.

Three properties of this rule, regression-pinned in `test_normalize.py` / `test_typedprops.py`:
- An FRotator component is compared as a verbatim integer, never reduced mod 65536 ✅ — UnrealEd
  stores and re-serializes the field verbatim, over-range values included, through import, `MAP
  SAVE`, the binary round-trip and the UCC re-export the post-verify reads (live-probed 2026-07-25 on
  point actors via `MAP IMPORTADD` and brushes via `EDIT PASTE`, three independent read-back legs:
  [`../spikes/2026-07-25-frotator-import-normalization/findings.md`](../spikes/2026-07-25-frotator-import-normalization/findings.md)).
  Negatives are not wrapped either (`-16384` stays `-16384`). Routing components through
  `rotation.parse_frotator`'s `% 65536` would rewrite 20,109 of the corpus's 23,960 `Rotation`
  components to zero — and since `-131072 % 65536 == 0`, an over-range rotator would then compare
  equal to an unrotated actor: a false pass, not just a spurious abort.
- Expansion is against the class default, never against zero. The two coincide for all but one class:
  `TNM.LavaSpitter` defaults `Rotation=(Pitch=16384,Yaw=0,Roll=0)` (verified offline over 1346 actor
  classes — the only one that defaults `Rotation` at all). Its `(Pitch=0)` export and an authored
  `(Pitch=0,Yaw=0,Roll=0)` are the same rotator, while "explicitly zero" and "no rotator" stay
  different levels (the second is pitched 90°) — the injectivity the compare must not lose.
- A zero test is unsound for other struct props too: 228 classes default `RotationRate` non-zero
  (`DeusEx.Rat` = `(Pitch=4096,Yaw=65530,Roll=3072)`), 17 default `PrePivot` non-zero, and
  `Engine.Camera` defaults `Location` non-zero. Member-wise expansion against each property's own
  default handles all uniformly.

Write-side rule: uedcli never omits an actor property to mean "zero". (A polygon sub-field is
different — see the note at the end of this section.) An omitted property re-imports as the class
default, so omitting one is only correct when it provably equals that class's default — which the
write paths (the trunk emit, the generators, `actor rotate`, `brush apply-transform`) have no resolver
to check. They write the value explicitly and let the compare-side typed expansion handle the
equivalence. Three omissions of this shape were live silent-corruption bugs until 2026-07-25 — each
built a wrong map that post-verify passed, because both compare sides shared the same mistake:

1. `actor rotate --to 0,0,0` / `--by` composing to identity dropped the `Rotation` prop, so a
   `TNM.LavaSpitter` came back pitched 90°. (Also `brush build --rotate 0,0,0`.)
2. `normalize_actor` cleared an all-zero `Location` into `canonical_actor_t3d` — i.e. into the
   trunk and the import payload — so an `Engine.Camera` (default `Location=(X=-500,Y=-300,Z=300)`)
   placed at the origin came back 655 uu away.
3. `normalize_actor` deleted a `Tag` equal to the actor's bare class name as the editor's
   default-stamp, so an authored `Tag=Trestkon` on a `TNM.Trestkon` (default `Tag='Player'`) was
   erased and the actor came back tagged `Player`, breaking its trigger/event wiring.

Two more were fixed on the same rule, neither ever observed (each needs a class default no placeable
DX class currently has): `brush apply-transform` (`transform.bake`) dropped the `PrePivot` when the
transform mapped it to zero — 17 classes default `PrePivot` non-zero — and dropped the `Rotation` it
had just baked into the vertices, which for `TNM.LavaSpitter` would have re-applied a 90° pitch to
already-flattened geometry. Both now write the explicit zero instead (`Rotation` only when the actor
carried one, so the bake never invents an orientation an actor did not have).

⚠ The rule is not yet total. Four write paths still omit against a hardcoded zero/constant:
`movers.set_key_pos`/`set_key_rot` (an all-zero `KeyPos(i)`/`KeyRot(i)`), `movers._set_numkeys`
(`NumKeys == 2`), `movers.canonicalize_mover` (`Rotation` when the base pose folds to identity —
that one runs on the map-ingest path, into the durable trunk), and the not-yet-wired
`native/materialize.py` (a zero `Location`). Measured harmless today — no `Engine.Mover` subclass
defaults `NumKeys`/`KeyPos`/`KeyRot`, and the only class defaulting `Rotation` is not a mover — and
filed on `board/inbox/` rather than changed here, because rewriting mover keyframe emission would
churn every mover trunk on disk for a currently-unreachable case.

A polygon sub-field is outside this rule and is omitted when zero. `Flags` and `Pan` inside a
`Begin Polygon` block are not actor properties and have no class default — an omitted one is always
zero (see "A poly sub-field has NO class default" below). uedcli omits both when zero. For `Pan` it
must: the editor never writes a zero one, so emitting it aborted every build (below). For `Flags` the
choice is free — the editor does sometimes write `Flags=0`
(`../../../uedcli/tests/fixtures/split7.t3d`), but a `Flags=0` line and no line both parse to
`flags == 0`, and both compare sides reach the comparison through uedcli's own emit, so whichever
spelling uedcli picks applies to both.

## Comments & unknown properties on import 🔬

The T3D import parser (`ULevelFactory::FactoryCreateText` → `ImportProperties` →
`Core.dll ParseLine`, all in UED22) is not the UnrealScript compiler tokenizer and does not share its
comment grammar. Verified 2026-07-18 by static disassembly and a live `MAP IMPORTADD` probe
([`../spikes/2026-07-18-t3d-comment-tolerance/findings.md`](../spikes/2026-07-18-t3d-comment-tolerance/findings.md)):

| Input on an actor-property line | Behavior on import | Mechanism |
|---|---|---|
| `//` line-comment | Stripped silently — everything after `//` is dropped, the line is still consumed; a line that is just `// …` imports as empty. No log warning. | `ParseLine` strips `//` when not inside a `"`-quoted value and `Exact==0` (which `ImportProperties` passes). A `//` inside quotes is preserved. |
| `/* … */` block-comment | Not a comment. `ParseLine` has no `*`/block handling. A standalone `/* … */` line survives, then is skipped by `ImportProperties` only because it has no `=`; a `/*` inside a value corrupts that value. | — |
| `;` semicolon | Not a comment. No `;` handling. A `; …` line with no `=` is skipped; a `; k=v` line trips the unknown-property warning. | — |
| unknown property (`Foo=1`, no such UProperty) | Warned + skipped, import continues (non-fatal): `Warning: <Class>: Unknown property in defaults: <line>`. A long (>64-char) string value is fine — no FName length limit on a value. | `FindProperty`→NULL → `Logf(NAME_Warning,…)` → next line. |
| `\|` (pipe) | end-of-line terminator (outside quotes) | `ParseLine` |

So `//` is the one robust, silent comment carrier. uedcli uses bare `//` lines as the on-the-wire form
of an actor's uedcli-side sidecars — `// uedcli-folder: <path>` for the single-path folder and
`// uedcli-labels: <l1,l2,…>` for the multi-valued label set (see `../architecture.md` "Folders" and
"Labels"): both ride `actor show` output and are stripped silently by the editor on paste/import while
uedcli's own parser reads them back into the respective sidecars (`--t3d-only` suppresses both).
Regression: `test_engine_facts.py` (`test_t3d_import_strips_double_slash_comments`) pins the
`//`-strip byte pattern in the committed `core.dll`. Do not carry data in `/* */` or `;` (they only
survive as no-`=` skipped lines), and never place the carrier inside a quoted value (there `//` is
preserved, not stripped).

## What T3D cannot carry ✅

T3D is a text snapshot of authored geometry and properties. It cannot
represent everything in a compiled `.dx` map file.

| What | Why it's absent | Recovery |
|---|---|---|
| `myLevel` embedded resources (textures/sounds) | binary blobs, not text-representable | use a package file + qualified `Texture=` ref |
| Computed BSP (nodes/surfs/polyverts) | built by `MAP REBUILD`, not authored | rebuild with `MAP REBUILD` |
| Lightmaps | built by `LIGHT APPLY`, not authored | rebuild with `LIGHT APPLY` |
| Pathnode reachspecs (`ReachSpecs`, `Paths`/`upstreamPaths` etc.) | built by `PATHS BUILD` (not `PATHS DEFINE`, which only spawns markers — see `commands.md`), not authored | rebuild with `PATHS BUILD` |

To preserve compiled state (lighting, BSP, pathing), edit in place and use
`MAP SAVE` — never reconstruct a `.dx` from T3D alone unless you plan to
rebuild all of the above. uedcli's `level apply` always triggers a full
re-import + `MAP REBUILD` + `LIGHT APPLY`, so rebuilding is automatic; but
T3D export of a built map loses these artifacts.

---

## Authored-vs-computed field taxonomy ✅

Not all fields in a `MAP EXPORT` are authored content. Some are computed by the editor at import,
rebuild, or load time and must be ignored when diffing two T3D snapshots (otherwise every no-op export
looks like a change).

The canonical list is `normalize.COMPUTED_PROPS` (exact-match) and `normalize._COMPUTED_PREFIXES`
(prefix-match, e.g. `AIProfile`); the code is the source of truth, not this list. Grouped by when and
how the editor/engine produces them:

- Engine-time fields set by the engine at load: `Level`, `NavigationPointList`, `PawnList`,
  `nextNavigationPoint`, `prevNavigationPoint`, `bSelected`.
- Rebuild-time fields derived during `MAP REBUILD`: `Region`, `TimeSeconds`, `Summary`.
- Load-time / import-time fields recomputed on import: `OldLocation` (the actor's prior location, a
  transient editor field), `AIProfile(N)` (stripped by prefix — computed AI navigation weight).
- Mover base-pose fields `BasePos`/`BaseRot`: the editor derives the mover's home pose from
  `Location`/`Rotation` at import and writes these into the re-export. uedcli-authored movers never
  emit them; a re-export adds them, so they must canonicalize away (confirmed by spike test E,
  2026-06-25).
- Mover engine-stamped sentinels `SavedPos`/`SavedRot`: pure engine runtime state, and the only
  fields in this taxonomy whose value is a fixed magic constant rather than derived from the level —
  `SavedPos=(X=-12345.000000,Y=-12345.000000,Z=-12345.000000)` and
  `SavedRot=(Pitch=123,Yaw=456,Roll=789)`. `AMover::PostLoad()` writes exactly those two values into
  every Mover object it loads, unconditionally — no guard, no test of what the file stored — so an
  authored value can never survive a round trip, and any mover through a package load carries the
  sentinel while a uedcli-authored one (which omits both) does not. Without the strip, every mover map
  fails the H3 post-verify. Disassembled out of both engines and corroborated by the corpus (487
  occurrences of each, exactly one distinct value each; every retail map holding a mover — 81 of the
  130 in `DX/Maps` — carries it once per mover):
  [spike 2026-07-25](../spikes/2026-07-25-mover-savedpos-savedrot-engine-stamped/findings.md). The
  same `PostLoad` also renumbers the mover brush's polygon `Link` to `0..N-1`; both writes come from
  that one function, so their co-occurrence fingerprints "this mover has been through a package load",
  distinguishing a mover the editor loaded from one created in-session (which carries neither).

Two mover fields are deliberately not listed. `OldRot` — only `OldLocation` is spike-confirmed.
`SavedTrigger` — `AMover::PostLoad` does not touch it and it appears zero times in the whole committed
export corpus, so it causes no mismatch. Each is added only if a re-export is actually seen carrying
it, never on faith.

Additional normalization rules (not simple field exclusion). All three below happen on the throwaway
compare view only (`normalize._actor_values` via `compare_view`) — never in `normalize_actor`, which
feeds the durable trunk and the `MAP IMPORT` payload; see "Partial struct/array property values"
above:
- A `Location` equal to the class default ≡ no `Location` line: the editor omits the line when the
  value matches the default, a freshly authored actor carries an explicit value, and both must resolve
  to the same typed value (an omitted axis resolves to that axis's default member). The default is
  `(0,0,0)` for every class except `Engine.Camera` — testing against zero instead of the class default
  silently built a camera 655 uu from where it was authored, until 2026-07-25.
- Polygon `Link=N` is a computed BSP cross-reference emitted by the exporter; `emit_actor` never
  writes it, so it is implicitly excluded on re-emit.
- `Tag=<ClassName>` is not in `COMPUTED_PROPS`. The editor stamps an unset `Tag` to the bare class
  name on import, but `Tag` is also real authored content (`add_light.t3d` carries `Tag=SpikeProbe`).
  Only the editor's own default stamp is noise, so only that is dropped, only at compare time, and
  only where the class does not itself default `Tag` (`TNM.Trestkon` defaults `Tag='Player'`, so there
  a `Tag=Trestkon` is authored content). Stripping it on the write side silently erased such a tag
  until 2026-07-25.

For the full rationale see `../architecture.md` "Coords" and
`uedcli/normalize.py`.

---

## Polygon sub-fields reference ✅

Each `Begin Polygon … End Polygon` block carries:

| Field | Required | Notes |
|---|---|---|
| `Item=<name>` | no | per-face semantic label (`Base`, `Step`, `Rise`, `Side`, `OUTSIDE`); used by "Select → Matching → Item Name". Survives round-trip. |
| `Flags=<n>` | no | `PolyFlags` bitmask: `NotSolid=8`, `Transparent=4`, `SemiSolid=32`. Omitted = 0. |
| `Link=<n>` | no | computed BSP surface link; never authored, ignored on import per the taxonomy above |
| `Texture=<ref>` | no | qualified `Package.Name` or bare name; see [`quirks.md`](quirks.md) for binding gotchas |
| `Pan U=<n> V=<n>` | no | texture pan offset in texture-space units. Omitted = 0, and the exporter writes the line only when a component is non-zero — see below |
| `Origin X Y Z` | yes (brush) | a point on the polygon plane; used for texture alignment |
| `Normal X Y Z` | yes (brush) | face normal (ignored by importer — winding is authoritative) |
| `TextureU X Y Z` | yes (brush) | texture U-axis in world space |
| `TextureV X Y Z` | yes (brush) | texture V-axis in world space |
| `Vertex X Y Z` | ≥3 per poly | world-space vertices in CCW-from-outside order |

### A poly sub-field has NO class default — `Pan U=0 V=0` ≡ no `Pan` line ✅

The observed fact ✅: `MAP EXPORT` writes `Pan` only when a component is non-zero, and never writes
`Pan U=0 V=0`; the editor accepts an explicitly-zero `Pan` on import and re-serializes it as absent,
so the two spellings are one value to it. Evidence, all re-checkable:

- The export corpus. Not one `Pan U=0 V=0` occurs in any real editor export held in this repo, while
  non-zero pans are common — of the two genuine `MAP EXPORT` goldens,
  `../../../uedcli/tests/fixtures/level_small.t3d` carries `Pan U=0 V=384` (×12) and `Pan U=16 V=8`
  (×36), and `brush_subtract.t3d` carries `Pan U=0 V=384` (×2). So a half-zero pan is written, and
  only the all-zero pair is dropped. Pinned by
  `test_engine_facts.test_editor_export_never_writes_an_all_zero_poly_pan`.
- One live `level materialize` run on the `basement` level, recorded twice before anyone understood
  it: it imported a trunk stating `Pan U=0 V=0` and got back a re-export with no `Pan` line on that
  face, which the line-oriented diagnostic reported as a `Vertex` opposite a `Pan`
  (`actor 'RoomA_jwvaq0' differs in GEOMETRY at line 7`). Filed as a suspected post-verify false
  positive in both
  [`../spikes/headless-materialize/findings.md`](../spikes/headless-materialize/findings.md) §11 and
  [`../spikes/levelbuild-friction/agent-reports.md`](../spikes/levelbuild-friction/agent-reports.md)
  ("post-verify diff prints two sides that look line-shifted") — two reports of the one run.
- A minimal repro on a plain cube, live 2026-07-26 (independent second run): `brush build
  cube | actor add -`, then `brush poly find --facing +Z | brush poly align --floor -`, then
  `level materialize` → exit 2, `differs in GEOMETRY at line 43`,
  `built: Vertex … / intended: Pan U=0 V=0`.

The mechanism below is inferred, not verified. The sub-fields in a `Begin Polygon` block are not
UnrealScript properties on an actor class — they are fields of the brush model's `FPoly` records, so
there is no class whose defaults could back them and an omitted one can only take the field's own
fixed zero. This is read off the format, not extracted from the binary, and does not predict what the
exporter writes: the editor emits `Flags=0` on occasion (`../../../uedcli/tests/fixtures/split7.t3d`,
all 7 polys) while never emitting a zero `Pan`, so per-field export behavior must be measured, not
derived.

Consequence for uedcli. The post-verify compares each actor's brush as one block of text
(`normalize._geometry_text` renders it, `verify` compares the whole string; the line-by-line walk in
`verify._first_diff` only builds the human diagnostic afterwards). So a redundant line is a difference
wherever it sits, reported by pairing up line numbers, so it surfaces as a bogus vertex mismatch
rather than "the pan differs". Until 2026-07-26 `emit_polygon` wrote `Pan U=0 V=0` whenever the model
held a zero pan, which `brush poly align` produces on any face that had no prior pan (i.e. every face
of a freshly built brush). `level materialize` then aborted with `post-verify mismatch: … differs in
GEOMETRY at line 43` and wrote nothing, making the whole `brush poly find … | brush poly align …` →
build workflow unusable. `emit_polygon` now omits a zero `Pan` exactly as it already omitted a zero
`Flags`; rationale and rejected alternatives in [`../rationale/emit.md`](../rationale/emit.md).

### The UV convention (`U = (Vertex − Origin)·TextureU + PanU`) ✅

A vertex's texture coordinate is computed from the surface's stored frame as:

> U = (Vertex − Origin) · TextureU + PanU   (and V the same with `TextureV`/`PanV`)

so `Origin` is the world point where `(U,V) = (PanU, PanV)`, and the texel scale is carried in the
magnitude of `TextureU`/`TextureV` — a unit `TextureU` gives 1 texel per world unit; halving the
density means halving `|TextureU|`. There is no separate `UScale` field on the poly (the classic
Unreal-source `…·TextureU/|TextureU|²·UScale` form is the same mapping with the scale split out; T3D
folds it into the magnitude). The stored `Origin`/`TextureU`/`TextureV` are in the brush's local
frame; the renderer maps them to world via `base_w = Location + R·(Origin − PrePivot)`,
`axes_w = R·axes` — so two faces on differently-placed/rotated brushes are seamlessly aligned only
when they share the same world frame, not the same stored fields. ✅ uedcli-used: the convention
`brush poly align` computes against and `render.rs`/`preview_native._world_uv_frame` render with;
pinned by `test_polyalign.test_engine_fact_uv_formula_is_base_relative_plus_pan`. (Uses the authored
`Origin` as `uv_base` and adds the surface `Pan` — evidence `render.rs:159-165`; do not anchor it to
`light.rs`, whose base is the BSP surf point and whose pan is the lightmap-grid pan, a different
quantity.)

---

## See also

- [`quirks.md`](quirks.md) "T3D format" — the gotchas: `MAP IMPORTADD`
  grid-snap, `Group` not required on a qualified `Texture=`, qualified
  `Texture=` does not auto-demand-load its package, no coplanar auto-merge.
  `EDIT PASTE` +32uu drift and `Brush=`-after-the-block emit ordering are
  in [`quirks.md`](quirks.md) "How brushes enter the level".
- [`../architecture.md`](../architecture.md) — the session store's T3D tree
  format (different thing), exact `Decimal` coord storage, `emit.clean`.
- [`uedcli/normalize.py`](../../../uedcli/normalize.py) — `COMPUTED_PROPS`,
  `normalize_actor`, `canonicalize_self_refs`.
