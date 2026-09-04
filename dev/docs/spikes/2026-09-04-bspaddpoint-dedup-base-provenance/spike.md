# UED22 `bspAddPoint` dedup + node-plane base provenance — decode & measurement

**Question (as posed).** Pin the exact behavior of UED22's CSG point-dedup "spatial index" so a native
port can reproduce it, to fix the UNATCO N=8 divergence where Brush74's `x=448` face-base stays
distinct while sibling `Z=240`/`z=416` faces snap.

**Headline (overturns the premise).** The N=8 divergence is **not** a dedup / spatial-index
difference. Measured native-vs-editor at N=8: the `Points` table and every `Surf.pBase` are
**byte-identical** — `bspAddPoint` returns the **same** index on both sides. The only difference is
the **node-plane `W`** (and the CSG-soup `Polys` base) of two nodes: the editor stores the **raw
`FPoly.Base`** (`447.99985`), native stores **`Points[pBase]`** (`448.00006`). So porting the spatial
index does **not** fix N=8; preserving the raw base through repartition does. The spatial index was
still decoded in full (below) because it governs dedup fidelity in general.

Binary: `uned/UED22/{Editor,Engine}.dll`, ImageBase `0x10000000`, all addresses are VAs.
Reproduce the disasm facts: `harness/decode_dedup.py`. Reproduce the measurement:
`harness/diff_n8.py golden/native_N8.dx golden/ref_N8.dx`.

## Part A — the dedup path, fully decoded (with addresses)

### `bspAddPoint` (`Editor.dll 0x35430`)
`INT UEditorEngine::bspAddPoint(UModel* Model, FVector* V, UBOOL Exact)`:

```
Thresh = Exact ? 0.002 (THRESH_POINTS_ARE_SAME) : 0.015 (THRESH_POINTS_ARE_NEAR)   ; 0x3546b/0x35475
dist = Model->FindNearestVertex(*V, &outNearest, Thresh, &pV)                        ; 0x35498
if (dist >= 0.0 && dist <= Thresh) return pV;               // spatial HIT             ; 0x354ab..0x354b7
return AddThing(Model->Points /*+0x88*/, *V, Thresh, !GFastRebuild);                  ; 0x354d1..0x354ed
```

- The `Exact` flag picks the threshold; the surf-`pBase` add (`bspAddNode`) passes `Exact=1` → 0.002.
- On a spatial **miss** it appends via `AddThing`, whose 4th arg is `(~Editor[0x10c]) & 1` =
  `!GFastRebuild`.
- Sibling `bspAddVector` (`0x35530`) is identical over `Model->Vectors` (`+0x78`); tol 2e-5 / 4e-4.

### `AddThing` (`Editor.dll 0x31ae0`) — the appender, and its **linear** fallback
`INT AddThing(TArray<FVector>& A, FVector& V, FLOAT Thresh, INT Check)`:

```
if (Check)                                   ; 0x31ae3
  for i in 0..A.Num:                         ; per-axis BOX test, half-width Thresh
    if |V.x-A[i].x|<Thresh && |V.y-..|<Thresh && |V.z-..|<Thresh: return i;   ; 0x31b10..0x31b47
return A.Add(V);                             ; 0x31b51 (append, return Num-1)
```

This is exactly native's current linear box-scan — **but it only runs when `Check != 0`**.

### `GFastRebuild` is the editor field `Editor+0x10c`, set for the whole rebuild
`csgRebuild` (`Editor.dll 0x4a650`): `Editor[0x10c] |= 1` at entry (`0x4a6a5 or eax,1`),
`Editor[0x10c] &= ~1` at exit (`0x4aac6 and dword[ebx+0x10c],0xfffffffe`). `bspAddPoint` reads
`Check = (~Editor[0x10c]) & 1`, so **throughout `MAP REBUILD`'s CSG, `Check == 0` → `AddThing`
skips its linear scan entirely.** During a rebuild, dedup is **only** the spatial index.

### `FindNearestVertex` (`Engine.dll 0x1adeb0`) — a **stale BSP descent**, not a hash grid
`FLOAT UModel::FindNearestVertex(const FVector& V, FVector& out, FLOAT R, INT& pV) const`:

```
if (Model->Nodes.Num /*+0x5c*/ == 0) { pV set to -1; return -1.0f; }   ; 0x1adee3 / miss = 0xbf800000
return <descend Model->Nodes from node 0>(...);                          ; 0x1adf00 -> 0x1adb60
```

- `Model+0x58/+0x5c` = `Model->Nodes` (Data ptr / Num), 64-byte `FBspNode`s (Plane@+0, iVertPool@+0x18,
  iSurf@+0x1c, front/back child @+0x20/+0x24, NumVertices@+0x36). Gate: **empty Nodes → immediate
  MISS (-1.0)**.
- The recursive query (`0x1adb60`) descends by plane side within radius `R`, and per visited node
  tests **the node's surf base** (`Model->Surfs[iSurf].pBase` → `Model->Points[..]`, `+0x98`/`+0x88`)
  **and every vert-pool vertex** (`Model->Verts[iVertPool + k].pVertex`, `+0x68`) by **squared
  Euclidean** distance (a sphere, then `appSqrt`).

So the candidate set is only points **already wired into `Model->Nodes`** (as a node surf-base or a
node vert-pool vertex). `AddThing` **does not** insert the appended point into the tree, so a
just-added point is invisible to the next query — the index is **stale by construction**. The exact
MISS condition: query at distance `d` returns MISS iff `Model->Nodes.Num==0`, OR the BSP descent
(plane-side pruned by `R`) never reaches a node whose surf-base / vert-pool contains a point within
`R` of `V`.

### The dedup rule (deterministic)
During `MAP REBUILD`: `bspAddPoint(V, Exact)` **snaps** to an existing point iff the BSP descent over
the **current** `Model->Nodes` finds a node surf-base or vert-pool vertex within `Thresh`
(0.002 / 0.015) of `V`; otherwise it **adds** a new point (no linear fallback, `GFastRebuild` set).

## Part B — the N=8 measurement (the actual cause)

Built the first 8 UNATCO actors both ways (native offline + the UED22 `MAP IMPORT` reference recipe)
and diffed the world `Model` (`harness/diff_n8.py`, goldens in `golden/`):

- `Points` (76): **byte-identical.** `Vectors` (30): identical. `Surfs`/`Verts`/`Nodes` counts equal.
- Every `Surf.pBase`: **identical** — including `Surf[36].pBase = 29`, `Points[29] =
  (448.00006, 64.0001, 3e-5)`, on **both** sides. `bspAddPoint` returned the same index; the dedup
  did **not** diverge. There is **no** separate `447.99985` point in either table.
- **Only** `Node[29]` and `Node[30]` (normal `(-1,0,0)`, `iSurf=36`) differ, in plane `W` alone:

  | | native | editor (ref) |
  |---|---|---|
  | `Node[29/30].plane.W` | `-448.00006` = `-Points[pBase]·N` | `-447.99985` = `-(raw Base)·N` |

  The editor's `W` is **not** derivable from any table point. For **every other node** (including all
  `Z=240` / `z=416` faces) `ref.W == Points[pBase]·N`, i.e. native already matches.

The Brush74 `Region` flip (`iLeaf/zone`) is downstream: Brush74's origin `(448,64,416)` lies on this
plane, so the `2.16e-4` `W` error flips the BSP-descent side in `SetActorZone`. All three N=8
residuals collapse to this one `W`.

### Where native loses the raw base
Native's **incremental** `bsp_add_node` already stamps the raw base into `W`
(`bspcsg.rs:357 edpoly.base.dot(&edpoly.normal)` — the trace `harness/trace_n8.py` shows the x=448
face entering with `B=447.99985`). Native's **repartition** then reconstructs each face from the
node via `bsp_node_to_fpoly` (`bspcsg.rs:1017 base = model.points[s.p_base]`) — i.e. from the
**snapped** `pBase` — and rebuilds the plane from that, overwriting the raw `W`. The editor's
repartition keeps the raw plane on these nodes. Native's reconstruction agrees with the editor for
every node where `raw == Points[pBase]`; it diverges only where `bspAddPoint`'s snap moved the base
to a **different** point (`raw != Points[pBase]`) — which the 270°-yaw + fractional-PrePivot Brush74
is the first case of in the lockstep ladder.

## Part C — port assessment

- The change is **not** "port the spatial index." It is: carry the **raw `FPoly.Base`** (the value fed
  to `bspAddNode` during incremental CSG) into the final **node plane** and the **`Model->Polys`
  soup**, independent of `Surf.pBase` (which must keep snapping via `bspAddPoint`). Loss site:
  `bsp_node_to_fpoly` (`bspcsg.rs:1017`) and native's repartition rebuilding planes from it.
- **Regression risk / open question.** The prior "thread raw base through reconstruction" attempt
  (board `native-n8-...-base-fp-diverges`) reportedly regressed `Z=240`/`z=416`. This spike's N=8
  node diff shows those planes are **already byte-identical** native==editor, and every non-29/30 node
  has `ref.W == Points[pBase]·N`. Two readings remain consistent with the data and must be
  distinguished **before** porting:
  1. **Uniform raw** — editor uses raw base on every node; it only *looks* like `Points[pBase]`
     because `raw == Points[pBase]` everywhere except 29/30. A correctly-scoped raw-base fix then
     changes only 29/30 and cannot regress. The earlier regression would be an artifact of a **wrong
     raw-base source** (re-derived, not the true incremental `Base`).
  2. **Survivor-only raw** — repartition rebuilds most node planes from `pBase` but preserves the raw
     plane on nodes it keeps as splitters; the divergence surfaces only on a survivor with
     `raw != pBase`. A blanket raw-base fix then *would* regress the rebuilt nodes.
  Deciding this needs either (a) decoding `bspRepartition`/`bspBuild`'s per-node plane provenance
  (does it preserve survivor `FBspNode.Plane` or recompute from the reconstructed FPoly?), or (b) an
  implement-and-measure A/B (incremental-raw-base preserved through repartition vs current) against
  N=8 on all three lockstep levels. **Owner decision — do not self-authorize the approach.**
- Native **does** already reproduce the editor's node/tree structure at N=8 (only these two W values
  differ), so the raw-base carry is a value-provenance change, not a structural rebuild.
- The decoded spatial index still matters for **general** dedup fidelity: at higher N / other levels
  native's linear box-scan can snap where the editor's stale BSP descent would MISS (or vice-versa),
  producing a spurious merged/extra `Point`. It is not the N=8 cause, but a faithful engine must
  eventually reproduce both the MISSES and the HITS. Not required to close N=8.

## Files
- `harness/decode_dedup.py` — asserts every pinned disasm constant/byte-pattern against the DLLs.
- `harness/diff_n8.py`, `inspect_n8.py`, `zface.py` — the native-vs-ref Model measurement.
- `harness/trace_n8.py` — dumps native's incremental raw bases (`UEDCLI_BSPCSG_TREE_DUMP`).
- `golden/{native,ref}_N8.dx` — the two first-8-actor UNATCO builds compared above.
- `test_bspaddpoint_dedup_facts.py` — pins the disasm facts and the golden node-plane provenance.
