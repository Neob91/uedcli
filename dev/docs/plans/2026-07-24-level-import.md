# `level import` — native map→T3D-tree ingestion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. TDD each task. Steps use `- [ ]`.

**Goal:** A `level import MAPFILE --tree level|stash/NAME [--overwrite]` verb that natively (no editor, no UCC) decodes a compiled `.dx`/`.unr` map file into a per-actor T3D trunk (or stash), rendering each actor exactly as `MAP EXPORT` would so the result is a clean, diffable, re-materializable trunk.

**Architecture:** `mapimport.py` decodes the binary → a `Begin Map … End Map` T3D **text** string, which `model.parse_t3d` ingests (reusing the tested text→model routing); the model is then written via the existing create-mode trunk/stash primitives. The decode REUSES the production value decoder (`uprops.render_default_tag` + `_decode_struct_bin`) and adds only: a StateFrame skip, UCC-exact rendering (member-stripped structs + 6dp floats), dynamic-array decode, and FPoly/UPolys decode. The schema-free hash path (`normalize`/`canonical_level_hash`) is **never touched** — UCC-fidelity is a decode concern (decision 18:49).

**Tech Stack:** Python 3.12, dataclasses, argparse, pytest via `bin/test`. **Spec:** `dev/docs/specs/2026-07-24-level-import.md` v3 (symbol-anchored; read it for rationale + evidence). **Decisions:** `decisions.md` 2026-07-24 16:48/16:59/17:19/18:49 UTC.

**Prior art to study before starting** (do NOT reinvent): `uedcli/uprops.py` (`render_default_tag`, `_decode_struct_bin`(`_at`), `resolve_class_defaults`, `Prop`, `_decode_property` array `type_ref`); `uedcli/upackage.py` (`read_property_tags`/`PropertyTag`, `object_path`/`object_class_name`/`name_of_ref`, `read_compact_index`, `Package`); `uedcli/native/actor_write.py` (`state_frame`, `write_prop`, `write_fpoly`/`write_upolys_body` — the encode mirrors); `uedcli/native/umodel.py` (`parse_model_body`, `field_0x54`); `uedcli/classindex.py` (`descends_from`, `ENGINE_ACTOR`, `qualify_and_validate`); `uedcli/dispatch.py` (`_level_create` ~2109, `_resolve_level_source`, `_tree_flag` in `cli.py`); `uedcli/stash_register.py` (`write_stash`), `uedcli/stashlib.py` (`write_tree_box`, `referenced_packages`); `uedcli/trunk.py` (`write_level`/`append_rank`); spikes `dev/docs/spikes/2026-06-27-decontainerize-uedcli/07-native-actor-bodies.md` (+ `harness/native_dx_actors.py`) and `.../harness/upolys_decode.py`.

**Shared rules for EVERY task:** shared checkout on branch `uedcli-impl` with concurrent agents — commit ONLY named files by explicit pathspec (never `git add .`/`-a`/dir); `git push` after each (never force-push/amend/rebase already-pushed). Test from `Tools/uedcli` via `bin/test`. Short imperative commit subjects, no AI attribution. Every CLI error names the offending value + exit 2 — never a traceback. Keep the schema-free hash path (`normalize`) untouched.

---

## SLICE 0 — Actor-order spike — ✅ DONE 2026-07-24 (build unblocked)

Spec §9/§5.1. **Resolved:** `Engine.Level` Actors array = `[i32 Num][i32 Max]` then `Num` signed-compact
refs (`0`=null slot, drop them), in the Level body's native tail after the `None`-terminated property
list; `Actors[0]==LevelInfo`. Export-table order does NOT match → import decodes the array. Verified on
retail `00_Intro`/`00_Training`/`02_NYC_Street`; matches the native writer `level_write.write_level_body`.
Harness `dev/docs/spikes/2026-07-24-level-import-order/harness/order_probe.py` + findings; regression
`test_engine_facts.test_level_actors_array_is_int_num_max_then_compact_refs`. Slice 3's `import_map`
consumes this. (The remaining `array-order == batchexport-order` end-to-end check rides Slice 5.2.)

---

## SLICE 1 — Decode primitives (promote + round-trip pin)

Each isolated and pinned against its encoder where one exists. `decode∘encode` pins guard OUR encoder only (spec §7) — document that in each test.

### Task 1.1 — StateFrame skip (`mapimport._skip_state_frame`)
**Files:** Create `uedcli/mapimport.py` (seed) with `_skip_state_frame(pkg, export) -> int`. Test: `uedcli/tests/test_mapimport_stateframe.py` (NEW).
- [ ] Invert `native/actor_write.state_frame`: for an `RF_HasStack` (`0x02000000`) export, skip Node ci, StateNode ci, ProbeMask u64, LatentAction u32, Offset ci **iff Node≠0**; return the property-list start offset. Promote the reader from Spike 07 `native_dx_actors.py`. Non-`RF_HasStack` → `soff` unchanged.
- [ ] Test: `state_frame(cls) + write_props(...)` bytes → `_skip_state_frame` lands exactly at the property `None`-terminated list start (`read_property_tags` then parses cleanly); Node=0 vs Node≠0 both handled. Cite Spike 07 in a docstring. Commit `uedcli/mapimport.py uedcli/tests/test_mapimport_stateframe.py`.

### Task 1.2 — FPoly/UPolys decode (`mapimport.decode_upolys`)
**Files:** `uedcli/mapimport.py` (`decode_fpoly`, `decode_upolys`). Test: `uedcli/tests/test_mapimport_upolys.py` (NEW).
- [ ] Promote `harness/upolys_decode.py`, **rewiring** its `utexture_decode` imports onto `upackage.read_compact_index`/`Package`. `decode_upolys(pkg, export_idx) -> list[FPoly]` reads `propNone + INT Num + INT Max + Num×FPoly`; `decode_fpoly` → `model.Poly` INCLUDING `Item` (`pkg.names[item_index]`, 0→none), Origin/Normal/TextureU/V/flags/texture-ref/pan.
- [ ] Test: `write_upolys_body(name, [fp…])` / `write_fpoly(fp)` → `decode_*` round-trips (verts CCW, flags, texture vectors, `Item`). Document the pin guards our encoder. Commit the 2 files.

### Task 1.3 — Expose `ArrayProperty` inner element kind on `uprops.Prop`
**Files:** Modify `uedcli/uprops.py` (`Prop` + `_decode_property`). Test: `uedcli/tests/test_uprops_array_inner.py` (NEW).
- [ ] For an `ArrayProperty`, follow the `Inner` UProperty ref (currently `type_ref`/`type_name` = the Inner's NAME only) to resolve the inner element KIND (byte/int/float/object/name/str/struct + its type). Expose it on `Prop` (e.g. `array_inner: Prop | None`). Do NOT change non-array `Prop` decode.
- [ ] Test: a class with `var array<int> Foo` / `var array<Object> Bar` → `Prop.array_inner.kind` correct. Commit `uedcli/uprops.py uedcli/tests/test_uprops_array_inner.py`.

### Task 1.4 — Dynamic-array value decode (`mapimport`)
**Files:** `uedcli/mapimport.py` (array branch). Test: `uedcli/tests/test_mapimport_array.py` (NEW).
- [ ] Decode a `PT_ARRAY` tag: `count + N× inner-SerializeItem` using Task 1.3's inner kind; render each element via the same value path (Task 2.1). NO encode mirror ⇒ no round-trip pin (spec §5.2d) — validate against a captured byte fixture.
- [ ] Test: a hand-built array tag (artificial: 3 ints `[1337,42,0]`) decodes to the right T3D indexed/inline form. Commit the 2 files.

---

## SLICE 2 — UCC-exact per-actor render

### Task 2.1 — Value decode + UCC-exact render (`mapimport.render_prop`)
**Files:** `uedcli/mapimport.py` (`render_prop`, wrapping `uprops.render_default_tag`). Test: `uedcli/tests/test_mapimport_render.py` (NEW).
- [ ] `render_prop(pkg, tag, prop, defaults, resolver)`: decode via `uprops.render_default_tag`/`_decode_struct_bin` (bool/byte-enum/int/float/object-ref/name/str + positional structs — NO native/script branch). Then UCC-exact (decision 18:49): (i) **member-strip** each native struct member equal to the class default's member (from `resolve_class_defaults(fqcn)`; absent ⇒ zero/default struct); (ii) **6dp `%f`** floats. Same requalified FQCN for the default lookup as the compare side (spec §5.2c).
- [ ] Tests (the load-bearing fidelity pins): `Rotation` with `Yaw=8192` renders `(Yaw=8192)` not `(Pitch=0,Yaw=8192,Roll=0)`; **`Scale` member equal to the NON-zero default `1.0` is dropped** (the `Scale=(1,1,1)` trap); a float prop renders `2.000000` (6dp), matching UCC; an enum byte renders its NAME; an object ref renders `Class'Pkg.Name'`. Commit the 2 files.

### Task 2.2 — Per-actor T3D block (`mapimport.render_actor`)
**Files:** `uedcli/mapimport.py` (`render_actor`). Test: `uedcli/tests/test_mapimport_actor.py` (NEW).
- [ ] `render_actor(pkg, export, schema) -> str`: bare class name (`Begin Actor Class=<bare> Name=<obj>`), FQCN of the class via `object_path(export["cls"])` used only for the schema/defaults lookup; StateFrame skip (1.1) → `read_property_tags` → `render_prop` per tag; for a brush, `decode_upolys` → the `Begin Brush/PolyList/Polygon` block + `Brush=Model'…'`; `End Actor`.
- [ ] Test: a fixture Light export → an importable `Begin Actor` block that `model.parse_t3d` accepts and whose props match a committed expected block; a brush export → full `PolyList`. Commit the 2 files.

---

## SLICE 3 — `import_map` orchestration

### Task 3.1 — Enumerate + order + assemble
**Files:** `uedcli/mapimport.py` (`import_map`). Test: `uedcli/tests/test_mapimport_importmap.py` (NEW).
- [ ] `import_map(pkg, index, schema) -> str`: select actor exports (`index.descends_from(object_path(cls), ENGINE_ACTOR)`), order per Slice 0, `render_actor` each into a `Begin Map … End Map` wrapper.
- [ ] Test: a small committed fixture `.dx` → a `Begin Map` string with the expected actor set in the expected order; `parse_t3d` of the result yields the right actor count/classes. Commit the 2 files.

---

## SLICE 4 — Verb + write path

### Task 4.1 — `_resolve_import_dest` (create-mode)
**Files:** Modify `uedcli/dispatch.py` (`_resolve_import_dest`). Test: `uedcli/tests/test_import_dest.py` (NEW).
- [ ] `--tree level/NAME` → a new trunk dir written via `trunk.write_level`+`append_rank` (mirror `_level_create`, ~dispatch.py:2109); `--tree stash/NAME` → the ASYMMETRIC `stash_register.write_stash(id, *, full_level=<name→body via canonical_actor_t3d>, order=<Slice 3>, packages=<stashlib.referenced_packages>, meta=<constructed>, folders=None, force=True)`. `prefab/…` → exit 2. **Overwrite guard BEFORE load** (existing box + no `--overwrite` → exit 2); decide empty-dir-counts-as-existing. **Name-collision** dedup-assert → exit 2 naming the offender.
- [ ] Tests: level dest writes a readable trunk; stash dest writes a readable stash entry; existing box w/o `--overwrite` → exit 2; `prefab/x` → exit 2; two same-named actors → exit 2 naming it. Commit `uedcli/dispatch.py uedcli/tests/test_import_dest.py`.

### Task 4.2 — CLI + dispatch handler + strict validation
**Files:** Modify `uedcli/cli.py` (`level import` subparser), `uedcli/dispatch.py` (handler). Test: `uedcli/tests/test_import_verb.py` (NEW).
- [ ] CLI: `level import MAPFILE --tree KIND/NAME [--overwrite]` (reuse `_tree_flag`; every arg a real `help=`).
- [ ] Handler: resolve project + `MAPFILE`; `upackage.load_package` (bad magic → exit 2 via `SchemaError`); build `ClassIndex`/schema; `import_map` → `parse_t3d`; **`ClassIndex.qualify_and_validate(level.actors)`** (strict, decision 18:49 — unresolved class/texture → exit 2 naming it); `_resolve_import_dest` write. Stderr summary, stdout actor names.
- [ ] Tests: import a fixture `.dx` into a level and into a stash (names on stdout, summary on stderr); non-package file → exit 2; unresolved ref (fixture referencing an off-path class) → exit 2 naming it; no project → exit 2. Commit `uedcli/cli.py uedcli/dispatch.py uedcli/tests/test_import_verb.py`.

---

## SLICE 5 — Validation goldens + integration

### Task 5.1 — Committed retail goldens (offline, load-bearing)
**Files:** `uedcli/tests/fixtures/import/` (a committed small retail `.dx` + a PRE-COMMITTED UCC `MyLevel.T3D` artifact / its canonical hash). Test: `uedcli/tests/test_import_goldens.py` (NEW).
- [ ] Compare `canonical_level_hash(import_map(pkg) |> parse_t3d |> qualify_and_validate)` against the pre-committed UCC artifact through the shared `level_order`+`normalize` (NOT a live `export_dx_level` — container-bound). Because decode is UCC-exact, no lens change is needed.
- [ ] Broaden shapes (spec §7): a light with enums, a mover with object refs, a brush with named polys, an actor with a **populated dynamic array** (arrays' only offline coverage). Commit fixtures + test.

### Task 5.2 — Integration (live container)
**Files:** `uedcli/tests/test_import_integration.py` (NEW, `-m integration`).
- [ ] Multiple OG `.dx`: native import canonical == `store_export.export_dx_level` canonical (through the shared lens). Log each relied-on inconsequential-divergence class so a NEW one trips.
- [ ] `verify.verify_dx_matches(original, materialize(import(original)))` round-trip (data-loss + end-to-end guard). Commit.

---

## SLICE 6 — Docs

### Task 6.1 — User + dev docs
**Files:** `docs/usage.md`, `dev/docs/architecture.md`, `dev/docs/unrealed/t3d.md`, `docs/leveldesign/` (a study/remix note). Board: move the item to `done.md` tail.
- [ ] `usage.md`: the verb, `--tree level|stash/NAME`, `--overwrite`, project requirement, strict-validation + embedded-resource + cross-actor-ref-stem caveats.
- [ ] `architecture.md`: the decode pipeline (`mapimport`), UCC-exact render, create-mode resolver, `qualify_and_validate` on import.
- [ ] `t3d.md`: new decode facts (Actors-array order + null handling from Slice 0, UPolys body, StateFrame) with Spike-07 citations + confidence markers. Commit each doc by explicit path.

---

## Self-review checklist
- **Spec coverage:** §5.1 order (0.1, 3.1), §5.2a StateFrame (1.1), §5.2b/c value+UCC-exact render (2.1), §5.2d arrays (1.3, 1.4), §5.3 brush polys (1.2, 2.2), §5.4 ingest gate (4.2), §6 create-mode/stash-asymmetry/guards (4.1), §7 goldens+circular-pin honesty (5.1, 5.2), §9 spike (0.1). Decisions: decode-time strip (2.1), strict validation (4.2), destination `--tree` (4.1/4.2).
- **Reuse, don't reinvent:** value decode = `render_default_tag`/`_decode_struct_bin` (2.1); NO native/script struct branch; write seams reused (4.1); hash path (`normalize`) untouched.
- **New code is bounded:** `mapimport.py`, StateFrame/FPoly promotion, array-inner plumbing, the verb — everything else reused.
- **Honest tests:** `decode∘encode` pins documented as encoder-only guards; the LOAD-BEARING gate is the committed retail goldens vs a pre-committed UCC artifact (5.1); arrays covered only by a golden (no pin).
- **Order spike is a hard gate:** Slice 0 completes and folds into the spec before Slice 3's order code.
