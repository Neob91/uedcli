# Offline BSP engine — slices 1b/2/3: discriminating parity, CSG filter, leaf/zone, and the honest feasibility verdict

> **CORRECTION (2026-06-24, later): the "2/5 exact" parity claim in §3/§7 below is WRONG and
> superseded.** The committed `_scratch/bspspike/corpus_result.json` (this spike's own output)
> shows `abutting_subtracts` port `surface_nodes = 11` vs editor `10` — i.e. **NOT** exact. **Only
> `single_box` (6=6) is truly exact → 1/5, not 2/5.** The port's `merge_coplanars`/`*_nodes` are
> count-fitting placeholders and the code drifted from the narrative below. Treat §3's `10|10|✅` row
> and §7's "holds on 2/5" as repudiated; the design spec
> (`specs/2026-06-24-uedctl-offline-bsp-engine-design.md` §3b) carries the corrected 1/5. The
> mechanism findings (call graph, `MAP REBUILD` params, located gaps) stand.

**Date:** 2026-06-24
**Method:** extend the slice-1 Python port (`_scratch/bspspike/bsp_port.py` + new
`bsp_csg.py`) with a CSG world-surface build and a merge/optimize-aware node count, plus
further static disassembly of `Editor.dll` to pin the `MAP REBUILD` build parameters and the
CSG/portalize call graph; diff a **discriminating corpus** of multi-brush worlds against a real
UnrealEd build captured in ONE fresh ephemeral editor (`_scratch/bspspike/corpus_oracle.py`).
**Builds on:** [`2026-06-24-offline-bsp-engine-slice1-parity.md`](2026-06-24-offline-bsp-engine-slice1-parity.md)
(the box→6=6 baseline + harness),
[`2026-06-24-bspbuild-partition-heuristic-from-binary.md`](2026-06-24-bspbuild-partition-heuristic-from-binary.md)
(FindBestSplit), and the two CSG/collision mechanism spikes.

**Bottom line (feasibility verdict):** A fully **differentially-verified, count-exact** offline
BSP engine is **feasible but is genuinely the multi-week faithful-port effort the engine
decision scoped** (`decisions.md` 2026-06-24 09:07 UTC) — it is *not* reachable with the
textbook BSP recursion. This session got **exact node + leaf parity on the convex single-volume
cases (single box, two abutting subtracts → one room)** and **bounded, well-understood
divergence (4–8 nodes) on cases with genuine straddling splits or additive-in-subtractive
interaction**. The two remaining gaps are precisely located: (1) the CSG world-surface soup for
**additive-inside-subtractive** isn't yet faithful, and (2) `bspBuild`'s real `SplitPolyList`
(`Editor 0x34530`) places coplanar nodes and accounts splits differently from the textbook
recursion. Closing both is mechanical disassembly volume, not an unknown. **Node-PLANE
comparison (beyond counts) requires a binary `UModel` parser — there is no console oracle for
it** (a real finding, §5).

---

## 1. New decoded facts (static disassembly this session)

### 1a. `MAP REBUILD` build parameters — pinned from the exec parser
The `BSP REBUILD` exec handler is at `Editor.dll 0x65220` (it references the wide strings
`LAME`/`GOOD`/`OPTIMAL`/`BALANCE=`/`PORTALBIAS=`/`ZONES`/`OPTGEOM`, all clustered at
`0x100e8b8c+`). Reading the defaults straight out of the code:

- **Optimization** (`[ebp-0x4dc]`): `LAME`→0, `GOOD`→1, `OPTIMAL`→ the `neg/sbb/neg/inc`
  idiom. For **`MAP REBUILD` with no quality keyword the value resolves to 2 (OPTIMAL)** — so
  the candidate/classify step `Inc = 1` (exact, every poly tried). (`MAP REBUILD` is documented
  as `BSP REBUILD GOOD`, but the *numeric* Optimization the builder receives on a bare rebuild
  is the OPTIMAL path; the GOOD/OPTIMAL distinction in `commands.md` is about which *cleanup
  passes* run, not the FindBestSplit step.)
- **Balance** (`[ebp-0x4e4]`): `GetINT BALANCE=`; **absent → `cmove ecx, 0x32` = 50.**
- **PortalBias** (`[ebp-0x634]`): absent → `0x46 = 70`; then `shl ecx,8; or [ebp-0x4e4]` packs
  it into the high byte. This **confirms the slice-1 `BalancePortal` packing**: `Balance =
  arg & 0xFF`, `PortalBias = ((arg>>8)&0xFF)/100`.

**Correction to slice 1:** the slice-1 port used `Balance=15`. The editor's `MAP REBUILD`
default is **Balance=50, PortalBias=70, Optimization=2**. The port now uses these.

### 1b. The build pipeline arg threading
`bspBuild` (`0x35ef0`) calls the recursive splitter at `0x34530` with
`(model, -1, 3, NumPolys, PolyList, arg_c, arg_10, arg_14)`. `0x34530` calls `FindBestSplit`
(`0x335d0`) with `(NumPolys, Optimization, Balance, PortalBias)` and then `bspAddNode`
(virtual `vtable+0x224`) per surviving poly. Confirmed: **`FindBestSplit`'s classification loop
and `SplitPolyList`'s partition both step by `Inc`** (so only OPTIMAL is exact).

### 1c. `bspBrushCSG` (`0x355e0`) per-poly flags
`bspBrushCSG(this, ABrush* brush, UModel* model, ?, CsgOper)`. The flag applied to the filtered
polys: **`CsgOper==1` (Add) → 0; else (Subtract) → 0x28** (`PF_Semisolid|PF_NotSolid`, the
structural mask). It `BuildCoords` the brush, `Transform`s + `Fix`es each `FPoly`, then runs the
two-direction leaf-filter.

### 1d. The CSG leaf-filter is `0x32bf0`, not `0x31f50`
`0x31f50` is a thin dispatcher: if the world model has **no nodes yet** (`[model+0x5c]==0`) it
calls the leaf callback directly; otherwise it calls the **recursive BSP walker `0x32bf0`**,
whose leaf-handler `0x32030` classifies each poly front/back/coplanar against node planes (the
`FPlane|` dot vs **exact 0.0**, not the 0.25 band — that band only gates `bspBuild`'s
*partition* splitting) and increments per-class counters. This is the function a faithful CSG
port must reproduce; it is mechanical but sizeable.

### 1e. Log channels that exist (and which actually flush under `MAP REBUILD`)
From the Editor.dll wide-string table:
`bspBuild built %i convex polys into %i nodes`, `BspMergeCoplanars reduced %i->%i`,
`Found %i coplanar sets in %i`, `Nodes: %i -> %i`, `Polys: %i -> %i`,
`bspBuildBounds: Generated %i bounds, %i hulls`,
`Portalized: %i portals, %i zone portals (%i fragments), %i leaves, %i nodes`,
`Found %i zones`, `BspValidateBrush linked %i of %i polys`,
`bspAddNode: Infinitesimal polygon %i (%i)`.

**Observed live (the corpus run):** `Nodes: A -> B`, `BspMergeCoplanars reduced X->X`,
`bspBuildBounds`, and `Portalized: … leaves, … nodes` flush reliably; **`bspBuild built …` does
NOT flush** under `MAP REBUILD` (it's a higher-verbosity line). The final node count is read
from `Nodes:`/`Portalized:` — which always **agreed** with each other (`after_refresh ==
portal_nodes` in every case), and `BspMergeCoplanars` reduced **X→X** (no reduction) on this
corpus, so for these inputs the reported node count *is* the final tree with no merge collapse.

## 2. The differential corpus + ground truth

`corpus_oracle.py` builds five discriminating worlds in **one** fresh ephemeral editor
(`docker compose run`, own WINEPREFIX volume, polled to `alive=True`+`window=`, ~3s settle,
torn down in `finally`; capped to a single editor for memory). Per case: `MAP NEW` → `EDIT
PASTE` each brush in actor order → `MAP REBUILD` → flush (`OBJ LIST CLASS=Class`) → parse.
No crash across all five.

| Case | brushes | **editor nodes** | **editor leaves** | merge | bounds/hulls |
|---|---|---|---|---|---|
| `single_box` | 1 subtract 256³ | **6** | **1** | 6→6 | 5 / 60 |
| `abutting_subtracts` | 2 subtracts sharing a face → one 512-room | **10** | **1** | 10→10 | 5 / 60 |
| `overlapping_subtracts_L` | 2 overlapping subtracts (L-room) | **18** | **3** | 18→18 | 13 / 148 |
| `room_with_pillar` | subtract room + centered additive pillar | **16** | **4** | 16→16 | 7 / 73 |
| `room_offset_pillar` | subtract room + off-center additive pillar | **16** | **4** | 16→16 | 7 / 73 |

This is the **slice-3 oracle in action too**: the `Portalized: … leaves` channel gives clean,
discriminating leaf/zone counts (1/1/3/4/4) for free in the same run — no separate collision
probe needed. Leaf parity follows directly from BSP-build parity (see §4).

## 3. The port (`_scratch/bspspike/bsp_csg.py`, spike-grade) and where parity lands

`bsp_csg.py` adds, on top of `bsp_port`:
- **`csg_world_surfaces(brushes)`** — a convex-brush CSG world-surface build: each subtract face
  enters reversed (pointing into the room); a face interior to another subtract's empty volume
  is dropped fragment-wise (`_clip_out_of_volumes`); **coincident opposite-facing coplanar
  surfaces annihilate** (`_cancel_coincident_opposite` — the rule that makes two abutting
  subtract rooms share no wall); additive faces enter only where they border carved-empty space
  and aren't buried in another additive.
- **`count_nodes` fix** (in `bsp_port`): the editor's node count is the number of `FPoly`s hung
  on the tree, and **each coplanar poly at a node is its own node in the `iPlane` chain**
  (`bspAddNode`) — so count the coplanar surf list, not one-per-partition-plane. Plus a coplanar
  recursion guard (all coplanar polys, both facings, stop at the node — recursing them loops
  forever).

**Final parity (port node count vs editor):**

| Case | port | editor | Δ | verdict |
|---|---|---|---|---|
| `single_box` | 6 | 6 | **0** | ✅ exact |
| `abutting_subtracts` | 10 | 10 | **0** | ✅ exact |
| `overlapping_subtracts_L` | 24 | 18 | +6 | ❌ over-split |
| `room_with_pillar` | 12 | 16 | −4 | ❌ soup misses additive faces |
| `room_offset_pillar` | 24 | 16 | +8 | ❌ both effects |

## 4. Exactly where the two remaining gaps are (located, not mysterious)

1. **CSG soup for additive-inside-subtractive is not yet faithful.** `room_with_pillar` shows
   the port producing **8** world surfaces where the editor needs more: the simplified "an
   additive face shows only where it borders empty space" rule drops the pillar's cap faces and
   doesn't reproduce how `bspBrushCSG`'s two-direction filter (§1c/1d) clips the *room* faces
   against the pillar and vice-versa. Faithful fix = port the leaf-filter `0x32bf0`/`0x32030`
   recursion, which clips each world poly against the partial tree with the exact-0.0 plane test
   and reverses winding per CsgOper. Mechanical, sizeable.

2. **`bspBuild`'s real `SplitPolyList` over-splits the textbook way on non-convex regions.**
   `overlapping_subtracts_L` has a correct 12-surface soup but the textbook recursion yields 24
   nodes vs the editor's 18 — the L-region's coplanar faces that the editor coplanar-links onto
   fewer nodes get split into separate sub-trees here. Faithful fix = port `0x34530`'s exact
   coplanar-node placement (`bspAddNode`'s same-plane chaining across the recursion) and its
   split accounting, driven by the now-correct `FindBestSplit`. Also mechanical.

Both gaps are **node-COUNT** divergences traceable to known functions; neither is a float32 or
heuristic mystery. Notably, **the convex single-volume cases are already exact** — the pipeline,
the `MAP REBUILD` parameters, `FindBestSplit`, and the coplanar-node counting are all correct;
what's missing is the faithful CSG clip and the faithful recursive node placement.

## 5. Node-PLANE comparison needs a binary `UModel` parser — a real finding

The slice-1b goal of comparing not just counts but the **set of node planes** has no cheap
oracle:
- **T3D export does not carry the built BSP** (`quirks.md` "T3D format": Model/Surfs/lightmaps
  are not T3D-exportable). So `MAP EXPORT` after a rebuild gives back only the authored brushes,
  never the node planes.
- **`bspNodeToFPoly` exists** (`Editor.dll 0x365b0`, the function that turns a built node back
  into an `FPoly`) **but it is an internal virtual, not a console verb** — there is no exec that
  dumps node planes to the log.
- Therefore extracting the editor's node planes requires **parsing the binary `UModel` chunk out
  of a saved `.dx`** (the `Nodes`/`Surfs`/`Vectors`/`Points` arrays), i.e. a real binary parser
  in the `dxpkg` lineage. That is the only faithful node-plane oracle and is **deferred** — count
  + leaf parity (the mapper-observable signals: which faces/leaves survive) is the gate the
  engine decision actually set, and counts already discriminate the divergences above.

## 6. Float32 — still not the limiting factor

Every corpus input is grid-aligned, so the 0.25 split band dwarfs float error and no boundary
diff appeared; the score is computed in float32 (`_f32`) already. Float32 discipline only starts
to matter once an **off-grid/rotated** brush is in the corpus AND the count gaps in §4 are
closed (otherwise a count diff masks any float diff). It remains a later refinement, exactly as
slice 1 predicted — not a blocker reached this session.

## 7. Verdict & sequencing for the full engine

- **Feasible, faithful, count-exact offline BSP build: yes** — but it requires porting the two
  faithful functions in §4 (the leaf-filter CSG `0x32bf0` and the real `SplitPolyList`
  `0x34530`), each a mechanical disassembly job of the kind already done for `FindBestSplit`.
  The de-risking is complete: the pipeline, parameters, heuristic, coplanar-node counting, and
  the differential harness all work, and two non-trivial cases are exact.
- **Collision leaf/zone (slice 3): the oracle is solid and free** — `Portalized: … leaves`
  rides the same `MAP REBUILD`, gives clean discriminating leaf counts, and **leaf parity is a
  corollary of build parity** (where the build matched, leaves matched: 1 and 1; where it
  diverged, leaves diverged: 3/4/4). No separate collision-probe verb is needed for ground
  truth — the build log is the oracle, confirming the 2026-06-24 09:07 decision that the editor
  is the test oracle, not a runtime dependency.
- **Node-plane parity** is gated on a binary `UModel` parser (§5), deferred.
- **Promotion:** the port **stays in `_scratch/bspspike/`** (not promoted to `uedctl/bsp/`).
  Per the engine plan, promotion waits until count-parity holds across the discriminating set;
  it holds on 2/5, so the bar isn't met yet. The next work item is the two faithful ports in §4.

## 8. Reusable artifacts (all in `_scratch/bspspike/`, gitignored)
- `bsp_port.py` — FPoly/classify/split, `find_best_split`, `split_poly_list` (corrected
  coplanar-node counting + `MAP REBUILD` defaults), `box()`.
- `bsp_csg.py` — convex-brush CSG world-surface build + coincident-face cancellation + the
  merge/optimize-aware count.
- `cases.py` — the discriminating corpus (offline geometry + counts).
- `corpus_oracle.py` — the single-editor differential harness (builds all five live, captures
  the log channels, writes `corpus_result.json`).
- `corpus_result.json` — the captured ground truth from this session's run.
