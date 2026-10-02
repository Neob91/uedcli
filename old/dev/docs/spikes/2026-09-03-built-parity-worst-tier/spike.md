# BUILT-parity worst tier: per-level localization + systemic mechanisms (2026-09-03)

Question: the corpus sweep's worst tier (nodes non-exact: NSFHQ04, TrainingFinal, NYC 747,
Vandenberg Gas, OceanLab Lab, Area51 Entrance, WanChai Garage, Paris Underground) — one systemic
cause or several, and what distinguishes these levels from the node-exact tier? Offline against
the cached goldens (`/tmp/uedcli-parity-cache/`) and trunks (the `breadth-parity-check` worktree's
`_scratch/uedcli-parity-cache/` — a gitignored dependency; if that worktree is gone, re-extract via
`sweep_corpus.py`), plus two live editor runs (a Paris Underground prefix search and one
discriminator golden).

## Results (detail in the board items this spike filed/extended)

1. **Kept degenerate Pass-D fragments** — a new confirmed mechanism: native ships BSP nodes with
   <3 distinct ring points; every editor golden has zero, corpus-wide. Fully explains Paris Club
   (+2), most of Chateau (+4) and Helibase (+9), 97 nodes of OceanLab's +465, and hides
   count-cancellation inside "exact" 04_NYC_Underground. Minimal offline repro: club `Brush20`.
   Board: `to-build/native-materialize/pass-d-zone-split-emits-degenerate-zero-area`.
2. **Vandenberg's post-merge sweep regression bisected** to `ccfaaa2` (the deliberate f32
   transform-chain ship), not the `8c4950f` mover content; no mover enters/leaves world CSG.
   Board: `vandenberg-count-parity-was-error-cancellation` (updated).
3. **Property census across 18 trunks** (`scan_corpus_props.py`): the node-exact tier has zero
   mirrored (det<0) brushes; every mirrored-brush level is node-non-exact. Scaled-brush count alone
   does not separate the tiers (UNATCOHQ: 90 scaled, exact). No level has a mover carrying
   `CsgOper=`; portal-poly counts don't separate tiers.
4. **Final-tree per-brush attribution is the wrong localization tool for the big levels**
   (`attrib_props.py`): divergent-brush property enrichment is ~1.0x everywhere on the diffuse
   levels — one upstream divergence smears across hundreds of brushes (same lesson as
   freeclinic08's `Brush586`). It does localize the small levels (club/chateau/helibase: 1-3
   brushes each, all scaled subtract boxes -> mechanism 1).
5. **Paris Underground live prefix search** (`pu_prefix_search.py`, log committed alongside):
   full 272-brush prefix reproduces `-108/+0/-4` exactly; first diverging brush is **n=2,
   `Brush328`** — a plain unscaled 6-poly `CSG_Subtract` overlapping `Brush1246` (the level's
   CsgOper-absent first brush, a default 256-cube at the origin; n=1 alone is exact). Native
   builds the pair 14 nodes/11 surfs/2 leaves, the editor 16/12/6: the editor keeps the cube's
   ceiling and full-height walls (and `Brush328`'s floor over the cube footprint) where native
   annihilates/trims them. The live discriminator (`pu_two_subtract_golden.py`): with `Brush1246`
   given an explicit `CsgOper=CSG_Subtract`, the editor builds 14/11/2 — exactly native (which is
   A/B-insensitive, `pu_two_brush.py`). So the shipped `CsgOper::Active`-behaves-as-Subtract model
   is refuted at the outcome level; detail in the updated
   `vandenberg-gas-csg-active-csgoper-brush-causes` board item.

## Continuation (2026-09-03): Garage + TrainingFinal localized — the two remaining un-localized under-build levels

Fresh worktree off `master` `1b8be83` (Active semantics in), native ext rebuilt. Offline baselines
vs the cached lit goldens reproduce the sweep: Garage `-68/+0/-12`, TrainingFinal `-59/+0/-11`
(nodes/surfs/leaves).

6. **06_HongKong_WanChai_Garage first divergence: `Brush21` (world-CSG idx 39), n=40 `+13/+0/+0`**
   (`wg_prefix_search.py`, log committed; n=39 exact; deltas flip sign along the prefix — n=99 is
   `+100`, full is `-68` — heavy cancellation). The whole n=40 delta is a different repartition
   ROOT splitter (sync walk: 1 origin at root; native `Y=-416` vs editor `Y=+143.99988`), and the
   causal chain is measured end-to-end, every stage live- or dump-verified (`prefix_struct_diff.py`,
   `wg_localize.py`, `ed_soup.py`, `fpolys_stage_verts.py`, `wg_merge_emul.py`/`wg_rings_cmp.py`,
   logs committed):
   - The 2-brush live case [`Brush20`, `Brush21`] (the only bbox-overlap partner: the 50-poly
     Yaw=16384 staircase Subtract preceding it; `Brush21` is a plain 6-poly Yaw=16384 Subtract) is
     **EXACT** — editor 58/32/12 == native (`wg_minimal_golden.py`). The divergence needs the wider
     prefix.
   - Pre-merge (`bspBuildFPolys` out) fragment sets for `Brush21`'s south wall (ilink 240) are
     23 == 23, index- and nv-identical — but **6 vert values differ, all on the z=0 seam: native
     SNAPPED 3 points onto `Brush20`'s coincident wall plane/pool
     (`(-288.000549,-896.001709,0)` → `(-288,-896.001953,0)`, same for x=-312/-336; Δ≈0.0005-0.0015,
     inside SAME=0.002)** where the live editor kept them on `Brush21`'s own plane (y=-896.0017).
   - Those 3 snapped points alone stall `bspMergeCoplanars`: native fuses 23→13, the editor 23→1
     (a clean 4-vert quad, live-captured). The **merge port is exonerated**: the as-ported
     emulation on the editor's own rings yields exactly 1 poly nv=4; on native's rings, 13 —
     byte-of-the-port equal (`wg_merge_emul.py`). No variant (NEAR/SAME neighbours, anchor retry,
     gate placement) moves native's 13.
   - Soup: native 371 vs editor 359 (+12, ALL on that one plane). Root `FindBestSplit` then has a
     score TIE at 48 (`f12/b8/s0` both) between native's pick (slot 108, `Y=-416`) and the editor's
     (slot 288, `Y=-143.9999`); strict `score<best` keeps the earlier slot, so the pick flip is
     purely the soup/stride difference. One flipped root → +13 nodes, cascading to `-68` full-level.
   - **Mechanism: KNOWN family — pass-1 ring-vert pooling/snap (the RING_NEAR / pool-reuse
     thread), NOT Active, NOT Pass-D (0 degenerate rings either side), NOT the f32 scale chain
     (both brushes unscaled).** First case measured end-to-end through merge → soup → root pick.
     Board: `to-build/native-materialize/garage-68-node-residual-three-pool-snapped-verts`.
7. **00_TrainingFinal first divergence: `Brush162` (world-CSG idx 686), n=687 `-107/+0/-13`**
   (`tf_prefix_search.py`, log committed; n=686 exact; n=689 `+42`, n=692 `+57`, full `-59` —
   cancellation again). The 2026-09-01 static lead (`Brush907`/`909`/`911`/`915`, idx 660-668) is
   **DISPROVEN as the first divergence — n=668 is exact.** `Brush162` is a 6-poly Yaw=32768
   `CSG_Add` sloped panel (`MainScale`/`PostScale` carry only `SheerAxis=SHEER_ZX`, rate 0 ⇒
   identity ⇒ unscaled marshal path). Its own fragment counts match (8 == 8) but the sloped surf's
   plane differs: native normal `(-5.8080545e-08, 0.66436398, 0.74740899)` vs editor
   `(-5.8080534e-08, 0.66436386, 0.74740934)` — **both sides carry a RECOMPUTED normal (authored x
   is exactly 0 pre- and post-180°-rotation; both store x≈-5.8e-8) differing by 2-6 ULPs per
   component**, pBase z differs ~8e-6, and the fragments' split verts shift 0.01-0.06. The final
   trees diverge at 69 origins (sync walk), most count-neutral ULP-plane pairs on 45°-normal
   planes (native `0.70714/0.70707` vs editor `0.70711/0.70711` — same recompute-vs-recompute ULP
   shape), net `-107`. **Mechanism: KNOWN thread — the unscaled-brush authored-vs-recomputed
   normal (`UEDCLI_BSPCSG_ADD_RECOMPUTE_NORMAL` / CalcNormal ULP) family**; TrainingFinal is its
   first localized whole-level driver. Minimal case: [`Brush663`, `Brush1`, `Brush162`] (its two
   bbox-overlap partners, both Yaw=32768) — see `minimal_golden.py` output in the board item.

## Harness

`harness/`: `scan_corpus_props.py` (per-trunk brush-property census), `attrib_props.py` (per-brush
surf/node-owner diff x property cross-tab, any cached level), `degen_census.py` (degenerate-ring
census native vs golden), `node_frag_diff.py` (per-brush fragment ring dump both sides),
`club_precise.py` / `find_splitter.py` (the club minimal repro), `prefix_search_lib.py`
(self-resolving copy of the fc08 prefix-search library), `pu_prefix_search.py` /
`pu_prefix_diff.py` / `pu_early_props.py` / `pu_two_brush.py` / `pu_two_dump.py` /
`pu_two_subtract_golden.py` (the Paris Underground search + 2-brush minimal-case tools). Scripts
self-resolve the repo root via `Path(__file__)`; the trunk-cache location is the one hardcoded
external dependency (see header).

2026-09-03 additions: `wg_prefix_search.py` / `tf_prefix_search.py` (per-level searches with an
offline `baseline` mode against the cached lit golden), `prefix_search_lib.py` grew an
editor-slot yield (waits while another `uned-*` container runs), `prefix_struct_diff.py` (native
prefix build vs the bisection's own golden: owner diffs, degenerate census, sync tree walk,
fragment dumps), `wg_localize.py` / `tf_localize.py` (bbox-overlap candidates + native pair
counts), `minimal_golden.py` (live golden for an arbitrary brush subset; `wg_minimal_golden.py`
is the Garage pair special case), `fpolys_stage_verts.py` (the 2026-08-29 stage-order gdb oracle
+ full rings for one i_link), `wg_merge_emul.py` / `wg_rings_cmp.py` (offline `TryToMerge`
emulation over the committed dumps; reproduces native 13 and editor 1 exactly). `logs/`:
`wg-n40-premerge-native.log`, `fpolys-stage-order-wg-n40-verts.log`.

Pinning: the "editor never stores a <3-distinct-vert node" invariant has no offline fixture with
node rings to assert against today; the fix round for the Pass-D item must land the regression test
(club `Brush20` fragment set) with it.
