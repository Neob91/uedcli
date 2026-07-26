# Fix spec — `FindBestSplit` repartition params (Balance 50→12, PortalBias 70→0, OPTIMAL→GOOD stride)

**Date:** 2026-07-17. **Status:** SPEC (RE + diagnosis complete; implementer needs no further RE).
**Owner of the file to edit:** the `bspcsg.rs` agent. **Do not** touch `bspoptgeom.rs` or the Python.

## What this fixes

The native `build_geometry_bspcsg` tree diverges from the UnrealEd golden **from node[0]** and
over-fragments (full castle: native ~1543 nodes vs editor 1156). The **subset differential**
(`harness/subset_diff.py`) pins the FIRST divergence at **N=2** (World Subtract + WallBack Add): a
*pure tree-order* divergence — the multiset shows **all 14 editor node-planes present in the native
23-node tree, with 9 SURPLUS native re-fragmentation nodes and 0 only-editor planes**. So the soup is
essentially right; the **tree-builder picks the wrong splitters**.

Root cause: `find_best_split_exact` runs the exact engine score op-order but with the WRONG constants.
The repartition `FindBestSplit` actually uses **Balance=12, PortalBias=0, Opt=GOOD (stride
`NumPolys/10`)** — decoded VA-by-VA in `../spikes/2026-07-15-native-materialize/re-raw-zones/
findbestsplit-params-decode.md` (`csgRebuild → bspRepartition 0x49fc0 → bspBuild 0x35ef0 →
SplitPolyList 0x34530 → FindBestSplit 0x335d0`; the packed value is `push 0xc` ⇒ Balance=`0xc&0xff`=12,
PortalBias=`0xc>>8`=0; Opt=`push 1`=GOOD). The prior "byte-verified 50/70/OPTIMAL" was a misread.

Why it cascades: at Balance=50 the score is `50·|Front−Back| + 50·Splits`, which over-weights tree
balance. At N=2 the floor face (`|F−B|=10, Splits=0` → 500) TIES the WallBack Add side face
(`|F−B|=6, Splits=3` → 450+... = 500 on the 15-poly native soup), and native's earliest-wins picks the
WallBack side plane, which straddles and shreds the ceiling/floor/walls into fragments. At **Balance=12**
the split term dominates: floor `12·10+88·0=120` vs WallBack `12·6+88·3=336` — the floor wins strictly
(0 splits), exactly as the editor does, and the ceiling stays whole.

## The three changes to `uedcli-native/src/bspcsg.rs`

All three are needed for byte-parity; **change #1 (Balance) is dominant** (~500 of the ~500-node
over-fragmentation on the full castle; stride is ~150; PortalBias is 0-effect on the portal-free
castle but required for correctness on portal maps).

### 1. `const BALANCE: i32 = 50;` → `12`  (line ~39)
```rust
// REPARTITION FindBestSplit params (byte-verified 2026-07-17, findbestsplit-params-decode.md):
//   bspRepartition pushes BalancePacked=0xc, Opt=GOOD(1).  Balance = 0xc & 0xff = 12.
const BALANCE: i32 = 12;
```

### 2. `const PORTAL_BIAS: i32 = 70;` → `0`  (line ~40)
```rust
const PORTAL_BIAS: i32 = 0;   // = (0xc >> 8) & 0xff = 0.  No portal split-term discount.
```
(With `PORTAL_BIAS=0` the `score -= score2 * pbias` term in `find_best_split_exact` is a no-op, which
is correct — the repartition does not bias toward portal splitters.)

### 3. Add the GOOD candidate stride to `find_best_split_exact` (lines ~705–751)
The repartition is `Opt=GOOD(1)`, not OPTIMAL — so `FindBestSplit` strides candidates by
`Inc = max(NumPolys/10, 1)`, on **both** the outer candidate loop AND the inner front/back/split
counting loop (decode: `0x3369e imul 0x66666667; sar 3` = integer `NumPolys/10`; `0x336bd cmovle 1`).
Replace the two `polys.iter().enumerate()` walks with strided walks:

```rust
fn find_best_split_exact(polys: &[FPoly], balance: i32, portal_bias: i32) -> usize {
    let structural = |pf: u32| (pf & 0x28) != 0 && (pf & csg::PF_PORTAL) == 0;
    let all_structural = polys.iter().all(|p| structural(p.poly_flags));
    if polys.len() == 1 { return 0; }
    let inc = (polys.len() / 10).max(1);              // Opt=GOOD stride
    let bal = balance as f32;
    let inv_bal = (100 - balance) as f32;
    let pbias = portal_bias as f32 / 100.0;
    let mut best = usize::MAX;
    let mut best_score = f32::INFINITY;
    let mut i = 0;
    while i < polys.len() {                            // candidate stride Inc
        let cand = &polys[i];
        if structural(cand.poly_flags) && !all_structural { i += inc; continue; }
        let cand_portal = (cand.poly_flags & csg::PF_PORTAL) != 0;
        let (mut front, mut back, mut splits) = (0i32, 0i32, 0f32);
        let mut j = 0;
        while j < polys.len() {                        // inner loop ALSO strides by Inc
            if j != i {
                let p = &polys[j];
                match p.split_with_plane(&cand.base, &cand.normal, false) {
                    Split::Front => front += 1,
                    Split::Back => back += 1,
                    Split::Coplanar => {}
                    Split::Split(_, _) =>
                        splits += if (p.poly_flags & csg::PF_PORTAL) != 0 { 16.0 } else { 1.0 },
                }
            }
            j += inc;
        }
        let score2 = inv_bal * splits;
        let mut score = (front - back).abs() as f32 * bal + score2;
        if cand_portal { score -= score2 * pbias; }
        if best == usize::MAX || score < best_score { best_score = score; best = i; }
        i += inc;
    }
    if best == usize::MAX { 0 } else { best }
}
```
The score op-order, STRICT `<` tie-break (earliest wins), and the structural-skip are already correct
— keep them. Note: with `Inc>1` the returned `best` is a *strided* index; `split_poly_list` already
uses it directly as the splitter index, which is correct (the engine likewise splits on the strided
winner and partitions ALL polys — only the candidate/counting SEARCH strides, not the partition).

## Do NOT change the temp-brush BSP
`build_brush_temp_bsp` is a *different* `bspBuild` call (`bspBrushCSG 0x35b83`) with its own params
`Opt=LAME(0), Balance=0, PortalBias=0, RebuildSimplePolys=1` (evidence §4). It is a convex partition
of one brush's own faces (few/no splits regardless of Balance); leave it as-is. Only the **repartition**
`split_poly_list`/`bsp_build` path (which consumes `BALANCE`/`PORTAL_BIAS`) is wrong.

## Expected effect on `node_diff.py` (acceptance)

- **N=2 subset:** native 23 → **14** nodes, node-for-node match with the editor golden (root plane
  flips from WallBack `(1,0,0,160)` to floor `(0,0,1,0)`; the 9 surplus ceiling/floor/wall fragments
  disappear). Verified in Python on the editor's own soup (`harness/validate_params.py`: MATCH at
  N=2,4,6).
- **Full castle:** the repartition node count drops from ~1620 (old params) to **~1112** (measured via
  `harness/spl_reorder.py` on the golden's 853-poly `Model.Polys` soup), i.e. from +33% over the
  editor to ~4% UNDER — the remaining gap being TestVisibility zone splits + semisolid LOOP3 (added
  after repartition, tracked separately). `node_diff` `only_native` should collapse from 569 toward
  the low tens.

## Secondary residuals (NOT this fix — separate follow-ups, file to `board/inbox.md`)

The subset scan shows a small `only_editor` term appearing from N≥4 (2–3 planes) and native carrying a
few surplus soup faces — i.e. the CSG **soup content/order** still differs slightly from the editor's,
independent of the Balance fix:

1. **Cospatial-facing-in face kept.** At N=2 the native soup has 15 faces vs the editor's 14: native
   keeps WallBack's bottom face (`surf11`, `(0,0,-1,0)`, coplanar with the floor) where the editor
   DISCARDS it. This is the §8.3 `FilterEdPoly` coplanar `F_COSPATIAL_FACING_IN` classification nuance
   (`AddBrushToWorldFunc` drops filter 4). With the Balance fix, native-soup SplitPolyList gives 15 vs
   the editor's 14 at N=2 — this one extra face is the delta. Fix it in the coplanar classification,
   not here.
2. **`bsp_build_fpolys` walk order.** Native reconstructs the repartition soup by walking the node
   ARRAY (`for ni in 0..model.nodes.len()`); the engine's `MakeEdPolys` (0x33bb0) walks the TREE
   recursively (front/back/iPlane DFS). This reorders the soup and — because `FindBestSplit` ties are
   broken by order — can still shift deeper splits even after the Balance fix. If node-for-node parity
   is not reached after the Balance/stride fix, port `MakeEdPolys` as a tree DFS.

These are second-order; land the Balance/PortalBias/stride fix first and re-measure with
`harness/subset_diff.py scan`.
