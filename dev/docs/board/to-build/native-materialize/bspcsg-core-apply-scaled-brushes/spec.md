# Spec — native `intersect`/`deintersect` over an in-tree brush set

**Status:** DESIGN ONLY (no code). Ephemeral per-feature scratch; the durable record is
[`dev/docs/decisions.md`](../../../decisions.md) `2026-07-24 16:32 UTC` + (on landing) `architecture.md` /
`unrealed/*.md`. **Date:** 2026-07-24.

**Read first:**
- [`dev/docs/spikes/2026-07-15-native-materialize/re-raw-zones/bspbrushcsg-intersect-deintersect-decode.md`](../../../spikes/2026-07-15-native-materialize/re-raw-zones/bspbrushcsg-intersect-deintersect-decode.md)
  — the instruction-level decode of UnrealEd's `BRUSH FROM INTERSECTION/DEINTERSECTION` (the ground-truth
  oracle for winding + flags).
- `dispatch.py:975` `_stash_intersect_impl` / `1034` `_stash_deintersect_impl` — the current
  **editor-driven** impl this replaces (and keeps as a differential oracle).
- `unrealed/quirks.md` "CSG model" — solidity/PolyFlags facts; `bspcsg.rs` — the native CSG core.

---

## 0. Goal

Reimplement `intersect`/`deintersect` **natively (no editor)** and reframe them to fit uedcli's stateless,
generator-based model. Today they spin up UnrealEd, recreate a red builder brush, and drive
`BRUSH FROM INTERSECTION`. UnrealEd's operation is `builder-brush ∩ world-solid` — it structurally needs a
live builder brush AND a surrounding carved room. uedcli has neither. So the operation is reframed, not
ported literally.

## 1. The model (what the verbs compute)

Both verbs take an **in-tree set of brush actors** and merge them into **one brush**, differing only by the
assumed **background solidity**:

| verb | background | the set's role | result | typical set |
|---|---|---|---|---|
| `intersect`   | **empty**       | additives make solid, subtractives carve it | boundary of the resulting **solid**, welded into one brush | additive-dominant |
| `deintersect` | **full / solid** | subtractives carve **voids** out of solid    | boundary of the **void** as a solid (the "negative"/plug, faces **reversed**) | subtractive-dominant |

- **`intersect`** welds a cluster of additive brushes (minus any subtracts biting into them) into a single
  solid — e.g. an additive block with a subtractive notch → one brush shaped like block-minus-notch. Errors
  if the set has **no additive brush** ("use deintersect"), mirroring today's impl.
- **`deintersect`** produces the solid that exactly fills what the set carves — e.g. a subtractive brush
  shaped like a doorway → the solid door **plug** that fits it (→ `brush build --mover-class` / mover). Errors
  if the set has **no subtractive brush** ("use intersect").

**Why no room is needed FROM THE USER (and how the algorithm still gets one).** UnrealEd's world is solid by
default, so the editor `intersect` prepends a wrap-**subtract** cube to force an empty background, then does
`builder ∩ solid`; editor `deintersect` uses the default solid world (no wrap), then `builder ∩ empty`. That
wrap-cube + bbox-builder is not semantically meaningful — the wrap just sets the background, and the builder
is any box large enough to contain the set. **The reframing removes them from the USER's hands but keeps them
as INTERNAL scaffolding** the faithful algorithm still needs (§4): the verb synthesizes a padded-bbox builder
and (for `intersect`) a wrap-subtract, exactly as the editor impl does, and runs the real decoded
`builder ∩ world` on them. So this is a faithful port of the editor operation with the scaffolding
auto-generated, NOT a different "merge with a uniform background" algorithm.

**Equivalence scope — SOLID, not (yet) face-set.** Because the padded builder fully contains the set,
`builder ∩ solid` returns the set's whole solid — the resulting **solid region** is provably the same as the
editor's. The exact **face representation** (poly count, fragmentation, winding) is only equal because §4
runs the *same* decoded algorithm on the *same* synthesized inputs; it is validated against the editor
differential oracle (§5), not asserted. (An earlier draft claimed face-set equivalence for a
`bsp_build_fpolys`-based shortcut — that was wrong: `bsp_build_fpolys` is the fat repartition soup, a
different fragmentation. See §4.)

## 2. Interface (verbs, I/O)

`brush intersect`/`brush deintersect` are **generators** (`CLAUDE.md` "Verbs compose"): they CONSUME a
T3D brush set and PRODUCE one brush actor T3D. Both ends are the pipe, so the operation is self-contained
(it needs only the set's own brush geometry — no level context) and composes with every tier.

- **Input = a T3D brush set on stdin via `-`** (the `build → add -` T3D convention, NOT a name list). This
  is the SOLE input; there are no name args. Every tier feeds it through its existing `show` verb
  (`actor show`, `stash show`, `prefab show` — all emit T3D blocks). Empty stdin = clean no-op, exit 0.
  Non-brush actors in the stream → **warn on stderr and skip**; a `Mover` → warn+skip (not a CSG brush).
  ```
  actor find --folder castle.door | actor show - | brush deintersect - --mover-class Engine.Mover | actor add -
  stash show s1                                   | brush intersect  -                              | actor add -
  prefab show arch                                | brush deintersect -                             > plug.t3d
  ```
- **Output = one brush (or mover) actor T3D** to stdout, placeholder `Name=` (name allocation is `actor
  add`'s job, per the generator convention). Disjoint result → still one actor + a stderr component-count
  warning (§6).
- **Shared `brush build` output flags.** Being generators, the two verbs accept the SAME output-shaping
  flags as `brush build` (its `_common_build_opts`, `cli.py:737`) — after the generator-flag cleanup
  (decisions `2026-07-24 17:04`): **`--csg add|subtract`** (default `add`), **`--solidity
  solid|semisolid|nonsolid`** (default = the faithful per-face rule §3; `solid` forces clean; `semisolid`/
  `nonsolid` sets actor-level solidity), **`--mover-class <FQCN>`** (emit a Mover — the door-plug→mover in
  ONE command; rejects `--csg`/`--solidity`), **`--texture`**, **`--prop KEY=VALUE`**, **`--rotate`**,
  **`--base-name`**, **`--folder <path>` / `--label <l>` (repeatable)** (emitted as the
  `// uedcli-folder:` / `// uedcli-labels:` T3D carriers, persisted at `actor add`), and **`--at X,Y,Z`**
  (place the re-centered result — §6b). Plus the verb-specific placement flags **`--origin`** and
  **`--pivot`** (§6b). **NOT** shared: `--group` (ditched everywhere → `--prop Group=`).
  > `--solid` from an earlier draft is GONE — it is subsumed by the shared `--solidity solid`.
  >
  > **Two shared flags need VERB-SPECIFIC defaults** (the `_common_build_opts` defaults are wrong here):
  > **`--at` default = `None`** (omitted = keep the carved position — NOT `_common_build_opts`' `(0,0,0)`,
  > which would teleport the result to the origin, §6b); **`--solidity` default = the faithful per-face rule**
  > (§3), NOT `_common_build_opts`' `solid`. Their help strings are overridden accordingly for these verbs.

**Wrappers DROPPED (were an open question — resolved).** The editor-driven `stash intersect`/`stash
deintersect` (`dispatch._stash_*_impl` + `driver.brush_from_*`) are **removed**, and no `prefab
intersect`/`deintersect` is added — all four are redundant with `stash show <id> | brush intersect -` /
`prefab show <name> | brush intersect -`. The editor drive survives ONLY as a test/oracle regeneration
entry (§5), never a shipping verb.

## 3. Flag rule (default = faithful to `bspBrushCSG` LOOP-1)

Poly flags are decided at CSG time and baked into the result faces (independent of whether the brush later
becomes a mover / add / subtract — `BRUSH ADDMOVER` copies polys verbatim, confirmed live). The default
mirrors the engine's `LOOP-1` adjust `PolyFlags = (pf|arg) & ~NotPolyFlags`, `NotPolyFlags=(CsgOper==Add)?0:0x28`:

- a result face from an **additive** source **keeps** that brush's solidity (a semisolid additive → semisolid
  face);
- a result face from a **subtractive** source is **forced solid** (`& ~0x28` — the engine forbids a
  semisolid/nonsolid subtract wall);
- non-solidity flags (texture/pan/translucent/twosided…) are preserved from the source face, masked
  `& 0x3cffffff` (drops only editor-internal high bits `PF_EdProcessed 0x40000000` / `PF_EdCut 0x80000000` /
  `PF_Memorized` etc. — never let those leak into the trunk).
- **`--solidity solid`** overrides: clear `0x28` on every result face (whole brush clean). `--solidity
  semisolid|nonsolid` instead sets the actor-level solidity (clearing per-face `0x28`, since actor-level
  governs). Omitted = the faithful per-face rule above.

This is the resolution of the mover-flags surprise that motivated the whole investigation: the trap is real
but now *chosen* — a semisolid face only appears if a semisolid **additive** was deliberately in the set and
no `--solidity solid` was passed.

**The rule lives in ONE place — the Rust CSG merge, NOT a Python post-pass.** `bsp_brush_csg` already applies
`ed.poly_flags = (ed.poly_flags | pf) & !not_poly_flags` with `not_poly_flags = 0x28` for non-Add
(`bspcsg.rs:1696`), and the leaf/`bsp_node_to_fpoly` already masks `& 0x3cffffff` (`bspcsg.rs:158`) — so the
additive-keeps / subtractive-forces-solid / high-bits-stripped rule falls out of the merge automatically,
per source `CsgOper`, which is only known *inside* the merge. **After extraction an FPoly no longer carries
its source `CsgOper`**, so a Python re-derivation of "additive vs subtractive source" would be ill-posed.
Therefore the default per-face rule is **emergent from the merge, not re-applied**; the only post-extraction
flag steps are the explicit `--solidity` overrides — `solid` = blanket `& ~0x28` on every face; `semisolid`/
`nonsolid` = set the actor-level solidity and clear per-face `0x28` (actor-level governs).

## 4. Native algorithm — a FAITHFUL port of the decoded `builder ∩ world` (corrected)

> **CORRECTION (post-review).** An earlier draft proposed a shortcut: loop `bsp_brush_csg` over the set with
> `root_outside=true`, then `bsp_build_fpolys` and reverse. **That was wrong on three counts, all verified in
> the code:** (1) `bsp_build_fpolys` is the *fat repartition-input soup* ("retaining every CSG fragmentation
> vertex", `bspcsg.rs:1330`), not a clean/editor-faithful brush boundary — it would emit an over-fragmented
> polylist; (2) `root_outside=true` is **unexercised** by the incremental CSG path (consumed only by the old
> `point_in_solid` classifier and a temp-model default — the whole bspBrushCSG pipeline is validated ONLY at
> `root_outside=false`, e.g. `bspcsg.rs:2508`); (3) a blanket `reverse` over all faces over-generalizes the
> decode (only the Phase-2 deintersect leaf reverses). This section replaces that with the real algorithm.

**Do the editor's operation, with the scaffolding synthesized internally — staying on the tested rails.**
`bsp_brush_csg` **already has the exact stub to fill** — `bspcsg.rs:1845`:
`if oper != Add && oper != Subtract { return; // Intersect/Deintersect not used by MAP REBUILD }`. The decoded
tail ([RE doc](../../../spikes/2026-07-15-native-materialize/re-raw-zones/bspbrushcsg-intersect-deintersect-decode.md)
§1) is exactly what goes there. Some building blocks are already ported: `bsp_filter_fpoly` (`bspcsg.rs:710`),
`filter_ed_poly` (`:570`), and the **straddle recursion** of `filter_world_through_brush` (`:834`). The
genuinely new Rust code is the tail driver + the **four intersect/deintersect leaf callbacks**
(`0x339e0`/`0x32390` phase-1, `0x33ab0`/`0x32460` phase-2 — decode §2).
> ⚠️ **Phase-2 is a NEW leaf, not a `bool→enum` widening of FWTB** (corrected after review). The ported
> `filter_world_through_brush` **mutates the world tree** — its leaf (`wtb_leaf`, `bspcsg.rs:963`) re-adds
> fragments as nodes and marks originals dead, with save/rollback of `world.nodes` (`:871`). Intersect/
> deintersect Phase-2 does something structurally different: per decode §2 the P2 leaves (`0x33ab0`/
> `0x32460`) just **append `EdPoly` to an OUTPUT polylist** (optional `Reverse`), never touching the world
> tree. So the port REUSES FWTB's straddle-recursion shape but with a NEW leaf that threads an output
> polylist and does NO world mutation / no commit-rollback — do not wire the world-mutating leaf into the tail.

```
brush_intersect(brush_set, deintersect: bool, solidity):
    validate: intersect needs ≥1 additive; deintersect needs ≥1 subtractive (else exit-2 with guidance msg)
    # NO sort — preserve stdin order as CSG order (§6, order-dependent CSG)
    tuples = [ _build_brush_input(name, actor) for actor in brush_set ]   # existing materialize helper;
              # ERRORS on non-identity Scale — see §6 (bake first or reject)
    lo,hi  = union_bounds(set)                                            # AABB of the set's world verts
    # INTERNAL scaffolding — BYTE-IDENTICAL to `_stash_intersect_impl` (dispatch.py:990-1004), which is
    # the golden generator, so the offsets must match EXACTLY (builders.cube is origin-centered):
    cx,cy,cz = ((lo+hi)/2);  w,d,h = (hi-lo)+64
    builder  = cube(w,d,h) @ (cx,cy,cz)                                   # span [lo-32, hi+32]
    wrap_sub = cube(w,d,h) @ (cx-32,cy-32,cz-32)                          # span [lo-64, hi]  (intersect only)

    # Rust entry `intersect_brushset(tuples, builder, deintersect) -> faces`:
    #   let mut world = Model::default();  world.root_outside = false;       # SOLID bg (tested rails)
    #   if !deintersect { bsp_brush_csg(&mut world, wrap_sub, ...); }        # empty-bg trick, FIRST brush
    #   for t in tuples { bsp_brush_csg(&mut world, t, i, pf); }             # LOOP-1 flag rule applies here
    #   let result = bsp_brush_csg_intersect(&world, builder,                # the DECODED tail (fills :1845):
    #       oper = deintersect ? Deintersect : Intersect);                   #   Phase1 builder↓world (append) +
    #                                                                        #   Phase2 world↓builder-hull (append,
    #                                                                        #   deintersect-P2 reverses); NO tree mutation
    #   return result.polys                                                  # editor's face set+order; iLink renumber
    faces = (solidity == "solid") ? strip_0x28(faces) : faces               # §3: the ONLY post-step
    faces = recenter(faces, origin, pivot, at)                              # §6b exact construction
    emit ONE actor T3D { class = mover_class ?? Engine.Brush; CsgOper = --csg (default Add, omit if mover);
                         Location/PrePivot per §6b; PolyList = faces;
                         + --prop/--rotate + --folder|--label carriers } to stdout   # NO --group (→ --prop Group=)
```

- **Background & builder are internal scaffolding**, generated **byte-identically to `_stash_intersect_impl`**
  (`dispatch.py:990-1004`): the wrap-subtract is `bbox+64` at `(cx−32,…)` (span `[lo−64,hi]`, high face
  coincident with the set max) and the builder is `bbox+64` centered at `(cx,…)` (span `[lo−32,hi+32]`) —
  they are DIFFERENT boxes; the `−32` offset is load-bearing (coincident faces are where CSG classification
  is fragile), so the port must reproduce the editor's exact offsets, NOT a `wrap==builder` shortcut.
  `intersect` prepends the wrap-subtract as the first-processed brush; `deintersect` uses the default solid
  world (no wrap). This keeps the whole pipeline at `root_outside=false` — the ONLY validated polarity.
- **Winding/reverse is per the decode, NOT global**: the deintersect Phase-2 leaf (`0x32460`) reverses its
  appended world-cap fragments; phase-1 and intersect never reverse. Pinned to the editor oracle (§5).
- **Fragmentation is the editor's** because it IS the editor's algorithm — no separate `bsp_merge_coplanars`
  guesswork. The finalize is the decoded iLink surf-share renumber (decode §1), not a repartition.
- **Transforms** (`Rotation`/`PrePivot`) flow through `_build_brush_input` unchanged; **Scale is rejected**
  (§6). Rotation uses the ported GMath sine table.
- ⚠️ **`deintersect` leading-additive risk (verify against oracle).** `intersect` always processes the
  wrap-subtract first (a leading subtract — the tested castle rail). `deintersect` has no wrap, so the
  first stdin brush is processed first; if it is **additive**, the `first_add_seed` convex-seed path
  (`bspcsg.rs:1874`, valid only for a convex first Add, **UNTESTED** for semisolid/non-convex — `:1866`)
  fires. `deintersect` permits additives (guard needs only ≥1 subtract). Mitigation: golden case (h) below
  covers a leading-additive `deintersect` set; if it diverges, prepend a synthetic no-op or reorder so a
  subtract seeds — decided during the build against the oracle.

## 5. Test oracle / fidelity bar

The bar is **T3D face-set parity with UnrealEd's own `BRUSH FROM INTERSECTION/DEINTERSECTION`**, not
byte-identity (there is no on-disk `UModel` — the output is a builder polylist). **Primary offline oracle =
committed goldens; the editor is a regeneration tool, not the standing bar** (it is crash-prone /
integration-gated — `CLAUDE.md` "Background/long-running work", `pytest.ini`):

- **Committed goldens (must be REGENERATED, not assumed captured).** The `intersect.t3d`/`deintersect.t3d`
  from the 2026-07-24 experiment are **gitignored `_scratch` scratch** (now copied to the RE spike dir as
  illustrative evidence only) — NOT test fixtures, and from a stacked-slab scenario, not the set verbs. Phase
  0 of the build regenerates a fresh golden per case via the editor path and commits it under
  `tests/fixtures/` (durable per `CLAUDE.md`). Cases: (a) additive + subtractive notch (`intersect`),
  (b) doorway subtract (`deintersect`), (c) semisolid-additive-in-set (flag rule), (d) `--solidity solid`,
  (e) a rotated source brush, (f) a two-component disjoint set (§6), (g) `--mover-class` output is a `Mover`,
  (h) a leading-additive `deintersect` set (convex-seed risk, §4).

> **Comparison is WORLD-position, not raw vert.** Default `--origin center` emits `Location=anchor` + rebased
> verts; the editor golden emits `Location=0` + world verts. So the compare reduces both sides to WORLD
> space — `world = Location + R·(v − PrePivot)` per face vert AND the poly `Base`/`Origin` — before diffing
> (poly count, world verts, normal, texture, pan, PolyFlags). Equivalently, generate the golden and run the
> native case with `--origin keep` for a direct `Location=0` compare. Do NOT diff rebased local verts against
> the editor's world verts (they will never match). A dedicated re-centering test asserts the §6b
> `Location`/`PrePivot`/vert construction reproduces the same world geometry as `--origin keep`.
- **Fast offline suite:** native output vs the committed goldens (poly count, per-face verts (f32), normal,
  texture, pan, PolyFlags — face-set compare, then tighten to poly order once stable).
- **`-m integration` (regeneration/audit only):** the editor differential (`_stash_*_impl` or an `--editor`
  path) re-derives a golden on demand; run behind the live-container mark, never the standing gate.
- **Engine-fact regression:** pin the §3 flag rule (additive keeps `0x20`; subtractive forced solid) against
  golden (c), back-referencing the RE doc.

## 6. Edge cases

- **Empty stdin / empty set** → clean no-op, exit 0 (generator convention).
- **CSG order = stdin order (do NOT sort).** ⚠️ Corrected after review: CSG over a mixed add/subtract set
  is **order-dependent** (last op on a region wins — `csgRebuild` applies brushes in actor order,
  `quirks.md` "CSG model"). Sorting the set (e.g. by `Name`) would **reorder adds vs subtracts and silently
  drop carves** — e.g. `intersect` of additive `Z_block[0,100]` + subtractive `A_notch[40,60]` under an
  empty background: Name-sorted (`A_notch` first) subtracts-into-empty (no-op) then adds → solid `[0,100]`,
  notch GONE; authoring order (add then subtract) → `[0,40]∪[60,100]`. So the verb **preserves the stdin
  stream order** as the CSG order — the caller controls it via the pipe (`actor show`/`find` emit in a
  deterministic order; the editor golden's `_re_add` likewise preserves the actors-list order,
  `writes.py:88`). Determinism is: same stdin → same output (inherent); there is NO re-sort. The wrap-subtract
  (intersect) is always prepended as the first-processed brush regardless.
- **Positioning & pivot — see §6b (movability).** The merged brush is re-centered so it is trivially
  relocatable; `--at`/`--origin`/`--pivot` govern placement. `actor add` carries NO positioning flag —
  placement is generator-side (`--at`) or a later `actor move`.
- **Scaled source brushes are REJECTED** — inherited from `build_geometry_bspcsg` (`bspcsg.rs:2064`), which
  errors on non-identity `MainScale`/`PostScale`. This is a **pre-existing gap in the bspcsg core**, NOT
  intersect-specific: the older coarse `build_geometry` core DOES apply scale (built 2026-07-19, `board/done/`),
  but the port into the incremental bspcsg core is a separate deferred workstream — **tracked as its own
  prioritized board item** (`board/inbox/`, "bspcsg core: apply scaled brushes"). Until then the verb surfaces a
  clear error naming the offending actor and suggesting `brush apply-transform` to bake the scale first — it
  does NOT silently mis-handle it. (The deferral is legitimate — a cross-cutting core feature that also gates
  bspcsg materialize of scaled maps — hence the board item rather than a silent punt.)
- **Disjoint result → one actor, WARN (no split option).** A set can yield multiple disconnected solids
  (two far-apart clusters under `intersect`). The editor returns them as ONE brush with multiple face groups;
  we do the same, and **emit a stderr warning naming the component count**. There is **no `--split` flag** — a
  user who wants independently mover-izable pieces runs the verb on each subset separately (the input is a
  set, so that is already a natural pipe: `find --folder doorA | … | brush deintersect -`). *(decision:
  no `--split`, 2026-07-24 18:12)*
- **All-additive under `deintersect`** (or all-subtractive under `intersect`) → the guard errors with the
  cross-verb guidance (matches `dispatch.py:431-438`).
- **Non-brush names** (lights) in the set → warn+skip (like `brush poly find`, `decisions.md 2026-07-24 16:28`);
  **unknown** name → hard exit-2. A **`Mover`** source is not a world-CSG brush → warn+skip.
- **Rotated source brushes** — flow through `_build_brush_input`; covered by golden (e).
- **Large sets** — `actor find --folder castle | brush intersect -` feeds O(n) brushes into incremental CSG;
  no hard cap in v1, but the verb prints the brush count to stderr so a runaway is visible.

## 6b. Movability & pivot — the door-mover crux

A brush's world geometry is `world = Location + R·(vert − PrePivot)` (+scale), so it is relocated by its
**`Location`** and rotated about its **`PrePivot`**. The result is a **standalone new actor** — the source
brushes are untouched and unreferenced, so it is inherently movable. The problem is that the *faithful* CSG
output has **`Location=(0,0,0)` and world-space verts** (like the editor's `BRUSH FROM DEINTERSECTION`
export): its local origin sits at the world origin, so "place it at X" needs a hand-computed offset, and a
`--mover-class` mover would rotate about the world origin, not the door. So the verb **re-centers on emit:**

**The exact re-center construction (corrected after review — the naive version displaced the mover).** The
world transform is `world = Location + R·(v_local − PrePivot)`, and the rotation pivot in WORLD space is the
point where `v_local = PrePivot`, which always maps to `Location`. So to preserve world position AND rotate
about a chosen pivot `P` (world), all three fields move together:
- `anchor` = `--origin` (default `center` of the result bbox; also `min`/`max`/explicit; `keep` = the raw
  faithful form, below).
- `pivot P` = `--pivot` (default = `anchor`).
- Emit: **`v_local = v_world − anchor`** (rebased; **apply the SAME translation to each poly's texture
  `Base`/`Origin` point** — finding: `Normal`/`TextureU`/`TextureV` are directions and are unchanged);
  **`PrePivot = P − anchor`** (local); **`Location = P`**. Check at rest (R=I):
  `world = P + (v_world − anchor) − (P − anchor) = v_world` ✓, and rotation is about `Location = P` ✓.
  Default (`P = anchor`): `PrePivot = 0`, `Location = anchor` — the simple re-center.
- **`--pivot` writes `PrePivot`** (ONE flag; decided 2026-07-24 18:33 — `PrePivot` is the only field to set
  offline; no `--prepivot` alias). Authoring `PrePivot` on a fresh brush is deliberate, not the forbidden
  rewrite of an existing pivot (`quirks.md` "Pivots" guards mutation).
- **`--at X,Y,Z`** — override `Location` to an ABSOLUTE world position (moves the whole result so its pivot
  `P` sits at `--at`). **Verb-specific default is `None` = keep the carved position** (NOT `_common_build_opts`'
  `(0,0,0)` default, which would teleport the result to the origin — §2 notes this override). Under
  `--origin keep` (Location already 0, world verts) `--at` is **rejected** (it would double-translate) —
  `keep` is the faithful raw form, incompatible with placement.
- **World-position preservation** holds by construction, so the §5 oracle (which compares WORLD positions,
  §5) is satisfied; a raw vert compare would NOT be (verts are rebased) — see §5.
- **`actor add` has NO `--at`/positioning flag** — it persists the `Location` the generator stamped;
  reposition later with the trunk verb `actor move`. (Same pure-consumer model as `--folder`/`--label`.)

Door-mover flow: `… | actor show - | brush deintersect - --mover-class Engine.Mover --pivot min --at
4096,2048,128 | actor add -` → then `mover key count`/`move`/`rotate` author the swing about the hinge.

## 7. Resolved (were open questions) + what remains

**Resolved by the generator-flag unification (Andrzej, 2026-07-24 — see §2, decisions):**
- **Output `CsgOper`** → the shared **`--csg`** flag (default `add`; omitted for a `--mover-class` output).
  No hardcoded stamp; the `stash deintersect` `CSG_Subtract` default simply goes away with the wrapper.
- **Mover ergonomics** → the shared **`--mover-class <FQCN>`** flag — `brush deintersect - --mover-class
  Engine.Mover` is the door-plug→mover in one command. No bespoke shortcut.
- **Solidity / the mover-flags trap** → the shared **`--solidity`** flag: default faithful per-face (§3),
  `--solidity solid` forces clean. One principled default + a loud help/doc warning ("welding a semisolid
  additive keeps semisolid faces; pass `--solidity solid` for a clean mover"). No per-verb default split.
- **`stash`/`prefab` wrappers** → **dropped** (§2): `stash show | brush intersect -` etc. cover them.
- **Editor path** → kept ONLY as a test/oracle-regeneration entry (§5), not a shipping verb.

**Also resolved since:** **`--split` — DROPPED entirely** (not a flag; one actor + warning, §6);
**scale — REJECT in v1**, tracked as a prioritized board item (bspcsg-core gap, §6); **re-center default =
`center`** (confirmed); **`CsgOper` default = `add`**.

**Pivot flag — RESOLVED 2026-07-24 18:33:** ship **`--pivot`** in v1 (single flag writing `PrePivot`; no
`--prepivot` alias), default = the anchor. No open design items remain.

## 7b. Coupled prerequisite — the generator-flag cleanup (its OWN work item)

The shared-flag design depends on a cross-cutting CLI change to the **generators**, decided this session
(decisions `2026-07-24 17:04`) and tracked separately on the board (it touches `brush build`, `actor build`,
`actor add` — not just these two verbs): **(1)** add `--folder`/`--label` (repeatable) to every generator
(`brush build` shapes, `actor build`), emitted as the `// uedcli-folder:`/`// uedcli-labels:` carriers;
**(2)** REMOVE `--folder`/`--label` from `actor add` (it becomes a pure carrier-consumer; post-hoc changes
use `actor folder set` / `actor label`); **(3)** ditch `--group` from `brush build` (→ `--prop Group=`). This
REVERSES the "folder/label live on `actor add`, not generators" rule (`direction.md`, decisions 2026-07-18
actor-folders / 2026-07-22 actor-labels) — reconciled in `direction.md`. `brush intersect/deintersect` inherit
the resulting common set. **Sequencing:** this cleanup lands (with its own review) before or alongside the
intersect/deintersect build.

## 7c. Doc deliverables (required by `CLAUDE.md`)

Landing this updates: `docs/usage.md` (the two verbs, the shared flags, I/O, the scale/disjoint caveats, the
generator `--folder`/`--label`/no-`--group` change + `actor add` losing the flags); `docs/leveldesign/`
(the door-mover workflow: `subtract a doorway → deintersect --mover-class → add`, incl. the `--solidity`
note); and `architecture.md` + `unrealed/*.md` fold-in of the intersect/deintersect CSG facts once built.

## 8. Decisions recorded

The load-bearing choices (the brush-set reframing + internally-synthesized background/builder; the faithful
decoded `builder ∩ world` port filling the `bspcsg.rs:1845` stub — NOT a `bsp_build_fpolys` shortcut; the
`LOOP-1` flag rule owned by the Rust merge; the T3D-stdin generator interface + dropped wrappers + shared
`brush build` flags; the generator-flag cleanup; rejected alternatives) are in
[`dev/docs/decisions.md`](../../../decisions.md) `2026-07-24 16:32 UTC` + the generator-flag entry (corrected/extended
post-review + post-design-iteration). This spec is ephemeral; the ledger is durable.
