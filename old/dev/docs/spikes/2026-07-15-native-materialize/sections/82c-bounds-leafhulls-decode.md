# 82c §12 — render `Bounds` (c0) + `LeafHulls` (cc): decode, then FAITHFUL EMIT (byte-structure parity)

> **UPDATE 2026-07-18 (IMPLEMENTED): both aux arrays are now EMITTED via a faithful `FilterBound`
> port** in `uedcli-native/src/passes.rs::bsp_build_bounds` (replacing the old empty-Bounds +
> approximate-hull stub). The port follows the byte-decoded editor algorithm in
> `re-raw-zones/bounds-and-zonelayout.md` §1.1–§1.8 verbatim. Ground-truth raw-byte state
> (`harness/ground_truth_bytediff.py`, `NativeCastle.dx` vs `Test_Castle.dx`):
>
> | section | before | after | notes |
> |---|---|---|---|
> | **Bounds(c0)** | 0 entries / 1 B | **484 / 484 entries, 12102 / 12102 B** | array length byte-EXACT; 202/484 FBoxes byte-identical, rest ≤0.005-unit float drift; **all 484 IsValid=1, no inverted extents** (OccludeBsp-safe) |
> | **LeafHulls(cc)** | 4028 ints | **3866 / 3866 ints, 15466 / 15466 B** | array length byte-EXACT; **ALL 308 hull plane-ref sets byte-IDENTICAL** to the editor; 174/308 tight-cell bboxes byte-identical, rest ≤0.005-unit drift |
>
> **The residual float drift is upstream, not in this pass.** The Bound/hull-bbox corners derive
> from `Points[surf.pBase]` (the node's Base fed to `BuildInfiniteFPoly`), and native's Point pool is
> NOT yet byte-identical to the editor's (`Points` section: native 1684 vs editor 2035 entries; the
> per-node Base is **0/1156** byte-equal — same plane, different representative vertex; Normals
> 1007/1156 equal). Same plane `(N,w)` ⇒ the split *distances* match, but the ±65536 infinite-quad
> vertices are centred on the differing Base, so clipping rounds to slightly different corners. The
> 202/484 + 174/308 that ARE byte-exact prove the port itself is correct; full float parity is gated
> on Point-pool parity (a separate section, not `passes.rs`). The **integer** content — array lengths,
> the 308 hull plane-ref sets, `iRenderBound`/`iCollisionBound` — is already byte-exact.
> **Live-verified:** `NativeCastle.dx` boots headless and renders a clean first-person frame (no
> OccludeBsp "Anomalous singularity") with the render bounds active.

> **UPDATE 2026-07-18 (§82 §10.17): the node-emit-ORDER blocker below is RESOLVED.** Native's node
> array is now positionally plane-identical to the editor (RAW `172/1156 → 1156/1156`, first
> divergence NONE) — the tree was already isomorphic and a tail-relabel of the Pass-D fragments fixed
> the linearization. So §1's "the blocker" is no longer a blocker: `Bounds`/`LeafHulls` are built
> against the editor-order tree and their array order is satisfied — which is what unblocked the
> faithful emit above.

**Status:** decode COMPLETE; both aux arrays are node-emit-ORDER-derived → byte-parity ~~blocked on
the separately-tracked node-order port~~ (node-order RESOLVED 2026-07-18, see banner above). **Date:** 2026-07-18.
**Reproduce:** `harness/bounds_leafhulls_decode.py` (loads golden `Test_Castle.dx` + fresh
`NativeCastle.dx`, prints every number below). ✅ live-verified against the two real `.dx`.

Context: §82b (§11) triaged the raw-byte body diff and listed Bounds (#6) and LeafHulls (#5) as
"tractable structural" gaps. This section decodes both fully and corrects that framing: **their
CONTENT and ARRAY ORDER are derived from the node/tree emit order**, which native and editor do
NOT share yet, so neither section can be byte-identical until the node-order grind lands. Only the
prefix `FBox.IsValid` fix (#10) was a genuinely order-independent byte win, and it is done (commit
"Native prefix: serialize FBox IsValid=0…").

---

## 1. The blocker, measured

Native vs editor node **planes match positionally only 172/1156, first diverging at node 51**
(`bounds_leafhulls_decode.py`). The plane *set* is identical (§82b), but the *order* is not. Every
fact below shows Bounds/LeafHulls are ordered by, or indexed into, that node array — so a divergent
node order forces a divergent aux array, regardless of how the aux values are computed.

## 2. Render `Bounds` (c0) — fully decoded

- **Which nodes carry a bound** (`iRenderBound != -1`): *exactly* the front/back-tree nodes with
  **≥1 child** (`iFront != -1 || iBack != -1`). Leaf nodes (both children −1) get `iRenderBound =
  −1`. For `Test_Castle`: 691 front/back-tree nodes − 207 leaf nodes = **484** bounds. The rule
  reproduces the editor's render-bound node set exactly (harness asserts `== True`).
- **`iRenderBound` numbering** = **post-order DFS index** over the front/back tree: the root (node
  0) gets the LAST index (483). So `Bounds[k]` is the k-th node *finished* in the front/back
  traversal → **the array order IS the tree traversal order**.
- **Bound VALUE** = the **tight convex-CELL bbox**, NOT the node's stored-vertex subtree bbox.
  231/484 happen to equal the vertex-subtree bbox (front+back+coplanar over `Points[Verts[..]]`);
  the other **253 are strictly LARGER** — the cell extends past the node's own clipped vertices out
  to the ancestor split planes. (This corrects the "render Bounds are the node subtree bounding
  boxes" premise: for ~half the nodes the cell bbox exceeds the vertex bbox.) The engine builds it
  by filtering the world box down the BSP (`bspBuildBounds`/`FilterBound`); reproducing the exact
  f32 corners is a faithful clip port with its own FP-exactness cost — and is still order-blocked.

**Why not just emit it anyway:** the array order is post-order DFS over native's *differently
ordered* tree, so `Bounds[k]` maps to a different node than the editor's `Bounds[k]` → not
byte-identical. Emitting non-matching bounds also re-arms the `OccludeBsp` NULL-`Bounds` crash
surface (§50) for zero byte-gate progress, so native still ships `Bounds` empty + every
`iRenderBound = −1`.

## 3. `LeafHulls` (cc) — fully decoded

- Editor and native **both** mark **308** collision nodes (`iCollisionBound != -1`) — same set size.
- Per-hull serial format is **identical**: `[plane-node refs (| 0x40000000 FLIP), …, −1, 6× i32-
  bitcast-f32 bbox]`, `iCollisionBound` pointing at the run start.
- **Two value gaps** (both real, both order-entangled):
  1. **bbox**: editor writes the **tight convex-cell bbox** (e.g. `[-295.7,-324,-32768, -48,-160,0]`);
     native hardcodes the **±32768 world box**. (Same convex-cell computation as the render bound in
     §2 — one `FilterBound` feeds both.)
  2. **plane selection**: native's `passes.rs::cull_parallel_planes` keeps **more** planes/hull
     (histogram tail to 14 planes) than the editor (capped at 10) → native emits **+162 ints**
     (1872 vs 1710 plane refs; 4028 vs 3866 total). The refs also differ in intra-hull ORDER.
- **The refs ARE node indices**, and the hull array order tracks `iCollisionBound` assignment order
  → both are node-order-derived. So even matching the plane count + tight bbox would not byte-match
  until node order matches. Native's hulls are collision-correct and the live castle is playable
  (MEMORY: collision was the native blocker); changing the plane cull risks a collision hole for no
  byte-gate gain, so it is left as-is.

## 4. Net (updated 2026-07-18 — IMPLEMENTED)

| Aux section | editor B | native B | state | residual |
|---|--:|--:|---|---|
| prefix `FBox.IsValid` | 1 | 1 | **byte-EQUAL** | none |
| Bounds (c0) | 12 102 | **12 102** | **length + structure byte-EXACT**; 202/484 FBoxes byte-equal | ≤0.005-unit float drift on 260/484 FBoxes, from Point-pool (pBase) non-parity |
| LeafHulls (cc) | 15 466 | **15 466** | **length byte-EXACT; all 308 plane-ref sets byte-IDENTICAL**; 174/308 bboxes byte-equal | ≤0.005-unit drift on 120/308 bboxes, same pBase cause |

Both aux arrays are now built by the faithful `FilterBound` port
(`uedcli-native/src/passes.rs::bsp_build_bounds`; recipe = `bounds-and-zonelayout.md` §1). The only
remaining gap is the sub-0.005-unit float drift in the FBox/bbox corners, which is **inherited from
the not-yet-byte-identical `Points` pool** (the node Base `Points[pBase]` is 0/1156 byte-equal to the
editor — same plane, different representative vertex). Closing that gap requires Point-pool parity, a
separate section; nothing further is actionable inside `passes.rs`. The port's own correctness is
proven by the 202/484 + 174/308 FBoxes that are already byte-identical.
