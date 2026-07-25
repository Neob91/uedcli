# 91 — The "native over-produces Leaves 3.6×" gap is a CORRUPT GOLDEN, not a native defect

**Status:** root-cause CLOSED (decode-proven) — **AND the golden-pipeline defect is now FIXED
(§9, 2026-07-19)**: the corrupt golden came from a LEAN headless rebuild (`MAP REBUILD` never runs
the visibility/leaf pass); the two-step full rebuild `MAP REBUILD; BSP REBUILD OPTIMAL OPTGEOM ZONES`
produces a complete refs/leaf==1.0 golden, and `bsp_health_check.py` now ASSERTS refs/leaf==1.0.
Against the corrected golden the old "+24% Verts" and "+2 Zones" gaps VANISH — the only real native
tree-fidelity residual is `Vectors +24%`. **Date:** 2026-07-19.
**Scope:** diagnose the standout tree-fidelity divergence flagged after §89/§90 — native UNATCO
`Leaves 2759` vs the UnrealEd batch golden's `762` (a claimed 3.6× over-production) — plus the
`Verts/Vectors +24%` and `Zones 9 vs 7` deltas. **Diagnostic only; no production `.rs`/`.py`
changed.** Harness: `harness/leaf_structure_diff.py` (+ the `--quiet-reads`/`--rebuild-min-seconds`
barrier knobs added to `harness/build_ued_golden.py`).

### Confidence legend
✅ decode-exact against real `.dx` bytes this session · 🔬 cross-checked against the UED22
disassembly of §70.

---

## 0. TL;DR — the headline reverses

- **The `Leaves 3.6×` is NOT native over-production. The batch golden's `Leaves` array is INVALID**
  (a deterministic non-1:1 array from the headless build path — see §2), so it is an unusable basis
  for a leaf-count comparison. ✅🔬
- **Native's leaf policy is CORRECT** — one `FBspLeaf` per empty terminal cell (refs/leaf = 1.00),
  which is *exactly* what UED22's Pass-A `AssignLeaves` does by construction (§70 §2, disasm-proven)
  and *exactly* what the real shipped `03_NYC_UNATCOHQ.dx` shows (2266 leaves = 2266 empty cells,
  refs/leaf 1.00). Native's 2759 is the same *order* as the shipped map's 2266 (+22 %, tracking the
  finer batch partition), **not** 3.6×. ✅
- The three UNATCO leaf figures and their refs/leaf tell the whole story: ✅

  | model | nodes | Leaves array | empty terminal cells (tree walk) | iLeaf refs | refs/leaf |
  |---|---:|---:|---:|---:|---:|
  | **native** | 6425 | **2759** | 2759 | 2759 | **1.00** ✅ correct |
  | **shipped `03_NYC_UNATCOHQ.dx`** | 5188 | **2266** | 2266 | 2266 | **1.00** ✅ correct |
  | **batch golden (world-only)** | 6314 | **762** | **4454** | 7204 | **9.45** ✗ impossible |
  | batch golden (full) | 7669 | 1127 | — | 7404 | 6.57 ✗ impossible |

  A completed Pass A **cannot** yield refs/leaf > 1 — it *appends* a fresh leaf per empty terminal
  (§70 §2). The golden's own tree has **4454** empty terminal cells but its `Leaves` array holds only
  **762**, with node `iLeaf` slots reusing them (leaf 737 alone is referenced by 241 tree terminals).
  The array is deterministically non-§70-faithful: a re-build with a **far more generous** idle
  barrier (`--quiet-reads 30 --rebuild-min-seconds 90`, rebuild idle after 91 s / 32 quiet reads)
  produced a **byte-identical Model body** (762 leaves / 76488 verts / 599 vectors; differs only at
  header byte 37 = GUID/timestamp). So this is **NOT the barrier-timing truncation §89 hypothesised**
  ("762 leaves = a truncated Leaves array is the tell") — a longer wait does not change it. It is a
  deterministic property of the headless `MAP IMPORT→REBUILD→SAVE` leaf production; whatever it is, it
  is not the 1:1 array §70's disassembly and the shipped map both show.
- **`Verts/Vectors +24%` splits in two.** `Vectors` +24 % is a **real** native over-production
  (shipped 596 and golden 599 AGREE; native 745). **⚠️ ROOT-CAUSED in §10 (2026-07-19): the cause is
  extra TEXTURE AXES on native's differently-partitioned surfaces, NOT node-plane normals** (node
  planes are stored inline and never enter the `Vectors` array; surf normals are in fact identical
  across all three, 257/257/257). The `~~extra node-plane normals~~` claim in the rest of this bullet
  is superseded by §10 — including the stale `~~native uses 261 distinct vNormals, shipped 260~~`
  (those are surf-REFERENCE counts pre-dedup; the distinct-vector count is 257 for all three). It is
  not fp near-dupes (only 6 merge at 1e-3).
  `Verts +24 %` is **mostly inflated by the same corrupt golden** (golden verts/node 12.11 is
  abnormally low vs shipped 15.90 — its vert pool is under-built too); against the trustworthy
  shipped map native `Verts` is only +15 % and is largely node-count-driven (native 6425 nodes vs the
  incrementally-authored shipped map's 5188). ✅
- **Action:** there is **no leaf over-production to fix in native**. The fix belongs to the GOLDEN
  PIPELINE (make UnrealEd emit a complete `Leaves` array before it is used as a parity basis) and to
  the parity harness (assert refs/leaf == 1.0 on any golden; `bsp_health_check.py` only range-checks
  `iLeaf`, so it passed the corrupt golden). The genuine tree-fidelity residual is `Vectors +24 %`
  and the zone count (see §4/§5) — both small and separate.

---

## 1. Method & the reversal (✅)

Decode both level Models (`harness/leaf_structure_diff.py`, on `uedctl.native.umodel`) and, for
every model, walk the front/back tree (engine order: FRONT = `iChild[1]` = `i_back`, BACK =
`iChild[0]` = `i_front`; coplanar `iPlane` chain followed only for reachability), counting empty
terminal child slots (`child == -1 && iLeaf >= 0`), and separately count the distinct `iLeaf` values
vs the `Leaves` array length.

The task framed native `Leaves 2759` as a 3.6× over-production vs the golden's `762`. The decode
shows the **opposite** relationship: native has *fewer* empty terminal cells than the golden (2759 vs
**4454**). The `Leaves`-array numbers diverge only because native gives every empty cell its own leaf
(2759 cells → 2759 leaves) while the golden's array holds just 762 entries that its 4454 cells
**reuse** (refs/leaf 9.45; max reuse: one leaf shared by 241 tree terminals; iLeaf-in-storage-order
is non-monotonic, descending-step fraction 0.20 vs the shipped map's clean 0.97).

## 2. Why the golden's `Leaves` array is provably corrupt (🔬 + ✅)

Three independent facts, any one damning, together conclusive:

1. **UED22's Pass-A `AssignLeaves` (`Editor.dll` `0xa7760`) is 1:1 by construction** (§70 §2,
   instruction-level): DFS the tree, and *at every empty terminal child append a new
   `FBspLeaf{iZone = Leaves.Num, …}` and set `node.iLeaf[side]` to its index*. Every empty terminal
   cell is its own leaf — a completed Pass A yields exactly `#empty-cells` leaves and refs/leaf ≡ 1.0.
   Nothing downstream compacts `Leaves`: Pass C compacts *zone* labels, not leaves; `bspRefresh`/
   `bspCleanup` GC nodes/points, not the leaf array (§70 pipeline table).
2. **The real shipped map confirms 1:1 at real-level scale** — `03_NYC_UNATCOHQ.dx`: 2266 leaves,
   2266 empty cells, refs/leaf 1.00. So a correct UnrealEd build of a UNATCO-scale level has ~2266
   leaves, not 762.
3. **The golden's own tree contradicts its own array** — 4454 empty terminal cells but a 762-entry
   `Leaves` array (refs/leaf 9.45). That is arithmetically impossible for a completed §70 Pass A.
   And it is **deterministic**, not a save-time race: the generous-barrier re-build (§0) yields a
   byte-identical Model body, so a longer wait does not "complete" it. The headless
   `MAP IMPORT→REBUILD→SAVE` path this golden uses (`build_ued_golden.py`, `ed.rebuild()`)
   deterministically emits a `Leaves` array that is not the §70-faithful 1:1 enumeration the shipped
   map carries — the leaf production diverges (a leaf array from an earlier/internal build state, or a
   headless `MAP REBUILD` that does not run the full `TestVisibility` leaf-enum the same way; the
   exact editor-internal reason is a golden-pipeline investigation, not a native concern). It passed
   §89's `bsp_health_check.py` only because that check asserts `iLeaf ∈ [-1, len(Leaves))` (max iLeaf
   761 < 762) — never per-cell uniqueness. **Corroborating tell:** the golden's verts/node (12.11) is
   far below the shipped map's (15.90), i.e. its `Verts` pool is under-built too — consistent with the
   same headless build under-running the `TestVisibility` Pass-D orphan-vert re-emit (§70 §11, which
   inflated the castle's verts 4405→10518). So BOTH the golden's `Leaves` and `Verts` sections are
   deterministically not editor-faithful and must not be used as parity targets.

**Native (2759, refs/leaf 1.00) faithfully reproduces UED22's Pass-A policy.** On the castle both
native and the golden are 1:1 (384 = 384) because a small/simple level's batch build captures cleanly
— which is exactly why the gap only appeared at UNATCO scale (a longer rebuild whose `Leaves`
serialization the fixed-barrier golden truncates).

## 3. Pipeline localization

- **Native side — nothing to fix.** Leaf enumeration is `zones::assign_leaves` (Pass A, `zones.rs`
  ~L44–82): one leaf per empty terminal, faithful to §70 §2. It is correct in policy and count.
- **Golden pipeline — the defect (deterministic, NOT the barrier).** `build_ued_golden.py`'s headless
  `MAP IMPORT→REBUILD→SAVE` deterministically emits a non-1:1 `Leaves` array (and an under-built
  `Verts` pool). This was tested and is **not** a `_wait_idle` timing race — a 90 s / 32-quiet-read
  barrier gives a byte-identical Model body. The `--quiet-reads`/`--rebuild-min-seconds` knobs added
  this session are how that was proven; they do **not** fix the leaf array. The real fix is either to
  root-cause why this headless rebuild's leaf/vert production diverges from §70 (does `ed.rebuild()`'s
  `MAP REBUILD` run the full `TestVisibility` leaf-enum + Pass-D vert re-emit? — a driver/verb
  investigation) or to treat `Leaves`/`Verts` as un-gradeable against this golden and fall back to the
  shipped map + native-internal §70 invariants for those two sections.
- **Parity harness — a blind spot.** `bsp_health_check.py` range-checks `iLeaf` but not refs/leaf.
  Add an assertion `distinct(iLeaf) == len(Leaves)` (refs/leaf == 1.0) so a truncated golden can
  never again be mistaken for a native defect.

## 4. `Verts / Vectors +24 %` — attribution (✅)

`ground_truth_bytediff.py` + `leaf_structure_diff.py`, native vs golden vs shipped:

| quantity | native | shipped | golden | native vs shipped | native vs golden |
|---|---:|---:|---:|---:|---:|
| Nodes | 6425 | 5188 | 6314 | +24 % | +1.8 % |
| Vectors | 745 | 596 | 599 | **+25 %** | +24 % |
| Verts | 94766 | 82487 | 76488 | **+15 %** | +24 % |
| Verts / node | 14.75 | 15.90 | 12.11 | — | — |

- **`Vectors` +24 % is REAL and robust** (596 / 599 / 745), but **⚠️ this bullet's attribution is
  OVERTURNED by §10 (2026-07-19).** It is **NOT** node-plane normals and **NOT** the §80 leak-repair
  flipped planes: node planes are serialized inline and never enter the `Vectors` array, and the bound
  node reuses the parent's `iSurf` (allocates no vector). The excess is **entirely texture axes**
  (`vTextureU` +105, `vTextureV` +50; surf normals identical at 257). The `+82` extra negation pairs
  are extra negated **texture-axis** pairs (native 248 vs golden 166), not plane/normal pairs (equal:
  170 vs 168). Root: native's **extra surfaces** from the less-merged CSG partition (§80) carry a wider
  set of texture-mapping vectors; matched surfaces agree exactly. See §10 for the decode.
- **`Verts` +24 %-vs-golden is largely a GOLDEN artifact.** The golden's verts/node (12.11) is far
  below the shipped map's (15.90) — its Pass-D orphan-vert re-emit (§70 §11, +6113 verts on the
  castle) is evidently under-captured too, the same partial-build truncation as its `Leaves`. Against
  the shipped map native `Verts` is only **+15 %**, and native's verts/node (14.75) is *below*
  shipped's — i.e. the total tracks native's higher node count (batch vs incremental), not an
  independent T-junction/weld blow-up. On the castle native `Verts` is already byte-near-exact (16163
  = editor, §70 §12), so there is no scale-independent vert defect; the UNATCO `+24 %-vs-golden`
  overstates the gap.

## 5. Zones 9 vs 7

Native 9 vs golden 7 (+2). This is the residual of §70 §13.3 **"Cause 2 — native's CSG tree is
geometrically shattered"** (already filed): on native's own tree whole regions of empty space are
portal-disconnected (extra/entombed leaves, boundary faces classified solid where the editor keeps
them open), so the zone flood over-fragments. It lives in the CSG pipeline (`bspcsg.rs`/`csg.rs`/
`passes.rs`), not the flood, and is a small residual here (+2) — the BlockPortal flood fix (§13.2)
already made the flood editor-exact *on a correct tree*. Not a leaf-specific issue.

## 6. Scope & recommendation (highest-leverage first)

1. **Do NOT chase native "leaf over-production" — there is none.** Native's Pass A is correct.
   *(effort: 0; the premise was a corrupt-golden artifact.)*
2. **Gate the golden + investigate its leaf/vert production** so the false gap can't recur:
   (a) add a `distinct(iLeaf) == len(Leaves)` (refs/leaf == 1.0) assertion to `bsp_health_check.py`
   and REJECT the current cached goldens for `Leaves`/`Verts` parity — they deterministically fail it;
   (b) root-cause why the headless `ed.rebuild()` path emits a non-1:1 `Leaves` array + low-vert pool
   (does `MAP REBUILD` run the full `TestVisibility` leaf-enum + Pass-D vert re-emit headless, or is a
   second verb / `LIGHT APPLY`-adjacent step needed?). A generous barrier is NOT the fix (proven
   byte-identical). Until then, grade `Leaves`/`Verts` against the shipped map + native's §70
   invariants, not this golden. *(effort: ~1 h for (a); a bounded editor-driver investigation for
   (b).)* Highest-leverage: every `Leaves`/`Verts` read against this golden is otherwise invalid.
3. **`Vectors +24 %` (real, ~+150 vectors)** — a genuine but small tree-fidelity residual. Attribute
   precisely between the §80 leak-repair flipped-plane nodes and the less-merged CSG partition, then
   decide (the leak-repair is a synthetic collision patch, not an editor pass; its flipped planes are
   a known non-faithful artifact — reducing them ties into the deferred incremental-`bspBrushCSG` port,
   §80 §5). *(effort: medium; couples to the byte-identity `bspBrushCSG` port already on the board.)*
4. **`Zones +2` / `Verts`** — no new work; both already tracked (§70 §13.3 CSG-shatter; Verts is
   node-count-driven + golden-inflated). Re-measure Verts against the *re-cached* (un-truncated)
   golden once (2) lands.

## 7. Reproduce
```
cd Tools/uedctl
# the decode that reverses the headline (uses the §89 cached builds under _scratch/uedgolden/)
.venv/bin/python dev/docs/spikes/2026-07-15-native-materialize/harness/leaf_structure_diff.py \
  _scratch/uedgolden/Native_unatco.dx _scratch/uedgolden/UEDGolden_unatco_world.dx
# cross-check the shipped map is 1:1 (refs/leaf 1.00) like native, unlike the golden:
#   decode 03_NYC_UNATCOHQ.dx the same way (see this section's tables)
# a fuller-barrier golden rebuild (bounded background job — the editor wedges silently).
# RESULT: byte-identical Model body to the 8-read golden (762 leaves) -> proves the leaf defect is
# deterministic in the build path, NOT a barrier-timing truncation.
.venv/bin/python -u dev/docs/spikes/2026-07-15-native-materialize/harness/build_ued_golden.py \
  --trunk _scratch/unatco/uedctl/maps/unatco --out _scratch/uedgolden/UEDGolden_unatco_world_gen.dx \
  --world-only --no-light --overwrite --quiet-reads 30 --rebuild-min-seconds 90
```

## 8. Follow-ups (to inbox)
- **[spike/chore] Gate + root-cause the golden's leaf/vert production.** Add a `refs/leaf == 1.0`
  assertion to `bsp_health_check.py` (rejects the current cached goldens, which deterministically
  fail it), and investigate why the headless `ed.rebuild()` path emits a non-1:1 `Leaves` array +
  under-built `Verts` (a generous barrier does NOT change it — byte-identical body; so it is a
  build-path/verb issue, not timing). Until fixed, `Leaves`/`Verts` are un-gradeable against this
  golden — use the shipped map + native's §70 invariants. (This section's whole finding.)
- **[note] The "native Leaves 3.6×" board headline is retired** — native's leaf policy is
  correct (1:1, editor-faithful, matches the shipped map). Re-point the remaining tree-fidelity chase
  at `Vectors +24 %` (real) and the §13.3 CSG-shatter zone residual.

---

## 9. FIX — the corrupt golden was a LEAN headless rebuild; `MAP REBUILD` never runs the leaf pass (✅🔬 2026-07-19)

§0–§8 pinned that the golden's `Leaves` array is corrupt (762 leaves reused across 4454 empty cells,
refs/leaf 9.45) and DETERMINISTIC (not a barrier-timing truncation), and deferred the exact
editor-internal reason as "a golden-pipeline investigation." **That investigation is now closed and
the golden is fixed.**

### 9.1 The decisive signature: leaves assigned to an EARLY tree, then subdivided (✅)
Decoding the corrupt golden's node array (not just the tree-walk of §1): of the **7204** node `iLeaf`
slots that are `>= 0`, only **4454 sit on TERMINAL nodes** (`child == -1`) — **2750 sit on
NON-terminal nodes** (`child != -1`). A fresh Pass-A `AssignLeaves` sets `iLeaf` **only** at empty
terminal children (§70 §2), so a non-terminal node carrying an `iLeaf` is impossible for a *completed*
enumeration. The only way to get 2750 of them is: `AssignLeaves` ran when the tree had ~762 empty
cells, and a LATER pass **subdivided** those cells (the old terminals became internal, their new
children inheriting the parent's stale `iLeaf` by copy) **without re-running `AssignLeaves`**. So the
762-entry array is a *stale snapshot* from before the final subdivision — exactly consistent with the
under-built `Verts` pool (the Pass-D orphan re-emit, part of the same visibility pass, also never ran).

### 9.2 Root cause: `MAP REBUILD` is NOT a full rebuild — the leaf pass is gated on the `ZONES` keyword (🔬 Editor.dll / unrealed.exe decode)
The editor exposes TWO different rebuild code paths (UED22 exec tokens are **UTF-16LE**, which is why
prior ASCII `strings` scans found none):
- **`MAP REBUILD`** (the harness's old `ed.rebuild()`) → the MAP-exec handler at `Editor.dll 0x65a40`
  parses `VISIBLEONLY=` and calls `UEditorEngine::Rebuild` (MAP-exec vtable slot **0xec**). This runs
  `csgRebuild` + `bspBuild` but leaves the **paste-era `Leaves` array stale** — it does NOT re-run the
  visibility/leaf enumeration on the final tree.
- **`BSP REBUILD <LAME|GOOD|OPTIMAL> [OPTGEOM] [ZONES]`** → the SEPARATE parser at `Editor.dll 0x65220`
  (all its keyword literals — `REBUILD/LAME/GOOD/OPTIMAL/BALANCE/PORTALBIAS/ZONES/OPTGEOM` — live as
  UTF-16 strings at `0x100e8b3c..`). Here the **visibility/leaf/zone pass** (`TestVisibility` →
  `AssignLeaves`, vtable slot **0x264**, call at `0x65482`) runs **ONLY when the `ZONES` keyword is
  present** — it is skipped by `je 0x1006548a` otherwise; likewise the Pass-D vert re-emit
  (`bspOptGeom`, slot 0x218 at `0x654d9`) runs only under `OPTGEOM`. The GUI "Rebuild Geometry" dialog
  (unrealed.exe `0x84b60`) builds its command by concatenating `"BSP REBUILD"` + optional `" OPTGEOM"`
  (checkbox "Optimize Geometry") + optional `" ZONES"` (checkbox "&Build Visibility Zones") — so a
  full GUI rebuild issues `BSP REBUILD <opt> OPTGEOM ZONES`.

`MAP REBUILD` == `BSP REBUILD GOOD` **with no `ZONES`/`OPTGEOM` keyword** ⇒ AssignLeaves never re-runs
on the finished tree ⇒ the on-disk `Leaves` stays the stale incremental-paste array. On the CASTLE the
small batch happened to leave the paste-era leaves 1:1 with the final tree (384=384), which is why the
defect only surfaced at UNATCO scale.

### 9.3 The fix: a TWO-command full rebuild (✅ live-verified)
`BSP REBUILD … ZONES` **alone gives an EMPTY Model** (nodes=0) — it operates on the already-CSG'd
model and never runs `csgRebuild`, and after `MAP NEW`+paste the world model is empty until
csgRebuild. So the faithful sequence is **two commands in order**:
```
MAP REBUILD                        # csgRebuild + bspBuild  (build the world Model from the pasted brushes)
BSP REBUILD OPTIMAL OPTGEOM ZONES  # re-optimize + AssignLeaves(final tree) + Pass-D vert re-emit + zones
```
`build_ued_golden.py` now defaults `--rebuild-cmd` to exactly this (`;`-separated, run in order), and
`bsp_health_check.py` now ASSERTS **refs/leaf == 1.0** (distinct(iLeaf)==count(iLeaf>=0)==len(Leaves)
AND zero iLeaf on non-terminal nodes; exit non-zero on violation), so a lean-rebuild golden can never
again be silently trusted.

### 9.4 The corrected golden — refs/leaf 1.0, and the headline deltas RE-MEASURED (✅)
UNATCO world-only unlit, fresh golden `UEDGolden_unatco_world_zones.dx` (two-step full rebuild) vs
`Native_unatco.dx`:

| metric | native | **corrected golden** | corrupt golden | shipped `03_NYC` | native vs corrected |
|---|---:|---:|---:|---:|---:|
| **Leaves** | 2759 | **2934** (refs/leaf **1.00**) | 762 (9.45 ✗) | 2266 (1.00) | **−6.0 %** (was "3.6×") |
| **Verts** | 94766 | **98152** | 76488 | 82487 | **−3.5 %** (was **+24 %**) |
| Nodes | 6425 | 6859 | 6314 | 5188 | −6.3 % |
| Points | 10744 | 11499 | 10752 | 9671 | −6.6 % |
| **NumZones** | 9 | **9** | 7 | 7 | **EQUAL** (was +2) |
| Surfs | 3698 | 3616 | 3616 | 3589 | +2.3 % |
| **Vectors** | 745 | **599** | 599 | 596 | **+24.4 %** (UNCHANGED — real) |

**The headline reverses completely.** Against a COMPLETE golden native does **not** over-produce
leaves (it is *within 6 %*, and both are 1:1) and does **not** over-produce verts (native is *below*
the golden, −3.5 %). The old "+24 % Verts" was **entirely** the corrupt golden's under-built vert pool
(now golden verts/node 14.31 ≈ native 14.75), and the "+2 Zones" was the corrupt golden under-zoning
at 7 (the complete golden zones to **9 = native exactly**). The **only** real native tree-fidelity
residual is **`Vectors +24 %`** — robust across corrupt AND complete goldens (both 599) and the
shipped map (596). **⚠️ Its cause is ROOT-CAUSED in §10 and is NOT what this sentence says:** it is
extra **texture axes** on native's differently-partitioned surfaces, **not** node-plane normals (which
are stored inline and never enter the `Vectors` array) and **not** the §80 leak-repair flipped planes
(which add zero vectors). The chase still couples to the incremental-`bspBrushCSG` port, but via the
surface set, not the plane normals — see §10.

### 9.5 Generalization (✅)
The castle golden **stays structurally correct** under the two-step: `UEDGolden_castle_world_zones.dx`
= 615 leaves, refs/leaf **1.00**, valid BSP (0 iLeaf-on-internal). Note the castle golden's counts
rise vs the shipped map (615 leaves / 1649 nodes vs shipped 384 / 1156) because the `BSP REBUILD
OPTIMAL` pass **re-partitions** — ANY `BSP REBUILD` rebuilds the BSP afresh, so the single-`MAP
REBUILD` castle golden's *coincidental* 384-match to the shipped map is not preserved. This is fine:
the castle's byte-parity basis is the **shipped `Test_Castle.dx`** (native byte-near-exact to it, §70
§12), not this golden; the golden is the UNATCO-scale basis where no clean shipped-vs-trunk compare
exists. If exact node-count nearness to native/shipped is wanted over a maximal-quality rebuild,
`--rebuild-cmd "MAP REBUILD;BSP REBUILD GOOD ZONES"` (GOOD, no OPTGEOM) is the knob to trade down.

---

## 10. `Vectors +24 %` ROOT-CAUSED — it is TEXTURE AXES on extra surfaces, NOT leak-repair plane normals (✅ decode-proven, 2026-07-19)

§4 / §9.4 left `Vectors +24 %` (UNATCO: native **745** vs golden **599** vs shipped **596**, ~+146)
as "the one real tree-fidelity residual" and hypothesised it was **extra node-plane normals from the
§80 leak-repair grafting flipped planes** (`+82 extra negated-plane pairs`). **Full decode of all
three Models OVERTURNS that attribution.** Harness: `harness/vectors_attribution.py` (reproduces every
number below). **Diagnostic only; no `.rs` changed.**

### 10.1 Node planes are NOT in the `Vectors` array at all (✅ — kills the primary hypothesis)
`FBspNode` serializes its split plane **INLINE** as four `float`s (`model_write.rs::put_node` writes
`n.plane.x/y/z/w` directly; the golden/shipped use the identical UE1 layout). The `Vectors` array is
referenced **only** by `FBspSurf` (`vNormal`, `vTextureU`, `vTextureV`) — never by a node plane. So the
§80 leak-repair (`build.rs::bound_leaked_solid_leaves`), whose bound node carries a **flipped parent
plane**, adds that plane inline to the node and **REUSES the parent's `iSurf`** (`insert_solid_bound`
copies `n.i_surf`, allocates no surf, calls no `bsp_add_vector`) — it contributes **exactly zero**
vectors. The whole "flipped-plane → extra vector" chain is impossible by construction.

### 10.2 The +146 excess is ENTIRELY texture axes; surf normals are identical (✅)
Distinct vectors by surf role (1e-3 key), native / golden / shipped:

| role | native | golden | shipped | native excess |
|---|---:|---:|---:|---:|
| surf **vNormal** | 257 | 257 | 257 | **0 — identical** |
| **vTextureU** | 298 | 193 | 191 | **+105** |
| **vTextureV** | 285 | 235 | 231 | **+50** |
| **total Vectors** | 745 | 599 | 596 | **+146** |

The surf-normal set is *bit-for-bit the same size* across all three. The entire residual is extra
**texture-mapping axes** (`vTextureU`/`vTextureV`). *(The +105 texU and +50 texV columns don't sum to
+146: ~99 native vectors serve a dual role, e.g. a value used as both a U axis on one surf and a V on
another, so the role sets overlap and the totals aren't additive. The headline — normals excess 0, all
excess in texture axes — is exact; the per-role deltas are upper bounds.)*

### 10.3 The extra negation pairs are texture axes, not plane/normal pairs (✅ — re-attributes §4's "+82")
§4's "`+82` extra exact-negation pairs" is real in count but MIS-ATTRIBUTED. Splitting the negation
pairs by role: pairs among **normals** are native **170** / golden **168** / shipped **169** (equal);
pairs among **texture axes** are native **248** / golden **166** / shipped **162**. The +82 is +82
extra negated **texture-axis** pairs — nothing to do with node/plane normals (which are equal, and
aren't in the array regardless).

### 10.4 It is NOT a texture-axis sign/convention bug — matched surfaces agree exactly (✅)
Define a **geo-key** = a surface's `(pBase, vNormal)` (position + normal, rounded to 0.01 / 0.001) —
i.e. a physical face location, *ignoring* texture mapping. Two surfs with the same geo-key are "the
same face" in both models. Matching native surfs to golden surfs by geo-key, **2829** surfaces are
common; on these, native's `vTextureU` is **equal to golden's in 2766, negated in 0** (63 differ by
neither — "other"); `vTextureV` **equal in 2760, negated in 0** (69 "other"). So native does **not**
flip or mis-orient texture axes on shared faces — deduping/canonicalising `n` vs `−n` would be wrong.
The bulk of the excess axes live on native's **EXTRA surfaces** (native-only geo-keys): distinct
`vTextureU` on native-only surfs = **130** (golden-only = 40), `vTextureV` = **85** (golden-only = 41).
Those extra axes are mostly **collinear with a golden direction at a different texture scale**
(114/125 native-only texU), i.e. genuine mapping diversity carried by native's differently-partitioned
surface set — not fp drift and not a scale formula bug (scale ratios scatter 0.1–36 with a mode at 1.0,
across 283 surfs / 27 textures). **A smaller, not-fully-decoded slice sits on COMMON surfaces:** 63
texU + 69 texV shared faces where native and golden pick *different* (neither equal nor negated)
texture axes, and native carries +16 distinct texU / +6 texV more than golden on common geo-keys. That
~20-vector slice is a candidate for a more localized lever (a `bspMergeCoplanars` / surf-dedup ordering
difference on shared faces) but is not root-caused here and is far too small to reach the 599 target on
its own.

### 10.5 The editor itself does NOT fold n/−n (✅ — kills the proposed "dedup n/−n" fix)
The golden itself has **310** vectors that have an exact-negation partner in its pool, and the shipped
map **307** — UnrealEd's `bspAddVector` keeps `n` and `−n` as **separate** `FVector`s
(`THRESH_NORMALS_ARE_SAME` is an exact-match tolerance, not a sign fold). *(These 310 are counted over
the whole pool; the by-role figures in §10.3 — 168 among normals, 166 among texture axes — are
computed on role-restricted key sets and double-count dual-role vectors, so they are separate metrics,
not a partition of 310.)* Deduping `n/−n` in native would drop the ~150 legitimate negation pairs the
editor keeps, take it **below** 599 (diverging from the editor), and **break the castle's 26-vector
byte-parity**. The task's two proposed mechanisms — "dedup n/−n" and "don't graft the redundant flipped
plane" — are therefore **both decode-disproven**: the first contradicts the editor's convention, the
second targets a node plane that never enters `Vectors`.

### 10.6 True root + where the fix lives (STOP — outside `bspcsg.rs`'s vector emission)
`bsp_add_vector` (`bspcsg.rs`) is behaving correctly: `UNREF-vectors == 0` (every vector is a real surf
axis), matched surfaces dedup identically, and the pool composition mirrors the editor's. The residual
is a **downstream consequence of native emitting a different/larger surface set** than the editor — the
**§80 less-merged CSG partition** (`csg.rs` leaf-filter → `passes.rs` `bspMergeCoplanars` → `bspoptgeom.rs`
single from-scratch `SplitPolyList`, vs the editor's incremental `bspBrushCSG` + un-repartitioned
semisolid layer). The bulk of the excess (~125 native-only texU axes on native-only surfaces) has **no
localized `bsp_add_vector` fix** — it cannot be reached without changing the surface partition. (A
small ~20-vector slice on COMMON surfaces, §10.4, *might* yield to a more localized `bspMergeCoplanars`
/ surf-dedup change, but is far too small to matter for the 599 target and is not root-caused here.)
Closing `Vectors` therefore **couples to the incremental-`bspBrushCSG` port**
(§80 §5, N-2+, already on the board) — the *same* work that closes the node/surf topology — and is not a
separate small win. Native Nodes are already **below** the corrected golden (6425 vs 6859), so there is
no "extra nodes from extra planes" to close here either; the §4 "extra planes ⇒ extra nodes" framing
does not hold against the corrected golden.

### 10.7 Reproduce
```
cd Tools/uedctl
.venv/bin/python dev/docs/spikes/2026-07-15-native-materialize/harness/vectors_attribution.py \
  _scratch/uedgolden/Native_unatco.dx _scratch/uedgolden/UEDGolden_unatco_world_zones.dx \
  /home/neob91/Games/LutrisDX/drive_c/DX/Maps/03_NYC_UNATCOHQ.dx
```
