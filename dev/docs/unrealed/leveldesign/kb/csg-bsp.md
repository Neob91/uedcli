# CSG, brushes & the BSP — the core skill  [ENGINE]

This is the **most important file in the KB**. Constructive Solid Geometry (CSG) and the Binary Space
Partition (BSP) it builds are the substrate every level sits on, and the BSP-problems section is the
single most **myth-ridden** topic in UE1 mapping. The meta-finding that reframes everything:

> **The community reliably gets the *fixes* right and the *mechanism* wrong.**

The whole deep section below reconciles ~40 community sources against the **disassembly spike**
[`../../../spikes/2026-06-24-bsp-csg-hole-mechanism-from-binary.md`](../../../spikes/2026-06-24-bsp-csg-hole-mechanism-from-binary.md)
— static disassembly of the shipped UED22 DLLs, which is the ground truth wherever code and folklore
disagree. Facts sourced from that spike are **decompiled facts** (we read the compiled instructions and
the float constants out of `.rdata`), a tier stronger than 📖.

---

## 1. The CSG mental model  [ENGINE]

- The world starts as **infinite solid void**. You **subtract** rooms out of the solid, then **add**
  detail brushes back inside the empty space you carved. (This is the opposite of "additive-first"
  engines — in UE1, empty space must be *cut out* before anything can exist in it.)
- A single **builder brush** (the red "cookie-cutter" wireframe) is shaped, positioned, then **committed**
  as a *Subtract* or *Add* operation. The builder brush is a stamp — it is **never itself part of the
  level**; committing copies its current shape into a new CSG brush actor.
- **uedctl verb:** `brush build {cube,cylinder,cone,sheet,staircase,spiral,extrude,revolve} --csg {add,subtract} | actor
  add -`. The generator (`brush build …`) prints a T3D snippet to **stdout**; it does **not** write the
  trunk. The write is always `… | actor add -` — show the full pipe, never `brush build` alone.
  - *(GUI equivalent: shape the red builder brush → **Shift-S** Subtract / **Shift-A** Add. 🔬 UED22
    accelerator table — Ctrl-A/Ctrl-S are Select-All/Save, not CSG.)*

### `.u3d` vs `.t3d`

**UnrealEd's brush `.u3d` Save/Load is broken — Export/Import `.t3d` is the reliable path** (import as
"Solid Mesh" + "Keep Original Polygons Intact"). 📖 Wolf. This is worth a callout because it independently
validates uedctl's entire git-tracked-T3D-trunk design: the community's own reliable interchange format is
the T3D text that uedctl treats as the source of truth.

---

## 2. Brush order determines the final geometry  [ENGINE]  ✅ binary-confirmed

Brushes resolve **in placement order** at rebuild. On an overlap, the **last** operation touching that
region wins. So the discipline is **"carve first, furnish after"**: send subtractive / structural brushes
**To First**, additive / detail brushes **To Last**.

**Binary confirmation** (disassembly spike §2): `UEditorEngine::csgRebuild` (Editor.dll `0x4a650`) is the
top of the F8 / `MAP REBUILD` pipeline. It:
1. `EmptyModel` — clears the world `UModel`.
2. Iterates the level's brushes **in actor order** (`ULevel::Brush()`, `AActor::IsStaticBrush`).
3. Applies each brush's CSG to the accumulated world via `bspBrushCSG` (Editor.dll `0x355e0`).
4. After all brushes: `bspBuild` → `bspRefresh` → `bspMergeCoplanars` → `bspOptGeom` → `bspBuildBounds`.

Each `bspBrushCSG` mutates the accumulated world model, so the **last** operation touching a region wins.
`MAP SENDTO FIRST/LAST` merely reorders the actor list the loop walks — **no heuristic re-sorts them**.

- **uedctl mapping:** CSG precedence is the trunk's **`(order_value, name)` sort**. `actor order --first`
  is the verb analog of "To First"; `actor order --last` of "To Last". There is no live editor state to
  reorder — the sort key IS the order.
  - *(GUI equivalent: select brush → Order → To First / To Last.)*

---

## 3. Intersect vs Deintersect — complex-brush authoring  [ENGINE]  📖 Wolf

These two operations trim the **builder brush** against the existing world, so you can fabricate a
complex convex shape (typically a mover, or a shape to add). They are the basis of complex-brush
authoring:

- **Intersect** reshapes the builder brush to **only the parts of it that lie in SOLID space** — the
  un-carved void or any added solid. It *is* aware of prior subtractions (a part inside a subtracted room
  counts as open space and is trimmed away) — so "Intersect ignores subtractions" is wrong. Use it to
  shape a convex brush that exactly fills a solid region.
- **Deintersect** is the complement: it reshapes the builder brush to only the parts lying in **EMPTY
  space** (open / already-subtracted regions), discarding the parts buried in solid.

Hotkeys **Ctrl-I** (Intersect) / **Shift-D** (Deintersect) 🔬 (UED22 accelerator table; Ctrl-N is New,
Ctrl-D is Duplicate — not these). **Reset ALL** (scale/rotation/pivot) on the builder
before intersecting a brush destined to become a mover, or the live transform leaks into the result.

**⚠ Do not over-use these** (see §8 contradictions): on-grid brushes join exactly with no intersect, and
intersect *makes complex multi-face brushes* — MORE splits and MORE float error. Use intersect only to
fabricate a mover/detail shape, never as a routine "make brushes fit" step.

---

## 4. Solidity  [ENGINE]  *(Settled)*

Every CSG brush has a **solidity** that decides whether it cuts the world BSP and whether it can be
subtracted-from / seal a zone.

| Solidity | Cuts world BSP? | Can be subtracted-from / close a zone? | Use |
|---|---|---|---|
| **Solid** | **yes** | **yes** | structural + **walkable** surfaces; anything subtracted-from; zone boundaries |
| **Semisolid** | **no** (cuts only itself) | no | detail that shouldn't cut the BSP (beams, pillars, trim, **walkable** platforms) — full reliable collision; keeps node count low, localises off-grid / curved geometry |
| **Nonsolid** | no | no (placed only inside a subtracted solid) | markers, **zone-portal sheets**, decoration |

- **uedctl verb:** `--solidity solid|semisolid|nonsolid` on `brush build`.
  - *(GUI equivalent: Add Special solidity, or the brush's Solidity flags.)*
- **Semisolids are fully walkable** — they have complete, reliable collision; you can walk and stand on them,
  so floors, ramps, and platforms built from semisolids are fine. Their ONLY special trait is that they do
  **not cut the world BSP** (they cut only themselves → fewer nodes).
- **A semisolid must NOT touch another semisolid, a nonsolid, or a zone portal.** This reliably wrecks the
  local BSP (invisible polys / HOM / zone merge). *(Folklore, but consistently real across sources.)*
- **Flipping a nearby semisolid ↔ solid re-cuts the local BSP a different way** — a standard hole fix
  (see §7). Mechanistically it changes whether the brush partitions the world at all, re-partitioning the
  region and dodging a bad split (spike §5).

Why semisolid is the workhorse for awkward geometry: it **receives cuts but emits no world-splitting
planes**, so off-grid / curved / high-facet detail can live on it without seeding float error into the
whole tree or exploding the node count — *provided* it stays clear of other semisolids/nonsolids/portals.

---

## 5. The BSP-problems section (DEEP)  [ENGINE]

This is the load-bearing craft topic. It is **engine-generic**: the code is the UT (`UnFPoly.cpp` /
`UnBsp.cpp` / `UnEdCsg.cpp`) lineage that DeusEx shares — an `appFailAssert` in `SplitWithPlane` embeds the
original source path `C:\GameDev\UnrealTournament\Engine\Src\UnFPoly.cpp`, confirming UED22's geometry
code is the Unreal-Tournament-era engine (spike §1 Provenance).

### 5.1 The one meta-finding that reframes everything

The dominant folk explanation — *"off-grid geometry causes a **floating-point overflow** and the engine
gives up on the maths"* — is **FALSE**. No value exceeds the double range. 🔬

The true cause is a small set of **discrete numeric validity tests with specific tolerance bands**.
Off-grid coordinates land *inside* those bands, so faces get **mis-classified as coplanar**, **collapsed
below 3 vertices**, or **rejected as zero-area** — and **a discarded `FPoly` *is* the hole.** The rule
("stay on grid") is right; the reason ("overflow") is wrong.

### 5.2 Where faces die — the engine code (spike §3–§6)

A `FPoly` is the engine's in-memory convex polygon (up to 16 vertices, a `Normal`, texture vectors,
flags). Brushes are lists of `FPoly`s; the BSP build chops them against planes. Every world face passes
through **`FPoly::Finalize`** (Engine.dll `0x150ac0`) — the survival gate. It can reject a poly three ways:

1. **`Fix` / `RemoveColinears` collapse** (`0x151090`) — two passes over the vertex ring:
   - *Pass 1, coincident vertices:* forms `Side = V[i] − V[i−1]`, crosses with the poly `Normal`, and tries
     to normalize via `FVector::NormalizeSlow` (Core.dll `0x249d0`), which returns false when length² <
     `SMALL_NUMBER` = **1e-8** (i.e. length **< ~1e-4 uu**). So two consecutive vertices **closer than
     ~1e-4 uu** are treated as the same point and one is deleted.
   - *Pass 2, colinear vertices:* compares adjacent side-plane normals component-wise with threshold
     **`9.999999e-05` (≈1e-4)** (the immediate `0x38d1b717`). A vertex on a straight edge is redundant and
     removed.
   - **After either removal, if `NumVertices < 3` it sets `NumVertices = 0`** → the caller discards the
     poly entirely. A face thinned below a triangle **vanishes**.
2. **`NumVertices < 3` → reject** — logs `"FPoly::Finalize: Not enough vertices (%i)"` (a warning if the
   `NoError` flag is set, else `appErrorf` → **Critical Error crash**) and returns `-1`.
3. **Zero area → reject** — `CalcNormal` (`0x150510`) accumulates a triangle-fan normal and normalizes; if
   `length² < 1e-8` the poly has effectively zero area → logs `"FPoly::CalcNormal: Zero-area polygon"` and
   is dropped. A **sliver** (a long thin fragment from a near-miss split) dies here.

A `-1` from `Finalize` means **this face does not exist in the world → a hole**. The two Critical-Error
variants are why a *bad enough* brush doesn't just leave a hole but **crashes the rebuild** (matches
`quirks.md`: degenerate geometry GPFs CSG).

**The upstream cause — the 0.25 uu split band** (`FPoly::SplitWithPlane`, Engine.dll `0x1518b0`, spike §5).
For every vertex it computes the signed distance to the partition plane `d = (V[i] − Base) · Normal`, then:
- `d > +T` → front · `d < −T` → back · `−T ≤ d ≤ +T` → **on the plane** (within the band),
where `T` is **0.25 uu** for a normal split (the 5th arg `VeryPrecise` selects 0.01 instead). If every
vertex is within ±T the whole poly is classified **`SP_Coplanar`** rather than being cleanly split.

**`T = 0.25 uu` is a *wide* band.** Any face lying within a quarter-unit of a partitioning plane is treated
as coplanar with it instead of split by it — exactly what off-grid geometry creates:
- A brush rotated by a non-90° angle, vertex-edited off grid, or fed through CSG with a live (non-permanent)
  float transform produces planes that are *almost* but not *exactly* aligned with neighbours.
- Faces that "should" split cleanly get mis-classified as coplanar, or split with a vertex landing inside
  the band, producing a **sliver** (→ killed by the zero-area test) or a **T-junction** (a vertex on one
  face with no matching vertex on the abutting face → a crack the renderer leaks through).
- Each split generates new vertices by interpolation; on a non-grid plane those land on irrational coords,
  so the *next* split accumulates more error. This is "off-grid diagonal cuts spray through everything
  behind them," seen from the numeric side.

**A second collapse point — the coplanar/merge tail** (`bspMergeCoplanars`, Editor.dll `0x36200`, spike
§6): it merges adjacent coplanar surfaces (using `THRESH_NORMALS_ARE_SAME = 2e-5`) and **re-runs
`RemoveColinears`** on the merged result. So even a face that survived initial CSG can be collapsed during
the merge pass if merging produces colinear vertices that thin it below 3. `bspMergeCoplanars` runs at
**every** optimization level — `LAME`/`GOOD`/`OPTIMAL` differ only in `FindBestSplit`'s splitter-candidate
stride, **not** in whether coplanars merge (verified: the `BSP REBUILD` handler calls
`bspBuildFPolys → bspMergeCoplanars → bspBuild` unconditionally; the level is passed only to `bspBuild`).
Different stride still → different splits → different coplanar adjacencies, so `LAME` and `OPTIMAL` can
yield different geometry — just not because one skips the merge.

### 5.3 The tolerance-band table (all read from `.rdata`)

| Constant | Value | Where | Effect |
|---|---|---|---|
| `THRESH_SPLIT_POLY_WITH_PLANE` | **0.25** | Engine `0x206780` (5 refs), Editor (2) | a poly within ±0.25 uu of a partition plane is **coplanar**, not split — the wide band |
| `THRESH_SPLIT_POLY_PRECISELY` | **0.01** | Engine `0x1fee1c` | the "very precise" split band, used where exactness matters |
| `SMALL_NUMBER` | **1e-8** (size²) | Core `0xa0a40` | `NormalizeSlow`'s zero-length floor → ~1e-4 uu length; drives both vertex-collapse and zero-area |
| colinear/coincident compare | **~1e-4** | immediate `0x38d1b717` | `RemoveColinears` vertex-drop threshold |
| `THRESH_POINTS_ARE_SAME` | 0.002 | Engine + Editor | point-equality elsewhere in CSG |
| `THRESH_POINTS_ARE_NEAR` | 0.015 | Engine + Editor | near-point tests |
| `THRESH_NORMALS_ARE_SAME` | 2e-5 | Editor | coplanar-merge normal equality (`bspMergeCoplanars`) |
| `THRESH_VECTORS_ARE_NEAR` | 0.0004 | Editor | vector near-equality |
| `THRESH_VECTORS_ARE_PARALLEL` | 0.02 | Engine + Editor | parallelism tests |

### 5.4 Problem catalog (community view → true mechanism ✅)

- **BSP hole** — a missing / see-through world face (or a `Black Space` triangle at a brush confluence),
  which in **solid space can also kill the player**. True cause: an `FPoly` discarded by `FPoly::Finalize`
  (`< 3` verts → "Not enough vertices"; ~zero area → "Zero-area polygon"; bad enough → **Critical Error**),
  usually because `RemoveColinears` collapsed vertices that drifted **< ~1e-4 uu** apart / near-colinear, or
  `SplitWithPlane`'s **±0.25 uu** band mis-handled an almost-aligned plane (→ slivers + T-junctions).
- **HOM (Hall of Mirrors)** — a *rendering* symptom: the framebuffer isn't cleared where a face should be,
  so you see smeared garbage. **Three causes, only ONE is BSP:**
  1. a BSP hole exposing the void (the geometry case above);
  2. a transparent / masked / invisible texture with **nothing behind it**;
  3. **an open view to the far clip plane with nothing to fill it** — no skybox (a FakeBackdrop surface +
     `SkyZoneInfo`) and no distance fog, so the far plane shows the un-cleared buffer.
  A **solid** brush's discarded face → HOM; a **semisolid**'s discarded face → an *invisible polygon*
  instead (it doesn't occlude, so it doesn't smear).
- **Leak** — two intended zones merge ("whole level full of water"). Cause: portals not watertight, **or a
  hole *on a portal face*** (the same `FPoly` mechanism applied to the portal). Diagnose in **Zone/Portal
  view**. (See [zones-performance.md](./zones-performance.md).)
- **Non-planar poly / "invalid brush"** — a vertex pulled off its face's plane, or two coincident verts.
  The **cleanest community↔binary match**: mappers observed the exact crash string `FPoly::Finalize<-FPoly:
  Not enough Vertices (0)`. An `FPoly` carries **ONE plane**; an off-plane vertex makes classification and
  rendering diverge (cracks / HOM) or collapses the face.
- **Coplanar flicker / z-fight** — two surfaces in the same plane. The famous **"1-unit gap"** fix (lift a
  nonsolid sheet ≥1 uu off the floor) works **precisely because 1 uu > the 0.25 uu split band**, pushing
  the two planes into distinct nodes. (The `No Bound Rejection` flag is a *render* band-aid, not a geometry
  fix.)
- **Node/poly explosion** — every brush face is a partitioning plane; an off-grid / awkward face becomes a
  global **"Supercut"** that splits many faces AND seeds float error into every interpolated vertex.
  Node:poly ~2:1 good (retail UT maps ~2.5–2.6:1); a high ratio (rule of thumb >4:1) is a warning sign, not
  a hard threshold. **Hard ceiling ≈ 65,536 BSP nodes — overflowing the *static*-node count means UnrealEd
  can no longer save the map, while the separate ~128,000-point (`MAX_POINTS`) limit is the one that
  *crashes*; UT-era reports put practical instability well before the ceiling** (stock UE1/DeusEx; the
  OldUnreal **227j** patch raises the **node** ceiling to 262,144 — **do NOT design DX maps to 227j limits**).
- **Invisible poly / Zone-0 face** — the zone flood-fill put a poly (usually a semisolid) in a non-visible
  zone. `PF_ForceViewZone` forces render but can leave it unlit — **symptomatic only**, not a fix.

### 5.5 Prevention — Tier A (verified mechanism: community fix AND disassembly agree)

1. **Grid discipline / integer on-grid coords / powers of two** (2-4-8-…-256; prefer 96/112/128 over 100).
   Off-grid signature to hunt: coords reading **`15.999976`** where `16` belongs. *Why:* exact plane
   coincidence → exact splits, nothing lands in the 1e-4 collapse band or the 0.25 split band as a sliver.
   - **uedctl caveat:** grid discipline is **guidance, not an enforced operation — uedctl does NOT snap
     coordinates for you.** The generators emit exactly the coords you pass; keeping them on-grid is the
     author's responsibility.
2. **Rotate SOLID (world-cutting) brushes only in 90° increments.** Off-90° *solid* brushes throw
   their partition planes off-grid (§5). **Semisolids, nonsolids, and decoration can be rotated to
   ANY angle** — a rotated box built as a semisolid is fine and often necessary, because a semisolid
   doesn't partition the world BSP (its off-grid planes only cut itself). *Corrects a common
   over-claim:* Transform Permanently does **not** rescue a 45°-rotated *solid* — the coords stay
   irrational.
3. **Keep every face planar & convex; never two coincident verts** (crashes Finalize).
4. **Coplanar surfaces: exactly coplanar (then Merge) or cleanly ≥1 uu apart** — never in-plane.
5. **Brush order: subtractive/structural To First; additive/semisolid/nonsolid/mover To Last** (last op
   wins — matches the actor-order rebuild loop, §2). uedctl: `actor order --first`/`--last`.
6. **Push off-grid / curved / detail geometry to SEMISOLID** — it receives cuts but emits no
   world-splitting planes, localising instability and cutting node count. *Constraint:* a semisolid must
   **not touch another semisolid, a nonsolid, or a zone portal** (§4).

### 5.6 Prevention — Tier B (real fix, folklore "why")

These *work*, but the popular explanation is wrong — recorded so the advice survives without carrying the
myth:

- **Transform Permanently after any rotate/scale/vertex-edit.** *Real win:* it bakes the float transform
  into vertices once, so CSG sees stable snappable coords instead of re-deriving drifting ones every
  rebuild — **not** "less runtime maths."
- **Keep node count low.** A real lever, but "the engine gives up at high node count" is folklore — the
  link is *more splits → more float error* (shared cause), plus the hard node/point ceilings (§5.4:
  static-node overflow blocks the save; the ~128,000-point limit crashes).
- **Rebuild at Optimal.** It samples more splitter candidates (`bspMergeCoplanars` runs at every level, so
  that's not the difference); "always rebuild 3×" is cargo-cult.
- **Avoid high-facet cylinders/spheres** and **tiny/thin sub-grid brushes** (they invite slivers).
- **Use the build sliders** (Minimise Cuts ↔ Balance, default 15/100) as a last-resort re-partition.

### 5.7 Repair (existing hole / HOM) + WHY each works

Reconciled to the disassembly (spike §5 repair table):

| Repair | Why it works (mechanism) |
|---|---|
| Rebuild Geometry+BSP at **Optimal** with **Build Visibility Zones ON** | re-runs the coplanar/merge pass; **building BSP without zones ON erases zones** |
| **Locate** via Zone/Portal view, a fog detector (`set PlayerPawn ConstantGlowFog (X=0.3)` → HOM spots turn solid red), or "show paths" (paths won't form over bad BSP) | narrows the culprit brush before you touch anything |
| **Grid discipline / clean multiples** (console `ACTOR ALIGN` to snap, then Transform Permanently) | keeps face planes exactly coincident → exact splits → nothing lands in the ±0.25 band as a sliver |
| **Transform Permanently** | bakes the float transform into vertices, so CSG sees stable coords instead of re-deriving drifting ones each rebuild |
| **Reorder** (To First / Last) | changes which planes partition which region → a different, cleaner set of splits (the `csgRebuild` order loop, §2) — uedctl `actor order --first/--last` |
| **Nudge** the culprit brush | shifts it out of a coplanar-coincident / near-band configuration |
| **Flip a nearby semisolid ↔ solid** | changes whether that brush cuts the world BSP at all → re-partitions locally, avoiding the bad split |
| **Hand-rebuild the face — select surrounding verts CLOCKWISE → Create** | re-adds an `FPoly` that survives `Finalize`; **clockwise *as seen in the viewport* = correct winding** so `CalcNormal` faces it outward (CCW-in-viewport = inverted). This is the same convention as `t3d.md`'s "CCW-from-outside", just viewed in UnrealEd's Y-down 2D view. Random vertex order → degenerate / Critical Error |
| **Merge coplanars** | collapses two same-plane faces into one, removing the z-fight/sliver pair |
| **1-unit gap** for a coplanar sheet | lifts it past the 0.25 uu band into a distinct node |
| **Convert to semisolid** | a solid's discarded face is a HOM hole; a semisolid's is a (non-occluding) invisible poly — less harmful, and it stops emitting the bad split plane |
| **Zone the area off** / restore from backup | last resorts |

### 5.8 Source contradictions — verdicts

- **"Always intersect/deintersect brushes that meet."** → **REJECT.** On-grid brushes join exactly with no
  intersect; intersect makes complex multi-face brushes = MORE splits and error. Use intersect only to
  fabricate a mover shape.
- **"Overlapping brushes cause holes."** → **FALSE** (explicitly, in multiple UE1 sources). Volumetric
  overlap is fine (last-op-wins); only **coplanar-coincident** and **off-grid** geometry cause holes.
- **"Brush sinking (add a face coplanar with a subtract to trim it)."** → **works only inside the 0.25 uu
  band; fragile** (HOM/collision when it drifts). Prefer surface-flag trim or a real detail brush.
- **"Semisolids must touch a subtract" (Red_Fist).** → that's **UT2004 / UE2** advice; in UE1 keep them
  **clear** of solids/subtracts/portals.
- **"Use semisolids only where players can't reach."** → **MYTH.** Semisolids have full, reliable
  collision — you can walk and stand on them, so floors/ramps/platforms built from semisolids are fine.
  The real constraint is only that a semisolid must **not** be coincident with / touch another semisolid,
  a nonsolid, or a zone portal (§4). Heavy use is correct and lowers node count.

### 5.9 Myths to REJECT (with correction)

1. **"Floating-point overflow / the engine gives up on the maths."** → the discrete tolerance bands (0.25
   uu split, <1e-4 colinear, <3-verts / zero-area). Rule right, reason wrong.
2. **"High node count itself causes holes."** → correlation via a shared cause (more off-grid splits → more
   error). The only hard node effect is that overflowing the ~65,536 static-node count **blocks the save**
   (the crash is the separate ~128,000-point limit).
3. **Static-mesh round-trip repair** → **UE2+**, unavailable in UE1/DeusEx.
4. **Antiportals / antiportal occlusion** → **UE2+**; in UE1 "portal" means **zone portal only** (see
   [zones-performance.md](./zones-performance.md)).
5. **The "Basic Level Design BSP (Unreal Tournament)" nerivec/michaeljcole wiki page** is actually **UE4**
   content ("Geometry mode", "Details panel", clip tool). The *concepts* carry back; the *tools/UI do not
   exist in UE1*. Do not cite its UI steps.
6. **227j node/bounds limits** → OldUnreal-patch-specific; stock DeusEx keeps the 65,536 ceiling.

---

## 6. uedctl verb summary for this file

| Craft task | uedctl | GUI equivalent |
|---|---|---|
| Carve / place geometry | `brush build {cube,cylinder,cone,sheet,staircase,spiral,extrude,revolve} --csg {add,subtract} --solidity {solid,semisolid,nonsolid} --texture … \| actor add -` | shape red builder → Subtract/Add |
| Solidity choice | `--solidity solid\|semisolid\|nonsolid` on `brush build` | Add Special solidity / brush flags |
| CSG precedence (To First/Last) | `actor order --first` / `actor order --last` | Order → To First / To Last |
| Grid discipline | **guidance only — uedctl does not snap for you** | GUI grid-snap toggle |

The disassembly-grounded facts here (the 0.25 split band, the ~1e-4 collapse threshold, the <3-verts /
zero-area rejection, brush-order = actor-order) are pinned by the `2026-06-24` spike's committed evidence;
a change that violates them should trip a red test rather than drift unnoticed.
