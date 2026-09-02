# Spec — Stage 2: decode + close the first UNATCO CSG surf divergence (`Brush755` dome subtract)

**Status:** LANDED (2026-07-19 08:58 UTC). The `bspValidateBrush` coplanar surf-link phase is ported
into `bspcsg.rs::bsp_brush_csg` (finalized-normal gate, exact-axis kept, temp-space link remap).
Dome CAP closed: UNATCO N=105 `only-native` 28→20; castle byte-identity UNCHANGED (485/1156/26/43.04%);
N=104 clean. Regression `bspcsg::tests::validate_brush_links_fuses_coplanar_same_facing_faces`; two
cold reviewers resolved (index-space desync on a dropped face + pre-finalize-normal gate — both fixed).
Durable choice: `decisions.md` 2026-07-19 08:58 UTC. **Remaining:** the 20 `only-native` at N=105 are
the sloped (non-coplanar) facets — a separate sub-class; re-bisect for Stage 3. Ephemeral per-feature
scratch. **Date:** 2026-07-19. **Parent:** spike §92 (esp. §8 stage-0 basis, §9 stage-1 pin) and §82
§10.6/§10.7 (the castle divergence + the gdb `bspAddNode` oracle method this reuses).

## 0. What is pinned (read §92 §9 first)

Native's real-level (UNATCO) build over-produces surfs vs UnrealEd's build of the SAME trunk. The §92
§3 residual is **+82 net surfs / +146 texture vectors, basis-independent** (invariant to the rebuild
path; confirmed against the corrected bare-`MAP REBUILD` GOOD basis in §8). Stage 1 (§9) pinned the
**FIRST brush at which native first OVER-produces a surf the editor lacks** via
`harness/unatco_subset.py` (binary search on the final `Model.Surfs` multiset, keyed
`(normal@1e-3, plane-offset@1e-2, polyflag-class)`):

- **First over-production at N=105 (N=104 clean).** Adding **brush index 104 = `Brush755`**
  (`class=Brush CsgOper=CSG_Subtract`, **78 polys** — a tessellated DOME/sphere: full azimuth ring ×
  several elevation rings of sloped facets + 9×`(0,0,1)` and 9×`(0,0,-1)` cap rings, loc
  (540,1204,276)) flips `only-native 0→28` and `only-editor 5→25` — **bidirectional**.
- The 28 over-produced surfs are the dome's facets, **dominated by 8× the single cap plane
  `(0,0,1)@268`** (native keeps 8 coplanar fragments of one dome cap where the editor merges them),
  plus one each of the sloped facet planes.

**Class:** the §82 §10.6 near-coincident-plane clip-selection + `bspMergeCoplanars`/`TryToMerge`
coplanar-merge family, GENERALIZED to a **curved subtract** (many facet planes at small mutual
angles) that the castle's box/octagon geometry never exercises. Bidirectional ⇒ **NOT closeable by
forcing a merge** (§82 §10.6 forcing regressed the castle twice; §92 §6).

## 1. The decode task (Stage 2 proper)

Reuse the editor-tree oracle (`harness/editor-tree-oracle/`, §82 §10.7) at the `golden104`→`golden105`
boundary — the two cached subset goldens already exist (`_scratch/unatco-subset/golden{104,105}.dx`):

1. **Port the oracle's subset source to UNATCO.** `editor_tree_oracle.py run N` and `native_tree_dump.py
   N` are castle-hardcoded (`subset_diff.build_editor_subset`, `castle_build.TRUNK`). Point them at the
   UNATCO trunk + the cached `unatco_subset.golden_path(N)` and the UNATCO project mounts (the
   `build_ued_golden.py` mounts logic — `resource_mounts(composed_search_dirs)` + the 20 texture
   packages OBJ LOAD). The gdb machinery (`bspAddNode` @ `0x10034e80`, `compose.override.yml` ptrace)
   is geometry-agnostic and unchanged.
2. **Capture both ADD streams for N=105** (and N=104 as the identical-prefix control): editor
   `oracle-105.log` (gdb) + native `native-105.log` (the `UEDCLI_BSPCSG_TREE_DUMP` hook), and
   `compare_trees.py` them under the plane-normalised key. Because the ADD stream is convention-stable
   (unlike the final surf set — §9), this pins the FIRST diverging incremental add: the exact dome
   facet + world plane + `SplitWithPlane` front/back routing that native resolves opposite to the
   editor.
3. **Decode that one decision against `Editor.dll`.** As §82 §10.6/§10.8 did for the castle roof:
   which near-coincident facet plane, which side classification (`THRESH_SPLIT_POLY_WITH_PLANE` /
   `…_PRECISELY` handling of a near-zero vertex distance), and which piece becomes `front` vs `back`,
   and the `TryToMerge` decision that keeps the editor's cap as 1–2 faces where native keeps 8.

## 2. The fix + gate (only after the decode)

Port the decoded `FPoly::split_with_plane` (vertex-side classification + near-zero handling + piece
routing) and/or `TryToMerge` parity into `uedcli-native/src/bspcsg.rs`, matching UnrealEd bit-exactly
for the `Brush755` facets. **HARD GATES (both must hold):**
- **Castle byte-identity UNCHANGED** — `build_native_castle.py` + `ground_truth_bytediff.py`: 485
  surfs / 1156 nodes / 26 vectors / soup 853/853 / 43.04% UNCHANGED. Any regression ⇒ revert.
- **UNATCO monotone move** — `unatco_subset.py diff 105` `only-native` drops toward 0 and the
  full-level `only-native` (534 in the subset build / the §3 174 in the canonical build) decreases; no
  new divergence introduced at a lower N (`bisect 30 105` still clean below 105).
- Two cold-reviewer gate (project `CLAUDE.md`), then commit.

## 3. Why this is one of a HANDFUL of classes, not the last fix

`only-native` grows 28→534 across N=105→762, so the dome is the FIRST of several curved/near-coincident
classes. After Stage 2 lands, **re-bisect** (`unatco_subset.py bisect 105 762` on `only-native`) for the
next first-divergence and repeat. Expect the dome/cylinder curved-subtract family, then the detail-layer
interaction (§3's semisolid +46, likely downstream of the structural set). Honest effort: weeks, one
decode+port+gate cycle per class (§92 §10).

## 4. Harness produced this pass (committed, reusable)
- `harness/unatco_subset.py` — the UNATCO subset differential + `bisect` (metric `only-native`).
- `_scratch/unatco-subset/golden{1,8,15,30,75,98,103,104,105,106,109,121,213,396,762}.dx` — cached
  editor subset goldens (gitignored scratch; rebuild via `unatco_subset.py build N`).
- `harness/build_ued_golden.py` — `--rebuild-cmd` default now bare `MAP REBUILD` (native's node basis);
  GOOD-OPTGEOM-ZONES is the opt-in clean-leaf variant (§8).
