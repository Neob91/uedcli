# `level import` — native (editor-less) `.dx`/`.unr` → T3D-tree ingestion

**Status: DESIGN v3 (2026-07-24), after two review rounds** — spec written, not yet built. Ephemeral:
once built, fold the mechanism into `architecture.md`, `unrealed/t3d.md`, and `docs/usage.md`, then
this file may be deleted.
**Decisions ledger:** `decisions.md` 2026-07-24 16:48 / 16:59 / 17:19 / 18:49 UTC — the durable record.
**Board:** `to-plan.md` (the actor-order `[spike]` at §9 gates BUILD, not planning).
**Code refs symbol-anchored** (line numbers drift). v3 folds in review round 2 (two cold reviewers)
which found the decode was *under*-credited (a production value-decoder already exists) and the struct
reconciliation mis-placed; Andrzej then locked **decode-time UCC-exact rendering** + **strict
validation** (18:49 UTC), which is simpler and safer than v2.

---

## 1. Motivation

Materialize is one-way: T3D trunk → `.dx`/`.unr`. `level import` is the inverse — it decodes a compiled
map file back into a **queryable, diffable, remixable** T3D trunk (or stash): study a retail mission
with `actor find`/`brush poly list`, extract prefabs, diff native-materialize output against real
content. **Native / editor-less**: no live UnrealEd, no UCC in the shipping path (UCC is a test oracle
only, §7).

## 2. What exists vs what is new (corrected in v3)

The *value decode* is largely REUSE — round-2 review found a production decoder the earlier drafts
missed. Genuinely-new work is narrower than v2 claimed:

| Piece | Real status |
|-------|-------------|
| Container parse + ref qualification | ✅ production — `upackage.load_package`, `Package.object_path`/`object_class_name`/`name_of_ref` |
| Tagged-property list reader (raw tags) | ✅ production — `upackage.read_property_tags` → `PropertyTag` |
| **Per-property VALUE decode → T3D text** (bool/byte-enum/int/float/object-ref/name/str/**arbitrary schema-driven struct**) | ✅ **production, REUSE** — `uprops.render_default_tag` + `_decode_struct_bin`(`_at`); an actor-body tag has the identical wire form to a class-defaults tag. NOT new. |
| Skip the actor `StateFrame` before the property list | 🔬 **characterized + retail-validated** — Spike 07 `07-native-actor-bodies.md` (`native_dx_actors.py` reader: `00_Intro.dx`, 3736 objects, 0 errors). Promote the harness. |
| **UCC-exact rendering** (member-strip native structs vs class defaults; 6dp `%f` floats) | ⚠️ **NEW, small, in `mapimport`** — reuse `uprops.resolve_class_defaults` for the per-prop default; §5.2c. Decision 18:49. |
| **Dynamic-array (`PT_ARRAY`) decode** | ❌ **NEW (the real new decode)** — needs schema plumbing: the inner element KIND is not exposed today (`Prop.type_name` is the Inner UProperty's *name*, not its kind). §5.2d. |
| Brush private `UModel`→`Polys`(`field_0x54`)→`UPolys`→`FPoly` decode (incl. poly `Item`) | 🔬 **spike harness** — `.../harness/upolys_decode.py`; **rewire** its `utexture_decode` imports onto `upackage` on promotion. §5.3 |
| World BSP `UModel` body parse | ✅ production `native/umodel.parse_model_body` — validate it also reaches EOF on a brush's PRIVATE model (§5.3). |
| Actor enumeration / FQCN / bare-vs-FQCN | ✅ production — `classindex.ClassIndex.descends_from(fqcn, ENGINE_ACTOR)`; FQCN = `object_path(exports[i]["cls"])`. |
| **Ingest gate** (bare→FQCN qualify + existence-validate) | ✅ production — `ClassIndex.qualify_and_validate` (run it — strict, decision 18:49; §5.4). |
| T3D text → model; model → tree; new box | ✅ production — `model.parse_t3d`, `emit`, `t3dtree`, `trunk.write_level`+`append_rank` (as `_level_create`), stash `write_stash`. |
| Acceptance-compare machinery | ✅ production — `canonical_level_hash`+`normalize`+`level_order` (the reusable core of `verify.verify_dx_matches`); `store_export.export_dx_level` is **container-bound** — oracle for INTEGRATION only (§7). |

**Genuinely new:** `mapimport.py` (orchestration + UCC-exact render + dynamic arrays), the StateFrame
skip + FPoly/UPolys decoders promoted from harnesses, the `Prop` array-inner-kind plumbing, the
`level import` verb + create-mode resolver. The value/struct decode, the write seams, and the compare
core are reused.

## 3. Locked decisions

1. **Destination `--tree level|stash/NAME`** (prefab deferred). (16:48)
2. **Fidelity = equivalence to `MAP EXPORT` through the canonical lens** (enum names + geometry must
   match; ordering/computed-fields inconsequential). (16:48)
3. **Native decode; UCC only as the test oracle.** (16:48)
4. **All actors imported verbatim.** (16:48)
5. **UCC-text fidelity lives at DECODE time** (18:49, supersedes the 17:19 compare-time choice):
   `mapimport` renders each prop as `MAP EXPORT` would — native structs **member-stripped against the
   class default** (via `resolve_class_defaults`; the default may be non-zero, e.g. `Scale=(1,1,1)`),
   scalar floats in **6dp `%f`**. So the trunk matches every other trunk (stripped/6dp, clean diffs),
   the schema-free `normalize`/`canonical_level_hash` hash path is **never touched** (contained safety
   blast radius — that path backs materialize's H3 verify), and the offline text compare "just works."
   The materialize round-trip test catches any wrongly-stripped member (data-loss guard).
6. **Strict validation** (18:49): import runs `ClassIndex.qualify_and_validate` before the trunk write
   — qualify bare→FQCN + existence-validate classes/textures; an unresolved package fails import exit 2
   (retail maps require the game's base packages on the composed path — true for OG DX). A lenient
   "import anyway, keep unresolved refs" mode is a deferred follow-up (inbox).

## 4. Verb surface

```
level import MAPFILE --tree KIND/NAME [--overwrite]
```

- **`MAPFILE`** (positional, cwd-relative) — `.dx`/`.unr`. Bad magic/unreadable → exit 2 naming it
  (`upackage.SchemaError` caught at dispatch).
- **`--tree KIND/NAME`** — DESTINATION; KIND ∈ `{level, stash}`. Import **creates** the box via a
  create-mode resolver `_resolve_import_dest` (NOT `_resolve_level_source`, which errors on a
  non-existent box). `prefab/…` → exit 2.
- **`--overwrite`** — refuse to overwrite an existing box (exit 2) unless given; the overwrite check
  runs **before** any load.
- **Project-dependent** — needs the composed `.u` path for `ClassIndex`, `uprops` schema/defaults, and
  qualification. No project → exit 2.
- **Output:** destination + actor count → stderr; imported actor names → stdout (producer convention).

## 5. Decode pipeline (`uedctl/mapimport.py`) → T3D text, then `parse_t3d`

`import_map(pkg, index, schema) -> str` returns a `Begin Map … End Map` string that `model.parse_t3d`
ingests (the tested inverse of `emit_actor` — gets `Location`/`MainScale`/`PostScale`/`Brush`-ref and
carrier routing right; decoding straight into `model.Actor` would drop location/scale). `schema` = the
`classindex` per-class inherited property schema + `uprops` class-default resolver, built/cached for
every actor class in the map.

### 5.1 Enumerate actors, in authoritative order
Export is an actor iff `index.descends_from(object_path(exports[i]["cls"]), ENGINE_ACTOR)` (the CLASS
ref's path, not the actor's; `object_class_name` gives only the bare name). Emit **bare** class names
(the ingest gate re-qualifies, §5.4). **Order** must match the oracle's (CSG precedence + the
order-folded hash), and the order source is **RESOLVED** (spike 2026-07-24-level-import-order — §9):
the `Engine.Level` object's Actors array, in the Level body's native tail AFTER its `None`-terminated
property list, serialized as **`[i32 Num][i32 Max]`** (raw INT32, NOT a compact count; `Num==Max` on
disk) then `Num` signed-compact object refs, **ref `0` == a null/deleted slot** (drop them; 29–329 per
retail map). `Actors[0]` is always `LevelInfo0` (UE1 invariant — proves alignment). Raw export-table
order does **NOT** equal this (verified 3 retail maps), so import MUST decode the Actors array — no
shortcut. Layout confirmed by the native WRITE side `native.level_write.write_level_body` and pinned by
`test_engine_facts.test_level_actors_array_is_int_num_max_then_compact_refs`. `batchexport` iterates
`Level->Actors` in this order (skipping nulls), so array-order == oracle-order (end-to-end confirmed by
§7 Slice-5 integration). Capture order **identically on both compare sides** (§7).

### 5.2 Per actor: locate + decode the property list
- **(a) Skip the `StateFrame`.** `RF_HasStack` (`0x02000000`, `exports[i]["flags"]`) actors serialize a
  StateFrame (Node ci, StateNode ci, ProbeMask u64, LatentAction u32, Offset ci **iff Node≠0**) before
  the tags — invert `native/actor_write.state_frame`; **evidence + a validated reader:** Spike 07
  (`07-native-actor-bodies.md`, `native_dx_actors.py`). Note: non-point classes carry class-specific
  trailing bytes AFTER the property list — harmless (`read_property_tags` stops at `None`), but do NOT
  assume end-of-props == end-of-body.
- **(b) Decode each tag value → T3D text: REUSE `uprops.render_default_tag`.** It already handles
  bool/byte(enum-named)/int/float/object-ref(`Class'Pkg.Name'`)/name/str and **arbitrary
  schema-driven structs** (`_decode_struct_bin`) from `PropertyTag.raw`. **All UE1 structs serialize
  POSITIONALLY (`SerializeBin`), members in schema order, no tags, nested positionally** (evidence
  `unrealed/class-schema.md`; `read_property_tags` is never called recursively). There is **NO**
  native-vs-script-struct branch — that was a UE2/3 concept, deleted in v3.
- **(c) Render UCC-exact (decision 18:49).** Two deltas from `render_default_tag`'s default output:
  (i) **member-strip native structs** — drop each struct member equal to the class default's member
  (from `resolve_class_defaults(fqcn)`, member-wise; the default may be non-zero — `Scale=(1,1,1)`), so
  `Rotation=(Yaw=8192)` not `(Pitch=0,Yaw=8192,Roll=0)`; (ii) **6dp `%f` floats** (UCC writes
  `X=12345.000000`; `format_float`'s int-trim would mismatch). Absent-from-defaults ⇒ the zero/default
  struct. Both compare sides use the SAME requalified FQCN for the default lookup.
- **(d) Dynamic arrays (`PT_ARRAY`) — the real new decode.** Needs NEW schema plumbing: resolve the
  `ArrayProperty`'s `Inner` UProperty ref → its KIND/element type (not exposed today — `Prop.type_name`
  is the Inner's *name*), expose it on `Prop`; then decode `count + N× inner-SerializeItem`. Static
  arrays already arrive as separate `array_index` tags → `Foo(N)=…`. No encode mirror ⇒ NO
  `decode∘encode` pin (§7) — covered by a dedicated retail golden containing a populated array.

### 5.3 Per BRUSH actor: private shape
`Brush=Model'…'` → private `UModel`; its `Polys` ref = `parse_model_body(...).field_0x54`
(`assemble.py`) → `UPolys` (`propNone + INT Num + INT Max + Num×FPoly`). Promote `upolys_decode.py`
(**rewire** its `utexture_decode` import onto `upackage.read_compact_index`/`Package`) →
`decode_upolys -> list[FPoly]`; map each to a `model.Poly` **including `Item`** (`pkg.names[item_index]`,
0→none — `write_fpoly` serializes it; dropping it mismatches every named face). **Validate**
`parse_model_body` (pinned vs WORLD models) reaches EOF on a brush's PRIVATE model.

### 5.4 Assemble + ingest gate
Emit each `Begin Actor … End Actor` (bare class, UCC-exact props, `Brush`/`PolyList` for brushes) into
a `Begin Map` wrapper. `model.parse_t3d` → level. **Run `ClassIndex.qualify_and_validate(level.actors)`**
(decision 18:49) — bare→FQCN + existence-validate; unresolved → exit 2 naming the ref (so the trunk is
FQCN-consistent with every other trunk and `level materialize`/`actor find --class`/the §7 requalified
compare all agree).

## 6. Write path — `_resolve_import_dest` (create-mode)
`TrunkLevelSource.save` refuses without a prior `load()` of an existing box — so mirror `_level_create`:
1. Resolve project + `MAPFILE`; `load_package`; build `schema`/`ClassIndex`; `import_map`; `parse_t3d`;
   `qualify_and_validate`.
2. **Overwrite guard first** (before load): existing box + no `--overwrite` → exit 2. Decide whether an
   existing-but-EMPTY trunk dir counts as existing.
3. **level** → `trunk.write_level(new_dir, level, ranks)`, ranks via `trunk.append_rank` per actor in
   §5.1 order (`model.Actor` has no `order_value` — order lives in `ranks`/`Level.order`). **stash** is
   **asymmetric**: `stash_register.write_stash(id, *, full_level=<name→body via canonical_actor_t3d>,
   order=<§5.1>, packages=<stashlib.referenced_packages>, meta=<constructed>, folders=None,
   force=True)` (see `stashlib.write_tree_box`) — a distinct model→disk conversion, NOT `save`.
4. **Name-collision guard:** duplicate export object names would collapse in the name-keyed level dict /
   `write_actor_tree` → dedup-assert, exit 2 naming the offender.

No editor, no rebuild, no git.

## 7. Validation — honest about what each layer proves

- **`decode∘encode == identity` pins (offline)** — invert OUR OWN writers (`state_frame`, `write_prop`,
  `write_fpoly`). These guard REGRESSIONS against our encoder only; they do **not** prove we parse what
  UnrealEd/retail wrote (our writers are documented loadable-not-editor-identical). State this plainly.
- **Committed retail goldens (offline, LOAD-BEARING)** — the real engine-faithfulness gate. The offline
  test CANNOT call `export_dx_level` (container-bound), so it compares native import against a
  **pre-committed UCC artifact** (a checked-in `MyLevel.T3D` / its canonical hash) through the shared
  `level_order`+`normalize`+`canonical_level_hash` (+ identical requalification). Because decode renders
  UCC-exact (decision 18:49), no struct-drop / float-renorm is needed in the lens — both sides already
  agree textually. **Broaden** beyond "1–2 small": a light with enums, a mover with object refs, a
  brush with named polys, and an actor with a **populated dynamic array** (the array's only offline
  coverage). Requires the game `.u` present offline for qualify/defaults.
- **Integration (`-m integration`, live container)** — native vs `export_dx_level` across multiple OG
  `.dx`; PLUS the strongest end-to-end: `verify.verify_dx_matches(original, materialize(import(original)))`
  (launders both through UCC → fidelity-robust; also exercises materialize, so pair with the direct
  compare to localize import bugs).

The shared lens deliberately hides computed-prop/`float32`/`Normal` noise — so thin real coverage + a
forgiving lens is where silent corruption hides; the broadened retail goldens are the antidote.

## 8. Limitations & caveats
- **Embedded `myLevel` resources** — refs `<mapname>.Foo`; preserved + warned; dangle until
  re-materialized with them (blob not T3D-representable). Extract-to-`.utx` is a follow-up.
- **Cross-actor object refs keep the source map stem** — `canonicalize_self_refs` rewrites only the 4
  structural self-ref classes; a mover `Base=`/`Owner=`/event ref renders `Class'<mapstem>.Other'` and
  isn't rebased. Symmetric for the compare; but the durable trunk stores stem-pinned refs (won't rebind
  under a different package name). Widening self-ref canonicalization is a follow-up.
- **uedctl-native-built maps** have empty private brush Models (shape lives in the world BSP), so their
  brushes import geometry-less. Corpus is UnrealEd-built OG levels (populated Polys) — doesn't bite v1.
- **Folders & labels start empty.** Deriving a folder from `Group=` is a follow-up.
- **Strict validation (decision 6):** a map referencing an off-path package fails import exit 2. OG DX
  maps resolve; custom maps may need their packages installed (or the deferred lenient mode).

## 9. Open items
- **~~`[spike]` — authoritative actor order~~ RESOLVED 2026-07-24** (build unblocked; folded into
  §5.1). Layout: `[i32 Num][i32 Max]` then `Num` compact refs (`0`=null), `Actors[0]==LevelInfo`;
  export-table order does NOT match (must decode the array); nulls dropped. Evidence + the initial
  compact-count mis-read: `spikes/2026-07-24-level-import-order/findings.md`; regression
  `test_engine_facts.test_level_actors_array_is_int_num_max_then_compact_refs`. The end-to-end
  `array-order == batchexport-order` confirmation rides §7's Slice-5 integration (near-definitional —
  the exporter iterates `Level->Actors`).
- **Sub-choice — builder `Brush0`:** keep verbatim (default; dropped symmetrically by `normalize_level`
  at compare) vs drop on import.
- **Sub-choice — unknown struct member kind:** schema-walk members, warn-skip a member whose kind isn't
  handled (arrays-in-struct raise `SchemaError` today — decide keep-raising vs support).

## 10. Module shape / touchpoints
- **NEW `uedctl/mapimport.py`** — `import_map(pkg, index, schema) -> str`: StateFrame skip, value decode
  via `render_default_tag`, UCC-exact render (struct member-strip + 6dp floats), dynamic-array decode,
  FPoly/UPolys decode, text render.
- **Promote (from spikes, with round-trip pins where an encoder exists):** `native_dx_actors`
  StateFrame skip (Spike 07); `decode_upolys`/`decode_fpoly` (rewire onto `upackage`).
- **`uedctl/uprops.py`** — expose an `ArrayProperty` Inner element KIND on `Prop` (§5.2d); a UCC-exact
  render mode (6dp floats + member-strip) or a thin `mapimport` wrapper over `render_default_tag`.
- **`uedctl/cli.py`** — `level import` subparser (positional `MAPFILE`, reuse `_tree_flag`, `--overwrite`).
- **`uedctl/dispatch.py`** — handler + `_resolve_import_dest` (create-mode, overwrite-before-load,
  name-collision), `qualify_and_validate` call; route `SchemaError`/`GeometryError` to the clean-exit
  guard.
- **Reused unchanged:** `render_default_tag`/`_decode_struct_bin`, `resolve_class_defaults`,
  `model.parse_t3d`, `emit`, `t3dtree`, `trunk`, `stash_register`/`stashlib`, `normalize`,
  `canonical_level_hash`, `classindex`.

## 11. Test strategy (`bin/test`; `-m integration` live)
1. **Round-trip pins (offline, regression-only):** StateFrame, `write_prop` value forms, `FPoly` —
   `decode∘encode == identity`; documented as guarding our encoder, not engine-faithfulness.
2. **Retail goldens (offline, load-bearing):** committed UCC artifact vs native import canonical, over
   a broadened shape set (enums / object refs / named polys / populated dynamic array).
3. **UCC-exact render pins (offline):** a struct prop renders member-stripped vs its class default
   (incl. `Scale=(1,1,1)` — a member equal to a NON-zero default is dropped); a float prop renders 6dp.
4. **Verb errors (offline):** non-package/missing `MAPFILE`, existing box w/o `--overwrite`,
   `--tree prefab/…`, duplicate actor name, unresolved class/texture ref (strict), no project → each
   exit 2 naming the offender.
5. **Brush geometry (offline):** a `CSG_Subtract` fixture imports its full `PolyList` incl. `Item`.
6. **Live corpus (integration):** multiple OG `.dx` native-vs-`export_dx_level`; + the
   `materialize(import(x))` round-trip via `verify_dx_matches`.

Artificial destination names (`m03-study`, `import-1337`).

## 12. Docs to update on build
- `docs/usage.md` (the verb + caveats), `docs/leveldesign/` (study/remix note),
  `architecture.md` (the decode pipeline, UCC-exact render, create-mode resolver, `qualify_and_validate`
  on import), `unrealed/t3d.md` (new decode facts: Actors-array order, UPolys body, StateFrame — cite
  Spike 07), `decisions.md` (16:48/16:59/17:19/18:49; append §9 resolutions when they land).
```
