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

Pinning: the "editor never stores a <3-distinct-vert node" invariant has no offline fixture with
node rings to assert against today; the fix round for the Pass-D item must land the regression test
(club `Brush20` fragment set) with it.
