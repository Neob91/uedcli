# 87 — Cause 2 pinned: native's shattered CSG tree is Pass-1 OVER-SOLIDIFICATION from ~~the `is_csg_filter` dead-node hack~~ **DROPPED BRUSH SCALE**

> **⚠️ SUPERSEDED — READ §9 FIRST (2026-07-19, later same day).** The `is_csg_filter` mechanism
> pinned in §4 was **FALSIFIED**. Two follow-ups proved it: (a) toggling `is_csg_filter`
> (hack / engine-faithful / tag-gated) leaves every `[A]` metric **identical** (a later
> `bsp_cleanup` pass neutralizes the dead nodes); (b) the real driver is
> **`materialize._build_brush_input` silently DROPPING each brush's MainScale/PostScale** — scaled
> brushes build at UNIT size, so scaled-up SUBTRACT brushes carve tiny holes instead of full rooms
> and the room interiors stay SOLID. **Applying scale collapses HK `[A]` 74.5%→8.9% and UNATCO
> 15.3%→1.1%.** The module is **`materialize.py` (Python), NOT `bspcsg.rs`**. The castle stayed a
> perfect control because it has **ZERO scaled brushes** — the entire §1–§7 diagnosis below was
> reasoned from a control that structurally cannot exhibit the bug. §1–§7 are kept for the record
> (the golden `shatter_probe.py` evidence in §2 is sound; only the §4/§5/§7 *mechanism/module* is
> wrong). **§9 is the confirmed root.**

**Status:** ~~DIAGNOSIS, CLOSED~~ **SUPERSEDED by §9; FIX LANDED — §10.** The §4 `is_csg_filter`
root was falsified; the confirmed root is dropped brush scale (§9), now FIXED in production
`materialize._build_brush_input` (§10 — scale baked + mirror winding reversed): HK `[A]` 74.5%→0.3%,
UNATCO 15.3%→1.1%, Catacombs 9.7%→0.9%, castle byte-identical, committed regression
`test_native_scale.py`. **Date:** 2026-07-19.
**Scope:** the follow-up to §70 §13.3, which split the real-level over-fragmentation into Cause 1
(zone-portal over-marking, FIXED in `zones.rs` §13.2) and **Cause 2** (native's finalized CSG tree is
"geometrically shattered" — 44 / 25 disconnected leaf-blobs on UNATCO / Catacombs where the editor's
own tree has 4 / 3). This section pins Cause 2's mechanism, the exact pipeline stage, the real
cross-level trigger, whether it is one defect or several, and the module + scoped fix.
**Reproduce:** `harness/shatter_probe.py` (cross-tree PointRegion probe) + `harness/overlap_discriminator.py`
(trigger metric) + the `UEDCLI_BSPCSG_NOREPART` env toggle. Nothing normalized; RAW geometry only.

### Confidence legend
✅ live-verified against the real `.dx` this session (golden geometric evidence).
🔎 code trace corroborated by two independent cold-review subagents + a direct read.

---

## 1. The one-line finding ✅

**Native marks as SOLID up to three-quarters of the empty space the editor keeps OPEN, and it does
so during Pass-1 incremental `bspBrushCSG` — before repartition — driven by the `is_csg_filter`
dead-node hack (`bspcsg.rs:437`) mis-firing on ADDITIVE faces buried solid-on-both-sides.** The
"shattered tree" (dozens of disconnected empty leaf-blobs, entombed zero-portal leaves) is the
DOWNSTREAM consequence: over-solidification carves the connected void into islands. `zones.rs` then
faithfully floods the broken tree.

## 2. The golden probe — `shatter_probe.py`, validated ZERO on the byte-identical castle ✅

A shipped `.dx` and a native build each carry a finalized BSP tree with per-node `iLeaf` and empty
leaves. The probe samples empty space DENSELY near real geometry: for every EDITOR node that stores a
polygon it takes the polygon centroid nudged ±EPS along the plane normal → two points just off a real
world face (exactly the doorway / wall-adjacency regions where connectivity lives), then does an
`FPointRegion` descent (the `iFront`/`iBack` convention the zone oracle already verified) in BOTH
trees. Ground-truth "is this open space" = the EDITOR golden's own descent (its finalized tree). The
classes it counts, over all probe points the editor says are empty:

- **[A]** editor-EMPTY but native lands in SOLID — native walled off open space (over-solidification).
- **[R]** editor-SOLID but native-EMPTY — native over-carved (the reverse).

**Validation:** on `Test_Castle` (native is byte-identical, 1156/1156 nodes) the probe reports
**[A]=0, [R]=0, components=2 = editor** — zero divergence. The probe has no systematic
orientation/winding bias; every non-zero number below is a real native defect.

**RAW result across the four levels** (`shatter_probe.py NATIVE.dx GOLDEN.dx`):

| level | style | native leaf-blobs `[D1]` (ed) | **[A] editor-empty→native-SOLID** | [R] over-carved |
|---|---|---|---|---|
| Test_Castle | mixed (byte-perfect) | 2 (ed 2) | **0.0 %** (0 / 1168) | 0 |
| 03_NYC_UNATCOHQ | additive office | 44 (ed 4) | **15.3 %** (812 / 5306) | 155 |
| 10_Paris_Catacombs | heavy overlapping SUBTRACT | 25 (ed 3) | **9.7 %** (1103 / 11338) | 692 |
| 06_HK_WanChai_Market | dense overlapping ADDITIVE | 131 (ed 2) | **74.5 %** (9431 / 12651) | 815 |

On HK native fills **three-quarters** of the editor's open volume with solid. The `[A]` points are
NOT scattered noise: they fall in **1260 distinct 256-uu voxels** spanning the whole level bbox
(`x[-18430,2814] y[-4862,6654] z[-1022,4862]`). This is why HK's surfaces halve (−49 %, §85), its
leaves halve (−62.6 %), and its empty space shatters into 131 blobs with 62 zero-portal entombed
leaves: the interior of most rooms is solid in native.

**It is not a thin-shell face-registration artifact — it is deep.** Sweeping EPS 2 → 16 → 64 uu (i.e.
sampling ever deeper into the editor's empty cells) holds HK `[A]` at **74.5 % / 73.3 % / 74.1 %**.
Whole rooms are solid, not just a sliver near each face.

## 3. STAGE localized: Pass-1 incremental CSG, NOT repartition/merge/FindBestSplit ✅

The pipeline is: Pass-1 incremental `bsp_brush_csg` per structural brush → **bspRepartition**
(`bsp_build_fpolys` → `bsp_merge_coplanars` → `bsp_build`/`find_best_split`) → `bsp_refresh` → Pass-2
detail brushes → `finalize` (`zones::assign_leaves_and_zones`). Building HK with `UEDCLI_BSPCSG_NOREPART=1`
(repartition skipped, raw incremental tree) and re-probing:

| HK build | nodes | leaves | surfs | **[A] over-solidified** |
|---|---:|---:|---:|---:|
| PRE-repartition (`NOREPART`) | 13394 | 3037 | 3041 | **74.5 %** (9427) |
| POST-repartition (shipped native) | 5428 | 1420 | 2664 | **74.5 %** (9431) |
| editor golden | 11849 | 3800 | 5224 | — |

**`[A]` is identical before and after repartition.** Repartition merely rebuilds the tree over the
SAME solid/empty partition (and collapses redundant empty leaves 3037→1420); it neither introduces
nor removes the over-solidification. Therefore the root is **Pass-1 incremental `bsp_brush_csg` /
`FilterWorldThroughBrush`**, and the three other suspects are RULED OUT as the root:
- **`bsp_merge_coplanars` (over-merge)** — post-Pass-1, doesn't change the solid/empty partition. Only
  merges fragments of the SAME source surface (`same_surface`); ruled out.
- **`find_best_split` / `bsp_build` repartition balance** — rebuilds from the soup; `[A]` unchanged.
- **`zones.rs` leaf/portal/flood** — proven byte-faithful to the editor's Pass A/B/C/D (cold-review
  subagent, cross-checked against `re-raw-zones/passA-leafenum-7760.md` + `passD-assignzones-7400.md`);
  it floods whatever tree it is handed, and reproduces editor counts on editor trees (§13.1).

## 4. MECHANISM: `is_csg_filter` (`bspcsg.rs:437`) drops the engine's `NumVertices>0` clause 🔎

```rust
// bspcsg.rs:437
fn is_csg_filter(n: &BspNode) -> bool { (n.node_flags & 0x21) == 0 }
```
The editor's real `FBspNode::IsCsg` (`Editor.dll 0x33b80`, decode §82 §8.6) is
`NumVertices>0 && !(NodeFlags & 0x21)`. Native **deliberately drops the `NumVertices>0` clause** — a
tuning shortcut whose own code comment (`bspcsg.rs:418-436`) states it was validated ONLY on the
subtract-heavy castle and closes with *"The engine reaches the same net fragment set via its node
ordering / tree structure; this is the order-independent equivalent."*

`FilterWorldThroughBrush` DELETES a world face buried inside a later brush by setting its node's
`NumVertices=0` while keeping the node in the tree as a plane-only splitter (`filter_one_world_node`,
`bspcsg.rs:~881`). Native's hack then treats every such **dead node** (nv=0) as a CSG solid-divider
that flips the `Outside` flag during the LOOP-2 add-pass (`filter_ed_poly` Outside propagation,
`bspcsg.rs:622-654`: front `outside||csg`, back `outside && !csg`).

- **SUBTRACT context (castle, catacombs) — hack is (net) CORRECT.** A face deleted by a subtract still
  bounds solid on one side (e.g. the world floor cut by a wall footprint — solid persists below), so
  the dead node's plane really is still a solidity boundary and SHOULD flip `Outside`.
- **OVERLAPPING-ADDITIVE context (HK) — hack MIS-FIRES.** When additive brush B buries a face F of an
  earlier additive brush A (F now sits inside the A∪B solid), F has **solid on BOTH sides** — its
  plane is no longer any boundary. The editor (seeing `nv==0`) makes it transparent; native forces it
  to keep flipping `Outside`. Its plane is INFINITE, so any later additive fragment that descends to
  the "back" of that spurious CSG plane — including fragments in genuine void far from A/B — gets
  `Outside` forced false → classified `F_INSIDE` → **the face is silently dropped** (`leaf_func` Add
  only adds on `F_OUTSIDE`-family; `bspcsg.rs:483-511`), AND the void it bounded mis-propagates as
  solid. At HK density (hundreds of overlapping additive brushes) every buried face injects an
  infinite false-CSG plane; this compounds into the ~50 % surface loss and 74.5 % over-solidification.

Two cold-review subagents converged on this independently: one traced the leaf/flag path and PROVED
`zones.rs` + `derive_nf` byte-faithful (so the defect is upstream); the other traced the LOOP-2
add-pass and pinned `bspcsg.rs:437` as the single highest-confidence line, ruling out the cospatial
tables, the `PF_SPLIT_MARKER` re-add gate, the bound-sphere prune, and the thresholds.

## 5. TRIGGER: additive faces buried solid-on-both-sides — NOT brush count, NOT dead-node count ✅

The pre-repartition **dead-node (nv=0) population** — the false-CSG-divider pool — measured on each
`NOREPART` build:

| level | pre-repart nodes | **dead nv=0** | `[A]` over-solidified | add : sub ratio |
|---|---:|---:|---:|---:|
| Test_Castle | 2332 | 540 (**23.2 %**) | **0.0 %** | 4.59 : 1 |
| 03_NYC_UNATCOHQ | 10540 | 1365 (13.0 %) | 15.3 % | 2.56 : 1 |
| 10_Paris_Catacombs | 24639 | 3272 (13.3 %) | 9.7 % | 2.32 : 1 |
| 06_HK_WanChai_Market | 13394 | 4051 (**30.2 %**) | **74.5 %** | 3.96 : 1 |

The control row is decisive: **the castle has 23.2 % dead nodes yet `[A]=0`.** So the raw dead-node
COUNT is NOT the trigger — the hack handles the castle's dead nodes correctly because they are
subtract-context dividers (solid on one side). What separates the levels is whether a dead node is
the **benign** kind (solid / void divider — hack correct) or the **malignant** kind (ADDITIVE face
buried solid / solid — hack flips `Outside` into genuine void). Hence:
- **Catacombs** (subtract-dominant, 2.32:1) — most dead nodes are benign dividers → `[A]` only 9.7 %
  despite 13.3 % dead and the highest brush count of the three real levels. **Density is NOT the
  trigger** (Catacombs is denser than UNATCO yet over-solidifies less).
- **UNATCO** (additive but sparser overlap) — some malignant dead nodes → 15.3 %.
- **HK** (dense overlapping additive, 3.96:1, 30.2 % dead) — malignant dead nodes dominate → 74.5 %.

The real discriminator is **overlapping-additive burial**: additive brushes whose faces end up
interior to other solid. `overlap_discriminator.py` corroborates the direction (HK has the most
additive-additive AABB overlap per brush, 1.99, and the highest additive ratio), though a raw AABB
overlap is too coarse in dense geometry to separate benign-adjacent from buried — the clean separator
is the golden `[A]` measurement itself.

## 6. ONE defect or several? — Cause 2 is dominated by ONE; a separate milder defect coexists ✅

- **Cause 2 (the shattered tree / over-fragmentation) = ONE defect:** the Pass-1 `is_csg_filter`
  dead-node hack (`bspcsg.rs:437`). It produces the over-solidification on all three real levels
  (worst on HK), and the disconnection/entombment is its downstream consequence. This is the defect
  behind the native-UNATCO load-hang suspicion.
- **A SEPARATE, milder defect: BSP over-split.** Even where the surface SET matches (UNATCO Surfs
  −0.2 %), native's node/vert/leaf counts run **+10…+21 %** (§84) — a repartition/`find_best_split`
  balancing difference, present independent of the over-solidification (it inflates the tree; the
  hack deflates it). It does NOT shatter connectivity and does NOT break playability; **out of scope
  for the Cause-2 fix.**
- Cause 1 (zone-portal over-marking) is already fixed in `zones.rs` (§13.2).

## 7. MODULE + scoped fix + effort ✅🔎

**Module to change:** `uedcli-native/src/bspcsg.rs` ONLY — `is_csg_filter` (437), the FWTB
dead-node deletion in `filter_one_world_node` (~881), and the LOOP-2 `Outside` propagation
(`filter_ed_poly` 622-654). **NOT** `zones.rs` (proven faithful), **NOT** `passes.rs` merge, **NOT**
`find_best_split`.

**Highest-leverage first fix (targeted, do this first).** Distinguish, at FWTB-deletion time, a face
deleted because it is buried **solid-on-both-sides** (additive burial — must become transparent, the
engine's true `nv==0` behavior) from one deleted as a **subtract divider** (solid on one side — must
keep flipping `Outside`). Tag the two kinds on the dead node and make `is_csg_filter` return `false`
for the buried kind only. The solidity of each side is testable at deletion time (the brush being
filtered is Add vs Subtract, and the face's classification already carries front/back-outside). Then
re-run `shatter_probe.py` expecting HK `[A]` to collapse toward 0, and **re-verify the castle stays
byte-identical** (1156/1156 nodes, 485 surfs) plus the §82 N=4..8 soup goldens.

**If parity can't be recovered that way — the proper fix.** The hack is a stand-in for an
order-dependence native does not reproduce: the editor keeps the below-a-cut solid represented by a
*live* node via its brush-ordered tree, so it never needs a dead node to act as a CSG divider. The
faithful fix is to finish porting `bspBrushCSG`'s node-ordering / tree-structure so no dead node is
ever consulted for solidity — then `is_csg_filter` can carry the exact `NumVertices>0` clause with no
special-casing.

**Effort estimate.** Targeted tag-and-gate fix: **MEDIUM** (a few days) — the change is small but the
risk is re-establishing castle byte-parity + the soup goldens, which the current hack is entangled
with. Proper order-faithful re-port: **LARGE** (weeks) — it reopens the incremental-CSG node ordering
that the byte-parity work is built on. Recommend the targeted fix first, gated on a dense
overlapping-additive level (HK, or a small synthetic two-overlapping-additive-in-void fixture) being
ADDED to the differential loop — the castle alone provably hides this entire class of bug.

## 8. Reproduce
```
cd Tools/uedcli
# cross-tree over-solidification probe (validated [A]=0 on the byte-identical castle):
.venv/bin/python dev/docs/spikes/2026-07-15-native-materialize/harness/shatter_probe.py \
    DX/Maps/NativeHKMarket.dx DX/Maps/06_HongKong_WanChai_Market.dx        # [A]=74.5%
.venv/bin/python dev/docs/spikes/2026-07-15-native-materialize/harness/shatter_probe.py \
    DX/Maps/NativeCastle.dx  DX/Maps/Test_Castle.dx                        # [A]=0 (control)
# stage isolation (pre- vs post-repartition): [A] identical => Pass-1 root
UEDCLI_BSPCSG_NOREPART=1 .venv/bin/python \
    dev/docs/spikes/2026-07-15-native-materialize/harness/build_native_hkmarket.py \
    DX/Maps/NativeHKMarket_norepart.dx
# trigger metric (additive-overlap density per level):
.venv/bin/python dev/docs/spikes/2026-07-15-native-materialize/harness/overlap_discriminator.py \
    _scratch/{unatco,catacombs,hkmarket}/uedcli/maps/*
```

---

## 9. CONFIRMED ROOT (2026-07-19, supersedes §4/§5/§7): DROPPED BRUSH SCALE in `materialize._build_brush_input` ✅

**Reproduce:** `harness/scale_defect_probe.py` (quantify + mode builds) + `harness/shatter_probe.py`.

### 9.1 The falsification of §4
Two independent follow-ups killed the `is_csg_filter` (`bspcsg.rs:437`) hypothesis:
1. **Toggle test.** Building HK with `is_csg_filter` in its hack form, its engine-faithful
   `NumVertices>0` form, and a tag-gated form left **every `[A]` metric identical**. A downstream
   `bsp_cleanup` pass removes the dead (nv=0) nodes before they can affect the finalized descent, so
   the LOOP-2 `Outside`-propagation story in §4 does not actually reach the output tree. The hack is
   **inert**, not the driver.
2. **The control was blind to the bug.** §1–§7 leaned on the castle staying `[A]=0`. But the castle
   has **0 scaled brushes** (`scale_defect_probe.py quantify`), and the real defect is scale-only — so
   the castle *structurally cannot* show it. A control that can't exhibit the failure can't
   discriminate its cause; the §4 mechanism was an artifact of reasoning from that blind control.

### 9.2 The mechanism, confirmed against the golden ✅
`materialize._build_brush_input` (docstring lines 393–398) **silently drops every brush's
MainScale/PostScale** — the Rust core (`build.rs:786`, `bspcsg.rs:1765`) *rejects* a non-identity
`scale` tuple, so `_build_brush_input` passes identity scale and any authored scale is lost. A brush
with `PostScale=(6.5,5,18)` therefore builds at **unit size**. HK is **73.3% scaled** (975/1330
brushes; 188 of 268 SUBTRACT brushes scaled): a scaled-up subtract carves a tiny hole instead of the
full room, so the room interior stays SOLID → the editor's open void reads solid in native → `[A]`.

### 9.3 Golden evidence — applying scale collapses `[A]` on BOTH real levels ✅
`apply_scale` bakes the model-side `rotation.actor_linear` = `PostScale·R·MainScale` into the brush
world transform (normals/origins recomputed from the transformed winding). `[A]` from `shatter_probe.py`:

| level | scaled % | baseline `[A]` / surfs | **apply_scale `[A]` / surfs** | golden surfs | % of `[A]` scale explains |
|---|---:|---:|---:|---:|---:|
| Test_Castle | **0 %** | 0.0 % / 485 | 0.0 % / 485 (gated = byte-identical) | 485 | control |
| 03_NYC_UNATCOHQ | 11.8 % | 15.3 % / 3581 | **1.1 % / 4056** | 3589 | **93 %** |
| 06_HK_WanChai_Market | 73.3 % | 74.5 % / 2664 | **8.9 % / 4723** | 5224 | **88 %** |

The scaled-brush fraction tracks `[A]` almost 1:1 across all three levels (0→0, 11.8→15.3, 73.3→74.5).
Applying scale recovers **80 %** of HK's lost surfaces (2664→4723 of the 5224 golden) and takes HK
leaf-blobs 131→21, UNATCO 44→18 — the "shattered tree" un-shatters as the rooms re-open.

**Weak control:** `exclude_scale` (drop the scaled brushes entirely) makes HK `[A]` **WORSE**
(74.5%→85.2%) — removing a scaled subtract leaves its room uncarved too. Only *applying* the scale
helps; this rules out any "the scaled brushes are simply noise" reading.

### 9.4 H2 (movers-as-CSG) — negligible for `[A]`, but a real SECONDARY tree-shatter / zone source ✅
`csg_order` (`materialize.py:550`) pulls every brush-bearing actor into CSG, including HK's 23
`DeusExMover`s (movers are dynamic, not world CSG). Isolated: HK `nomovers` (scale still dropped)
`[A]` 74.5%→**74.3%** — movers explain ~**0 %** of the over-solidification. BUT with scale applied,
dropping movers takes leaf-blobs **21→2** (= the editor's 2 exactly) and zones **23→4** (~editor 5).
So movers-as-CSG are the **residual** tree-fragmentation / spurious-zone contributor once scale is
fixed — the "milder separate defect (BSP over-split / entombed leaves)" §6 already flagged, now
attributed. H3 (float precision) needs no separate experiment: scale + movers explain essentially all
of `[A]` (HK residual 8.9% is comparable to UNATCO's *baseline* and is an artifact of the diagnostic
hack's PostScale-pivot / winding-normal approximation, not large-coordinate precision).

### 9.5 SCOPED FIX
- **Module: `uedcli/native/materialize.py` — `_build_brush_input`** (Python; **NOT** `bspcsg.rs`,
  **NOT** `zones.rs`). Apply the authored scale by composing `rotation.actor_linear`
  (`PostScale·R·MainScale`) into the world transform passed to the Rust core, transforming
  vertices/base by the full linear map and normals/tex-axes by its inverse-transpose (or recompute
  from winding, as the core already does for the solid oracle). The Rust `scale`-reject guard
  (`build.rs:786`) then never fires because scale is baked in upstream — matching that guard's own
  advice ("apply scale upstream"). Secondary: exclude Mover-class actors from `csg_order` (they are
  dynamic actors, never world CSG) to recover exact leaf-blob/zone counts.
- **Castle byte-parity entanglement: NONE — verified.** Gate the new path on non-identity scale;
  identity-scale brushes take the existing builder unchanged. The castle has 0 scaled brushes, so a
  gated build is **byte-identical to baseline** (verified: only the 16-byte package GUID differs,
  offsets 36–51; all geometry sections identical). The fix is transparent to every existing
  byte-parity/soup golden by construction.
- **Effort: SMALL–MEDIUM.** The transform composition is a few lines (the linear map already exists
  in `rotation.actor_linear` and is used by the model-side world-geometry path). The real work is the
  correct normal/tex-axis/base transform under non-uniform scale for surf/Points byte-parity and
  adding a **scaled real level (HK/UNATCO)** to the differential loop — the castle alone provably
  hides this whole bug class. The `is_csg_filter` hack can be left as-is (inert) or reverted to the
  faithful `NumVertices>0` clause independently; it is not on this critical path.

**Board (recorded here rather than `board/inbox.md`, which a concurrent session is editing):**
~~p1 `[implement]` Apply brush MainScale/PostScale in `native/materialize._build_brush_input`~~
**DONE — §10 below** (incl. the mirror winding-reversal the review gate surfaced). p2 follow-ups:
(1) exclude Mover-class actors from `csg_order` (residual leaf-blob/zone shatter, §9.4); (2) pin the
texture-axis transform under scale (forward-`L` vs the editor's inverse-transpose covector convention
— byte-parity/appearance only; needs live editor evidence); (3) native-ingest robustness nits from
the review gate — a `det(L)=0` (degenerate/zero-axis) scaled brush silently drops its polys (no
`SCALE_EPS` guard on this path; the CLI guards at authoring time), and a sheer_rate inside the
`(0,0.05]` snap-deadzone flips `scaled=True` yet bakes an ≈identity `L` (needless byte-parity loss on
that one brush; geometrically harmless).

## 10. FIX LANDED (2026-07-19): brush scale baked in `_build_brush_input`, gated on non-identity scale ✅

The §9 fix is now the durable production path in `uedcli/native/materialize.py::_build_brush_input`
(NOT the diagnostic harness). For a brush with non-identity `MainScale`/`PostScale`:
- the full linear map `L = PostScale·R·MainScale` (`rotation.actor_linear`) is baked into the `rot`
  3×3 handed to the Rust core, so `FPoly::transform` yields `world = Location + L·(v − PrePivot)` —
  the correct scaled world winding — and the `scale` tuple stays identity, so the Rust reject guard
  (`build.rs:786`) never fires;
- the authored per-poly **normals and Origins are dropped** (empty lists): they are PRE-scale and no
  longer describe the scaled face, so the Rust core recomputes each final surf `vNormal` from the
  transformed winding (the oracle's `finalize`/`calc_normal` + the post-`bsp_merge_coplanars` plane
  re-derivation in `build.rs` — verified both recompute, so a winding-derived normal is exactly
  right and no inverse-transpose is needed here), and the surf `pBase` falls back to `verts[0]`;
- a **MIRRORED brush (`det(L) < 0`)** — an odd count of negative scale axes — has its per-poly vertex
  ring **pre-reversed** (exactly as the model-side `transform.bake` does), because the mirror inverts
  winding orientation and the Rust core assumes Orientation +1 (`bspcsg.rs:1589` "NO LOOP-1 reverse")
  and never re-flips; without the reversal a mirrored subtract's winding-recomputed normal points
  INWARD and the room builds inside-out. This was surfaced by the cold-review gate and is DECISIVE
  on HK (30 mirrored brushes) — it takes HK `[A]` 9.8 %→**0.3 %**;
- **texture axes ride the same forward `L`** — exact only for a PURE ROTATION; the editor treats them
  as covectors (inverse-transpose `(L⁻¹)ᵀ`, per `transform.bake`), so under ANY non-identity scale
  forward-`L` differs. That gap changes neither solidity nor surf counts (the gated metrics) — it can
  only shift the `Vectors`-pool dedup (a byte-PARITY / texture-appearance concern) — and is boarded
  as a p2 follow-up (needs live editor evidence to pin the exact convention).

**GATE — an unscaled brush takes the exact prior rotation-only path**, so its `BrushTuple` is
bit-for-bit unchanged. The castle (0 scaled brushes) is therefore byte-identical to baseline.

### 10.1 Production numbers (`shatter_probe.py`, this session, current extension + trunks) ✅

`[A]` = fraction of the editor's OPEN void that native reads SOLID (over-solidification). Baseline =
scale dropped; fixed = scale baked + mirror winding reversed.

| level | scaled % (mirror) | baseline `[A]` / surfs / leaf-blobs | **fixed `[A]` / surfs / leaf-blobs** | golden surfs |
|---|---:|---:|---:|---:|
| Test_Castle | 0 % (0) | 0.0 % / 485 / 2 | **0.0 % / 485 / 2 (Model body 100.00% byte-identical to baseline)** | 485 |
| 03_NYC_UNATCOHQ | 11.8 % (0) | 15.3 % / 3581 / 44 | **1.1 % / 4056 / 18** | 3589 |
| 06_HK_WanChai_Market | 73.3 % (30) | 74.5 % / 2664 / 131 | **0.3 % / 5572 / 21** | 5224 |
| 10_Paris_Catacombs | 10.7 % (1) | 9.7 % / — / 25 | **0.9 % / 7396 / 23** | 6491 |

HK over-solidification collapses **74.5 %→0.3 %** (a 250× reduction); its surfs recover past the 5224
golden (5572 — the residual is the milder BSP over-SPLIT defect §6/§9.4, not over-solidification) and
leaf-blobs 131→21. Castle Model-body byte-identity to a fresh baseline-HEAD build confirmed at
100.00 % (245234/245234 B; GUID in the header excluded). Without the mirror reversal HK sits at
`[A]=9.8 %` / 4712 surfs — i.e. the 30 mirrored brushes were the bulk of the post-scale residual.

### 10.2 Committed regression — `uedcli/tests/test_native_scale.py` ✅

Real-level probes run out of gitignored `_scratch/` trunks and can't be committed, and the castle
differential provably HIDES this bug class (0 scaled brushes). So the regression is a self-contained
SYNTHETIC differential (4 tests): a `cube(64,64,32)` subtract with `PostScale (8,8,8)` must carve the
SAME 512×512×256 world room as an explicit `cube(512,512,256)` subtract — asserted by equal solidity
(`_model_point_zone`) at interior + exterior probe points. Verified the assert GOES RED against the
baseline (scale-dropping) module: interior `(200,200,100)` reads SOLID (zone 0) there. A MainScale
variant pins the MainScale leg; a **MIRROR variant (`PostScale (-8,8,8)`, `det(L)<0`)** pins the
winding-reversal (verified red-on-regression: without the reversal that interior reads SOLID/zone 0);
a fourth test pins the unscaled-path gate (identity scale + authored normals preserved). Full offline
suite green (1811 passed).

### 10.3 Headless-boot payoff: the UNATCO load-hang does NOT clear ❌ (scale was not its cause)

Booting the fixed `NativeUnatco.dx` headless (`uplayctl session start --map NativeUnatco`) still
**hangs on load**: the container comes up but the game never establishes its TCP link and no
screenshot is produced (waited >6 min). Inside the container, `DeusEx.exe -log` sits at **95 % CPU
for 5.5 min** — a CPU-BOUND infinite loop during level load, not an I/O wait; its `-log` output never
flushes because the process never leaves the loop. So **correct solidity is necessary but NOT
sufficient**: the over-solidification is fixed (`[A]` 15.3 %→1.1 %, editor-faithful open space) yet
the load-hang remains, with a SEPARATE root cause. Leading suspects (unverified, boarded): the milder
BSP over-SPLIT / entombed-leaf defect (§6, UNATCO nodes/verts still +10…21 %), the movers-as-CSG
spurious zones/leaf-blobs (§9.4 — UNATCO wasn't isolated for movers), or a non-geometry loader path
(Lights / reachspec). Honest verdict: **this fix removes the over-solidification bug class it targets
and is a large correctness win on every real level, but it is NOT the fix for the UNATCO load-hang.**
Next: capture the spinning `DeusEx.exe` call site (attach under the container, or bisect the trunk)
in a dedicated follow-up — filed to the board.

