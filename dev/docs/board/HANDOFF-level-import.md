# HANDOFF — `level import` (native `.dx`/`.unr` → T3D trunk), 2026-07-27

**Status: STARTED AND PARKED, mid-build.** The work was halted by the owner partway through, not
finished and not gated. Nothing has been reviewed. The branch is local-only and unmerged.

**Read this before touching anything on the branch.** It is written for someone who has never seen
this work: it says what exists, what is knowingly broken, and which two traps in the on-disk format
cost the most time to find.

---

## 0. TL;DR

- **Branch `level-import`**, a git worktree at `.claude/worktrees/level-import`, branched from
  `master` at `85c88ab`. **Two commits, never pushed** (a feature branch is squash-merged, never
  pushed — `CLAUDE.md` "Feature worktrees").
- **Slice 1 and Slice 2 of the plan are written; Slices 3–6 are not.** More precisely: the decode
  *core* exists and demonstrably decodes real retail maps end to end, but it has **zero tests**, two
  **known defects** (below), and no CLI verb, no write path, no goldens and no docs.
- **The offline suite is GREEN and identical to the baseline** — the work added no tests and broke
  none.
- **Two confirmed defects** in the committed decoder, both found by reading emitted T3D or by
  decoding retail maps, both with the fix already identified. Fix these FIRST; do not build on top
  of them. See §4.
- **One thing the spec asserted that turns out to be FALSE**, and one thing it asked to be validated
  that FAILS as written. See §5.

---

## 1. Where the plan stands, slice by slice

The plan is `dev/docs/plans/2026-07-24-level-import.md`; the spec it implements is
`dev/docs/specs/2026-07-24-level-import.md` (v3). Read both — this handoff does not restate them.

| Plan slice | State |
|---------------------------------------|---
| **0 — actor-order spike** | ✅ DONE before this session; untouched. `mapimport.actor_refs` consumes its finding.
| **1.1 — StateFrame skip** | Written (`mapimport._skip_state_frame`). **No test.**
| **1.2 — FPoly/UPolys decode** | Written (`mapimport.decode_fpoly`, `decode_upolys`, `polygon_of`, `brush_of`). **No test.** Carries defect A *and* defect B (§4).
| **1.3 — `ArrayProperty` inner kind on `Prop`** | Written (`uprops.Prop.array_inner`), plus the schema-cache persistence it forced (§3). **No test.**
| **1.4 — dynamic-array value decode** | Written (`uprops.decode_array_tag`, wired through `mapimport.render_prop`). **No test, and never exercised against a real array-valued property** — no map in the corpus was checked for one.
| **2.1 — UCC-exact value render** | Written (`mapimport.render_prop` + `uprops.ValueStyle`/`T3D_STYLE`). **No test.** Spot-checked against two committed editor goldens by eye (§6) — not by an automated compare.
| **2.2 — per-actor T3D block** | Written (`mapimport.render_actor`). **No test.**
| **3.1 — `import_map` orchestration** | Written (`mapimport.import_map`). **No test.**
| **4.1 — `_resolve_import_dest`** | **NOT STARTED.** No code in `dispatch.py` at all.
| **4.2 — CLI verb + handler + strict validation** | **NOT STARTED.** `level import` does not exist; `cli.py` and `dispatch.py` are untouched on this branch.
| **5.1 — committed goldens** | **NOT STARTED.** See §7 for a blocking question about what the golden can even be.
| **5.2 — live integration** | **NOT STARTED.**
| **6 — docs** | Partially: the two new format facts landed in `dev/docs/unrealed/package-format.md` (§5). `docs/usage.md`, `dev/docs/architecture.md` and `dev/docs/rationale/` are **untouched** and still describe a tool with no `level import`.

**There are NO tests for any of this work.** That is the single largest gap. The suite is green
because nothing tests the new module, not because the new module is right.

---

## 2. The commits

Both are local on `level-import`. Neither is pushed. `git log --oneline master..level-import`:

| SHA | Subject | Contents |
|-----------|---------------------------------------------------------|---
| `0e22262` | Add array-inner plumbing and a T3D value style to uprops | `uedcli/uprops.py`, `uedcli/schema_cache.py`, `uedcli/tests/test_schema_cache.py`, `uedcli/tests/fixtures/schema_golden_fire_v2.marshal` (new), deletion of `schema_golden_fire_v1.marshal`
| `475f237` | Add a partial native map decoder for level import       | `uedcli/mapimport.py` (new, ~500 lines)

### What `0e22262` changed in `uprops.py`

1. **`Prop.array_inner: Prop | None`** — an `ArrayProperty`'s *element* property, decoded as a
   `Prop` of its own. Needed because an ArrayProperty's own `type_ref`/`type_name` point at the
   element property OBJECT, so `type_name` is the element's *name*, never its kind. Resolution is
   one level deep only (`_decode_property(..., _inner=True)`), because UnrealScript has no
   `array<array<T>>` and a self-referential Inner in a corrupt package would recurse forever.
2. **`ValueStyle` + `CLI_STYLE` + `T3D_STYLE`** — one object carrying the two ways a decoded value
   is rendered to text, threaded through `render_default_tag`, `_decode_struct_bin(_at)`,
   `struct_tag_members` and `resolve_class_defaults` as `style=`. `CLI_STYLE` is the default
   everywhere and is byte-identical to the previous behaviour, so no existing caller changed.
   `T3D_STYLE` differs in exactly two ways, both required to match what the editor writes:
   - **floats at a fixed six decimals** (`format_float_t3d`) — `Location=(X=6048.000000,…)`, where
     the CLI form trims to `6048`;
   - **a byte STRUCT MEMBER rendered as its enum value name** — `MainScale=(SheerAxis=SHEER_ZX)`,
     where the previous code rendered `(SheerAxis=5)`. The old behaviour is preserved under
     `CLI_STYLE`; a new `_byte_member_text` is the only place that branches.
3. **New public helpers**, all thin and all used by `mapimport` so it needs no private access:
   `struct_member_schema` (a StructProperty's type → its ordered members),
   `resolve_class_default_tags` (the effective class defaults as RAW tags rather than rendered
   text — the struct member-strip must compare member by member, so a joined `(A=…,B=…)` string is
   useless to it), `zero_struct_members` (the all-zero default a class that declares none
   inherits), `member_keys`, and `decode_array_tag`.

### What `0e22262` changed in `schema_cache.py` — **read this, a committed golden was deleted**

`Prop` gained a field, and `schema_cache` persists `Prop`s to a marshal blob keyed by an explicit
field tuple (`_PROP_FIELDS`). Two consequences were handled:

- **`array_inner` is persisted, not dropped.** It is a nested `Prop`, so it cannot ride the old
  `getattr`-into-a-tuple encoding; `_prop_row`/`_prop_from_row` encode it recursively.
  *Why it had to be persisted:* if the cache handed back `array_inner=None`, the dynamic-array
  decode would fail — or silently skip an array — **only on machines whose cache happened to be
  warm**. That is the worst possible failure shape.
- **`SCHEMA_CACHE_VERSION` bumped 1 → 2**, which is what makes every stale v1 entry unreachable
  (the version is folded into both the cache key and the `v<N>/` directory name). The bump is
  mandatory: `_props_loads` does `zip(_PROP_FIELDS, row)`, and `zip` **truncates** — a v1 9-tuple
  read with a 10-name field list would load cleanly with `array_inner` silently `None`.

**The golden.** `uedcli/tests/fixtures/schema_golden_fire_v1.marshal` was deleted and
`schema_golden_fire_v2.marshal` added. This is the exact step
`test_schema_cache.py::test_frozen_golden_bundle_matches_fresh_decode` instructs in its own failure
message ("Either bump SCHEMA_CACHE_VERSION and refresh the golden, or fix the regression"); the
filename carries the version by convention, and `_GOLDEN` in that test was repointed.

**What a reviewer should check about the golden** (it is a binary blob, so the diff proves nothing):

- It regenerates deterministically. From the worktree root:
  ```
  UEDCLI_SCHEMA_CACHE=off PYTHONPATH=. .venv/bin/python -c \
    "from uedcli import schema_cache; \
     open('uedcli/tests/fixtures/schema_golden_fire_v2.marshal','wb').write( \
       schema_cache.load_package_schema('uned/UED22/fire.u', name='fire', \
                                        need_props=True).golden_bytes())"
  ```
  The committed file must come out byte-identical (5601 bytes). `test_decode_is_deterministic`
  covers the determinism half independently.
- The ONLY intended semantic delta from v1 is the added `array_inner` field and the version stamp.
  `fire.u` has exactly one array property, `Sparks`, whose `array_inner.kind` is `StructProperty` —
  that is the fact the new golden bytes carry that the old ones could not.
- Nothing in the *discovery* half (class list, cmap, super refs, abstract flags) was touched.

---

## 3. What `mapimport.py` actually does

`import_map(pkg, index, schema) -> str` returns `Begin Map … End Map` text for `model.parse_t3d`.
The interesting parts, in the order it runs:

- `actor_refs(pkg)` — finds the single `Engine.Level` export, reads its `None`-terminated property
  list, then the `[i32 Num][i32 Max]` + `Num` compact refs `Actors` array, dropping null slots.
  This is Slice 0's finding, unchanged.
- Two **integrity gates** in `import_map` implement "no silent half-answers": every non-null
  `Actors` entry must be a local export descending from `Engine.Actor`, and **every actor-classed
  export must appear in the array** (otherwise the decode would drop content and the trunk would
  look complete). Verified to hold exactly on the maps probed — `actor_exports == actors_array` and
  `not_in_array == 0` on `paste.dx`, `00_Training.dx`, `02_NYC_Street.dx`.
- `render_actor` — bare class name, StateFrame skip, tags via `read_property_tags`, one
  `render_prop` per tag, then (for a brush) the inline geometry block followed by the `Brush=` ref
  and the trailing `Name="…"`, mirroring `emit.emit_actor`'s ordering and reason.
- `render_prop` — the value forms come from `uprops.render_default_tag` under `T3D_STYLE`, with two
  additions: a **struct drops each member equal to the class default's member** (the editor's own
  rule — this is what produces `Rotation=(Yaw=8192)`), and a **dynamic array becomes one indexed
  line per element** (`Foo(0)=…`).
- Brush geometry — `brush_of` walks `Brush=` ref → private `UModel` → `parse_model_body(...)
  .field_0x54` → `UPolys` → `FPoly`s → `model.Polygon`s, then `emit.emit_brush` renders them
  (deliberate reuse: the geometry text is then guaranteed to parse back).

---

## 4. KNOWN DEFECTS in the committed code — fix these first

### Defect A — `Item=OUTSIDE` is silently deleted from every decoded map

`mapimport.polygon_of` treats FPoly name index `0` as "unset":

```python
    if fp.item_index != 0:          # WRONG
```

Name index 0 is a real name. In every Deus Ex map sampled it is `OUTSIDE`, and in
`02_NYC_Street.dx` **7399 of 10690 authored polygons carry it**. The emitted T3D for that map
contains `Item=2DLoftSIDE`, `Item=Base`, `Item=Rise`, … and **not one `Item=OUTSIDE`**.

This was found by reading `_scratch/out_02_NYC_Street.dx.t3d` and cross-checking the raw item
indices — not by any test, and nothing errors.

**Fix:** drop the `!= 0` guard; the correct unset test is `pkg.names[idx] == "None"`, which the
next two lines already do. Full write-up in `dev/docs/unrealed/package-format.md` §"`FPoly.ItemName`
— name index 0 is a REAL name".

### Defect B — brushes whose `Model`/`Polys` export carries `RF_HasStack` fail to decode

`brush_of` calls `parse_model_body(pkg.buf, me["soff"], me["ssize"])` and `decode_upolys` starts at
`e["soff"]`. Both are wrong when the export's flags carry `RF_HasStack` (`0x02000000`): the body
then begins with an `FStateFrame` and the parse desyncs.

Observed: `00_Training.dx` fails to import at all — `brush_of: corrupt map body (IndexError…)` on
`Brush41`/`Brush42`. Across the first twelve retail maps, 21 `Model` exports (and the matching 21
`Polys` exports) carry the flag; `00_TrainingCombat.dx` has 13.

**Fix:** enter both bodies through `_skip_state_frame(pkg, export)` and pass the remaining length,
i.e. `parse_model_body(pkg.buf, start, soff + ssize - start)`. Confirmed: with the skip applied,
`parse_model_body` reaches EOF on **21 of 21** flagged models. Full write-up in
`dev/docs/unrealed/package-format.md` §"`RF_HasStack` is a per-EXPORT flag".

*(Probe scripts for both live in `_scratch/` — `diag3.py` dumps the failing 86-byte model bodies,
`diag4.py` produces the per-map `RF_HasStack` census. `_scratch/` is gitignored; the findings they
produced are in `package-format.md`, so the scripts are disposable. If you want them as committed
evidence they belong under `dev/docs/spikes/<slug>/harness/` per `dev/docs/rules/spikes.md`.)*

---

## 5. Where the spec/plan turned out to be wrong or under-specified

- **Spec §5.3 asks to "validate `parse_model_body` reaches EOF on a brush's PRIVATE model".** It
  does **not**, for the ~1.5 % of brush models carrying `RF_HasStack` (defect B). The spec frames
  this as a validation step; it is really a required code change.
- **The spec's implicit assumption that `RF_HasStack` marks actors** is wrong — see §4B. Anything
  reading an object body must branch on the export's flag, never on the object's class.
- **The plan's `render_prop` "wrapping `uprops.render_default_tag`" is not sufficient as written.**
  `render_default_tag` renders floats through `format_float` (integral values trimmed to `24`) and
  byte struct members as numbers; the editor writes `24.000000` and `SHEER_ZX`. Hence `ValueStyle`.
  A thin wrapper cannot fix this from outside — the difference is inside the struct decoder.
- **The plan says to expose the array inner "on `Prop`"** and is silent on the schema cache, which
  persists `Prop`. That silence is a trap: see §2.
- **Spec §9's builder-brush sub-choice interacts badly with §5.4's strict validation, and this is
  unresolved.** See §7.

---

## 6. What was actually verified, and how — be precise about this

**Verified by reading serialized T3D output:**

- `_scratch/out_paste.dx.t3d` — the full decode of `uedcli/tests/fixtures/map_import_bounds/paste.dx`
  (a committed 3.5 KB two-brush map that a real editor session produced via `EDIT PASTE`). 10 actors,
  12 polygons. Read by eye and compared against the committed editor goldens
  `uedcli/tests/fixtures/level_small.t3d` and
  `dev/docs/spikes/levelinfo_update/ucc_export_after_save.t3d`. The forms that matched: the
  member-stripped `MainScale=(SheerAxis=SHEER_ZX)`, `Region=(Zone=…,iLeaf=-1)`, six-decimal
  `OldLocation=(X=-500.000000,…)`, quoted `Tag="LevelInfo"`, object refs as `Class'Pkg.Name'`, and
  the omission of a `Location=` whose value equals a non-zero class default (the `Engine.Camera`
  case). **This is an eyeball comparison of two texts, not an automated one.**
- `_scratch/out_02_NYC_Street.dx.t3d` — the full decode of a 2064-actor retail map (7.4 MB of T3D).
  This is where defect A was found: the `Item=` census in the emitted text is missing exactly the
  `OUTSIDE` label.

**NOT verified — do not assume any of it:**

- **No round trip was run.** The emitted text has never been fed through `model.parse_t3d`, never
  emitted back through `canonical_actor_t3d`, and never compared byte-for-byte against anything.
- **No hash compare against a UCC oracle** — the load-bearing gate of Slice 5.1 — was attempted.
- **No `decode ∘ encode` pin** against `native.actor_write`'s `state_frame`/`write_fpoly`/
  `write_upolys_body`, which is what Slice 1 was supposed to produce.
- **Dynamic arrays were never exercised on real data.** `uprops.decode_array_tag` is written and
  never ran against an actual `PT_ARRAY` tag from a map.
- `00_Intro.dx` (the biggest sampled map) was never decoded end to end; only its `RF_HasStack`
  census was taken.

---

## 7. Questions that need the owner's ruling

**Q1 — The builder brush ends up in the imported trunk, and probably should not.**

Every compiled Deus Ex map contains the editor's red "builder brush" as `Actors[1]` — a transient
editing tool, not level content. uedcli already knows how to spot one (`normalize.is_builder_brush`),
but that check keys on the class name being the literal bare string `"Brush"`, and the spec requires
import to run `ClassIndex.qualify_and_validate`, which rewrites `Brush` → `Engine.Brush`. After that
the check can never fire again. The locked decision "all actors imported verbatim" (spec §3 item 4)
says keep it; spec §9 lists dropping it as an open sub-choice.

Consequence if it is kept: every imported trunk carries a builder brush, and `level materialize` of
that trunk would paste it into the built map alongside the editor's own fresh builder brush — with a
likely name collision on `Brush0`. **This was not investigated further and is not a call to make
without the owner.** The options are (a) keep verbatim as ruled, (b) filter builder brushes *before*
qualification, (c) keep it but exclude it at materialize.

**Q2 — What can the Slice 5.1 "committed retail golden" actually be?**

Slice 5.1 wants a committed small retail `.dx` plus a pre-committed UCC `MyLevel.T3D` for it. But
`dev/docs/spikes/2026-07-24-level-import-order/findings.md` records that **game maps are gitignored
copyrighted assets** and cannot be committed — which is why that spike's own regression rides the
*writer* instead. There are three committed `.dx` files
(`uedcli/tests/fixtures/map_import_bounds/{import,importadd,paste}.dx`) that a real editor session
produced from a synthetic two-brush fixture; those are the obvious candidate, but they have no
committed UCC export, and producing one needs the live `dx-lum-uned` container (which is present on
this machine). Whether generating and committing that pairing is acceptable is an owner call.

---

## 8. Concrete next step

1. **Fix defects A and B** in `mapimport.py` (§4 — both have the fix spelled out), then re-run the
   probe against `00_Training.dx` and `02_NYC_Street.dx` and confirm both decode and that
   `Item=OUTSIDE` now appears.
2. **Write Slice 1's tests, which do not exist**: `decode ∘ encode` round-trip pins against
   `native.actor_write.state_frame` / `write_fpoly` / `write_upolys_body` (documented, per the plan,
   as guarding *our encoder* and not engine faithfulness), the `array_inner` kind test, and the
   `T3D_STYLE` render pins (`Rotation=(Yaw=8192)`, the `Scale=(1,1,1)` non-zero-default drop, 6dp
   floats, `SheerAxis=SHEER_ZX`). Add a regression test for each of defects A and B so they cannot
   come back.
3. **Prove the round trip through serialized text, not in-memory objects**: `import_map` →
   `parse_t3d` → `canonical_actor_t3d`, and assert on the resulting text.
4. Then Slice 4 (the verb and write path), then Slice 5, then Slice 6's docs.
5. **Nothing here has been through a review gate.** The whole branch owes a build round before it
   can be merged (`CLAUDE.md` "Review gates").

---

## 9. Test state

- **Baseline, captured on `85c88ab` before any change:** `1 failed, 3653 passed, 13 skipped,
  64 deselected, 1 xfailed` plus 58 Rust tests passing.
- **Now, on `475f237`:** `1 failed, 3653 passed, 13 skipped, 64 deselected, 1 xfailed` plus 58 Rust.
  **Identical.** No new failures, no new skips, no new tests.
- The one failure is the **pre-existing** `test_doc_links.py::
  test_prose_citations_into_the_new_trees_resolve[dev/docs/plans/2026-07-27-actor-preview-faces-plan.md]`,
  caused by another session's in-flight work citing a not-yet-written preview rationale topic.
  **It is not this branch's, and it must not be "fixed" here.**
- Run with `bin/test` from the worktree root, never bare `pytest` (`dev/docs/rules/tests.md`).

---

## 10. Pointers

- **Code:** `uedcli/mapimport.py` (the whole decoder), `uedcli/uprops.py`
  (`ValueStyle`/`T3D_STYLE`, `array_inner`, `decode_array_tag`, `resolve_class_default_tags`,
  `struct_member_schema`, `zero_struct_members`), `uedcli/schema_cache.py` (v2 blob + nested Prop).
- **Not yet touched:** `uedcli/cli.py`, `uedcli/dispatch.py`, `docs/usage.md`,
  `dev/docs/architecture.md`, `dev/docs/rationale/`.
- **Spec / plan:** `dev/docs/specs/2026-07-24-level-import.md`,
  `dev/docs/plans/2026-07-24-level-import.md`.
- **Format facts:** `dev/docs/unrealed/package-format.md` (the two new sections),
  `dev/docs/unrealed/t3d.md` (the T3D text forms), the actor-order spike
  `dev/docs/spikes/2026-07-24-level-import-order/findings.md`.
- **Prior-art writers the decode mirrors:** `uedcli/native/actor_write.py` (StateFrame, property
  tags, `FPoly`/`UPolys`), `uedcli/native/level_write.py` (the `Actors` array),
  `uedcli/native/umodel.py` (`parse_model_body`).
- **Test corpus on this machine:** `uned/DeusExAssets/Maps/*.dx` (gitignored retail maps),
  `uned/DeusExAssets/System/*.u` (the class packages a decode needs),
  `uedcli/tests/fixtures/map_import_bounds/*.dx` (the committed editor-built maps).
