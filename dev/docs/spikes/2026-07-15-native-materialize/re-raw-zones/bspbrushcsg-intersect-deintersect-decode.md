# RE: `bspBrushCSG` Intersect / Deintersect (`CsgOper 3/4`) — the `BRUSH FROM INTERSECTION`/`DEINTERSECTION` core — 2026-07-24

**Binary:** `uned/UED22/Editor.dll` (ImageBase `0x10000000`). Decoded with
`harness/adis.py Editor 0x<rva> 0x<len>`. Raw disassembly evidence committed alongside this doc in
`raw-intersect/*.asm`. 🔬 = disassembled this session.

**Why this exists.** The materialize port
([`bspbrushcsg-filter-decode.md`](bspbrushcsg-filter-decode.md), `sections/82`) decoded the
Add/Subtract half of `bspBrushCSG` and **deliberately skipped** the Intersect/Deintersect tail
("`CsgOper 3/4` dedup back into brush — not used by MAP REBUILD"). That tail IS the whole of the
`BRUSH FROM INTERSECTION` / `BRUSH FROM DEINTERSECTION` editor commands (the "carve the builder brush
to the world, then make it a Mover" workflow). This doc closes that gap: the two commands are now
decoded to instruction level and are **directly reimplementable** on top of the already-ported filter
machinery (`uedctl-native/src/bspcsg.rs`). It builds on the sibling doc — `bspFilterFPoly` (`0x31f50`),
`FilterEdPoly` (`0x32bf0`), `FilterLeaf` (`0x33130`), `SplitWithPlane`, the `EPolyNodeFilter`
6-way classification, `bspNodeToFPoly` (`0x365b0`), `FilterWorldThroughBrush` (`0x33250`) — are NOT
re-derived here.

**The one-line summary.** `BRUSH FROM INTERSECTION`/`DEINTERSECTION` computes a genuine boundary-rep
CSG of `builder ∩ world-solid` (intersect) or `builder ∩ world-empty` (deintersect) by (Phase 1)
clipping the **builder's** faces to the world's solid/empty field and (Phase 2) clipping the **world's**
faces to the builder's convex hull — the union of the two face sets is the result, written back into
the builder brush. Phase 2 is why the result inherits the surrounding surfaces' textures **and
PolyFlags** (the semisolid/nonsolid-mover finding, `unrealed/quirks.md` "CSG model").

---

## 0. `EPolyNodeFilter` and the "Outside" field (recap from the sibling doc)

`FilterEdPoly` descends an FPoly down a BSP, splitting at every straddled node plane, and calls a
leaf callback with an `EPolyNodeFilter F` classifying each surviving fragment. `Outside` starts at
`Model->RootOutside` and is CSG-adjusted per node (`SP_Front → Outside||IsCsg`,
`SP_Back → Outside && !IsCsg`); `FilterLeaf` maps `Outside==0 → F_INSIDE`, `Outside!=0 → F_OUTSIDE`.

```
F_OUTSIDE=0  F_INSIDE=1  F_COPLANAR_OUTSIDE=2  F_COPLANAR_INSIDE=3
F_COSPATIAL_FACING_IN=4  F_COSPATIAL_FACING_OUT=5
```

"Inside" = inside solid (for the world tree) or inside the brush hull (for the brush temp BSP);
"Outside" = the void / empty space. This polarity is the crux of the four leaf funcs below.

---

## 1. `bspBrushCSG` Intersect/Deintersect tail @ `0x35ab3` 🔬  (`raw-intersect/tail.asm`)

At `0x359cd`, `bspBrushCSG` branches `if (CsgOper==3||4) goto 0x35ab3`, skipping the Add/Subtract
LOOP-2 (`0x359e5`). LOOP-1 (shared, `0x35791`, decoded in the sibling doc) has already transformed
each builder-brush poly to world space and pushed it into `TempModel->Polys`, with the flag adjust
`Ed.PolyFlags = (Ed.PolyFlags | argPolyFlags) & ~NotPolyFlags` where **`NotPolyFlags = 0x28`
(`PF_NotSolid|PF_Semisolid`) for Intersect/Deintersect** (only Add uses 0). So the builder's OWN
transformed faces come out with solidity bits STRIPPED — the result's semisolid/nonsolid faces come
exclusively from Phase 2 (world caps), never from the builder itself. `argPolyFlags == 0` for the exec
commands.

Locals (proven by the recursion arg-shuffle at `0x33514`/`0x33547` and the tail's uses):
`[ebp-0x3cc]` = **the builder brush's `UModel`** (results land here directly); `[ebp-0x3d0]` = the
**world `Model`**; `[ebp-0x3d4]` = `CsgOper`; `edi+0xac` = `GEditor->TempModel` (the brush's polys,
then its temp BSP). `GModel` = the global `[0x101491c8]` the leaf funcs append into.

```c
// 0x35ab3 — INTERSECT/DEINTERSECT tail
Result = Actor->Brush->Brush;           // [ebp-0x3cc], the builder brush UModel
Result->EmptyModel(1,1);                 // 0x35ab9  wipe — we refill its Polys
GModel = Result;                         // 0x35af1  leaf funcs append here

// ---- PHASE 1 (0x35ac1): clip each BUILDER face to the world solid/empty field ----
for (i = 0; i < TempModel->Polys.Num; i++) {
    FPoly Ed = TempModel->Polys[i];                          // 0x35ae5 copy ctor
    FILTER_FUNC f = (CsgOper==CSG_Intersect/*3*/) ? IntersectLeaf_P1 /*0x339e0*/
                                                  : DeintersectLeaf_P1 /*0x32390*/;   // 0x35b03 cmove
    bspFilterFPoly(f, /*tree=*/World, &Ed);                  // 0x35b18  -> 0x31f50
}

// ---- PHASE 2 (0x35b3d): clip each straddling WORLD face to the builder hull ----
if (World->Nodes.Num != 0 && !(argPolyFlags & 0x28)) {      // 0x35b43/0x35b4d
    GEditor->bspBuild(TempModel, LAME/*0*/, 0, 1, 0);       // 0x35b93  brush temp BSP (convex)
    TempModel->BuildBound(); TempModel->BuildBound();       // 0x35bcf/0x35bdd
    GModel = Result;                                        // 0x35bc3 (re-assert)
    FilterWorldThroughBrush(World, TempModel, CsgOper, 0, &TempModel->Bound);  // 0x35bf8 -> 0x33250
}

// ---- FINALIZE (0x35c14) — iLink surf-share renumber over Result->Polys, then RootOutside=1 ----
//   TWO INDEPENDENT grouping passes, each walking i DOWNWARD so the j<i it compares still hold
//   their ORIGINAL values (re-disassembled 2026-07-25):
//     fwd 0x35c44: i from P1Count-1 down to 0, j in [0,i)        -> poly[i].iLink = first j with
//     bwd 0x35cb1: i from Num-1 down to P1Count, j in [P1Count,i)   the same original iLink, else i
//   P1Count = [ebp-0x3e8], captured at 0x35b23 (Polys.Num after Phase 1), so a Phase-2 cap can
//   NEVER link to a Phase-1 builder face. Then 0x35d3b sets Result->RootOutside(+0xf4)=1.
//
//   ...FOLLOWED BY a per-poly loop (0x35d3b-0x35db9) omitted from the original write-up:
//     for (i) { Polys[i].Transform(&Coords, [actor+0xd0], [actor+0x140], Orientation); // 0x100cee3c
//               Polys[i].Fix();                                                        // 0x100cee38
//               Polys[i].Actor = NULL; Polys[i].iBrushPoly = i; }                      // +0x1b4/+0x1c8
//   i.e. the result is mapped back into BUILDER-LOCAL space and its surf-link metadata reset.
//   uedctl's port deliberately stops before this (see `bspcsg.rs::intersect_brushset`): it returns
//   WORLD-space polys and KEEPS the source `iActor`/`iBrushPoly`, because the CSG core never sees
//   textures and the Python caller needs those ids to recover each face's Texture/PanU/PanV — and
//   it does its own re-centring (spec §6b) rather than the editor's fixed builder-local form.
//   Then the shared bBuildBounds epilogue. Result->Polys IS now the builder brush's polys.
```

**Phase 2 is guarded by `World->Nodes.Num != 0`** — against an unbuilt world (no BSP) intersect/
deintersect degrade to Phase 1 only (builder faces clipped, no caps). This matches the editor UX:
you must `MAP REBUILD` before the intersect trick produces a closed solid.

---

## 2. The four leaf callbacks 🔬

Each is a small SEH-framed `FILTER_FUNC(Model, iNode, FPoly* EdPoly, EPolyNodeFilter F, ENodePlace P)`.
All share the tail: `if (EdPoly->Fix() >= 3) GModel->Polys.Add(*EdPoly)` (append iff still a valid
poly; `Fix` = `[0x100cee38]`, returns vertex count after de-dup/colinear-strip). They differ ONLY in
(a) which `F` values they accept and (b) whether they `Reverse()` the fragment before appending.

| leaf | addr | phase / tree filtered through | accepts `F` | reverse? |
|------|------|-------------------------------|-------------|----------|
| Intersect P1   | `0x339e0` | builder face ↓ **world** tree  | `{1 INSIDE, 3 COPLANAR_INSIDE}`               | no  |
| Deintersect P1 | `0x32390` | builder face ↓ **world** tree  | `{0 OUTSIDE, 2 COPLANAR_OUTSIDE}`             | no  |
| Intersect P2   | `0x33ab0` | world face ↓ **brush** temp BSP | `{1 INSIDE, 3 COPLANAR_INSIDE, 5 FACING_OUT}` | no  |
| Deintersect P2 | `0x32460` | world face ↓ **brush** temp BSP | `{1 INSIDE, 3 COPLANAR_INSIDE, 4 FACING_IN}`  | **yes** |

Reading it out:

- **P1 (builder faces):** intersect keeps the builder-face pieces **inside solid**; deintersect keeps
  the pieces **in empty space**. (Exact complements: `{1,3}` vs `{0,2}`.)
- **P2 (world faces):** both keep the world-face pieces **inside the builder hull** (`{1,3,…}`), i.e.
  the caps where a world surface passes through the builder volume. These caps carry the world surf's
  texture and `PolyFlags & 0x3cffffff` (which preserves `0x8`/`0x20`) — the flag-inheritance
  mechanism. **Deintersect reverses the caps** (`FPoly::Reverse`, `[0x100cee44]`, wrapped around the
  append): the deintersect solid is the "negative" of the intersect solid, so its cap normals point
  the opposite way. The cospatial tie-breaker differs by exactly one bit — intersect takes
  `FACING_OUT(5)`, deintersect takes `FACING_IN(4)` — the coplanar-with-a-world-surface case, resolved
  toward the side each operation's solid lives on.

Switch decode (`raw-intersect/*.asm`), e.g. P1-deintersect `0x32390`:
`sub eax,0; je keep; sub eax,2; jne skip` ⇒ `F∈{0,2}`; P1-intersect `0x339e0`:
`sub eax,1; je keep; sub eax,2; jne skip` ⇒ `F∈{1,3}`; P2-intersect `0x33ab0`:
`sub eax,1;je / sub eax,2;je / sub eax,2;jne` ⇒ `{1,3,5}`; P2-deintersect `0x32460`:
`sub eax,1;je / sub eax,2;je / sub eax,1;jne` ⇒ `{1,3,4}` + the two `FPoly::Reverse` calls.

FWTB dispatch (`raw-intersect/fwtb_switch.asm`, `0x333d7`): `cmp CsgOper,3; je → push 0x33ab0`,
`cmp CsgOper,4; je → push 0x32460`, both `bspFilterFPoly(leaf, [ebp-0x1f8]=Brush/TempModel, &Ed)` — the
world face is filtered through the **brush** temp BSP (arg `+0xc`), NOT the world (an earlier draft of
the sibling doc said "Model"; corrected here at instruction level).

---

## 3. The exact algorithm (reimplementation-ready pseudocode)

```
brush_from_intersection(builder_brush, world_model, deintersect: bool):
    # LOOP 1 — transform builder faces to world space (already in bspcsg.rs)
    temp = []
    for poly in builder_brush.polys:
        p = transform_to_world(poly, builder_brush)   # BuildCoords/PrePivot/Location + base-snap
        p.PolyFlags &= ~0x28                           # strip NotSolid|Semisolid on builder's own faces
        temp.append(p)

    result = []                                        # becomes builder_brush.polys

    # PHASE 1 — clip builder faces to the world solid/empty field
    for p in temp:
        for frag, F in filter_fpoly(p, world_model):   # split at each straddled world node plane
            keep = (F in {1,3}) if not deintersect else (F in {0,2})
            if keep and fix(frag) >= 3:
                result.append(frag)                    # no reverse

    # PHASE 2 — clip world faces to the builder hull (skipped if world has no BSP)
    if world_model.nodes:
        brush_bsp = bsp_build(temp)                    # LAME convex partition of the builder faces
        brush_bound = build_bound(brush_bsp)
        for world_face in straddling_world_faces(world_model, brush_bound):   # FilterWorldThroughBrush recursion
            for frag, F in filter_fpoly(world_face, brush_bsp):
                keep = (F in {1,3,5}) if not deintersect else (F in {1,3,4})
                if keep and fix(frag) >= 3:
                    if deintersect: frag.reverse()
                    result.append(frag)                # frag carries the WORLD surf's texture + PolyFlags

    renumber_ilinks(result)                            # surf-share: iLink -> lowest index sharing the surf
    builder_brush.polys = result
    builder_brush.RootOutside = 1
```

`filter_fpoly`, `transform_to_world`, `bsp_build`, `FilterWorldThroughBrush`'s straddle recursion,
`fix`, `reverse` — **all already exist in `bspcsg.rs`** (ported for the Add/Subtract materialize path).
The genuinely new code is the ~10-line tail driver + the four `keep`/`reverse` predicates above.

---

## 4. Reimplementation assessment

- **Effort: small.** The heavy machinery (FP-exact `SplitWithPlane`, the filter recursion, the temp
  BSP build, `bspNodeToFPoly`) is ported and FP-characterized (all SSE-scalar, bit-exact reachable —
  `81-phase0-feasibility.md`). Intersect/Deintersect is a *thinner* consumer than Add/Subtract (no
  incremental `bspAddNode` growth, no repartition, no zones/bounds/lightmaps — the output is just a
  builder polylist).
- **Byte-identity is NOT the natural bar here.** Unlike materialize, the output is a builder brush the
  user turns into a Mover; there is no on-disk `UModel` to byte-diff. The right oracle is **T3D
  face-set parity** against the live editor's `BRUSH EXPORT` after `BRUSH FROM INTERSECTION/
  DEINTERSECTION` (poly count, per-face verts/normal/texture/**PolyFlags**). Illustrative editor outputs
  from the 2026-07-24 mover-flags experiment are preserved beside this doc as
  `raw-intersect/{intersect,deintersect,aftermover}.t3d` (a stacked-slab scenario, evidence only — real
  per-case goldens are regenerated into `tests/fixtures/` when the verb is built).
- **Order fidelity** (poly order, iLink numbering) follows the same op-order discipline as the rest of
  the port; the finalize renumber (§1) is the one intersect-specific ordering rule.

**Verdict: reimplementable now**, as a standalone `brush intersect`/`brush deintersect` generator verb
(model-side, no editor) — the exact algorithm is §3, gated by the live T3D face-set oracle.
