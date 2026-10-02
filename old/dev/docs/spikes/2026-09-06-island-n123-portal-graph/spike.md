# Island N=123 — Pass B ported faithfully; the leaf-26 divergence is NOT the portal graph

**Result: the prior root cause is DISPROVEN, one faithful port landed, the divergence re-localized
and still open.** `dev/docs/board/inbox/island-n-123-world-model2-leaf-permeating-light/` blamed
native's `zones::collect_portals` for building a different portal graph than
`FEditorVisibility::MakePortals` — a plain `1e-4` Sutherland–Hodgman clip where the editor uses
`FPoly::SplitWithNode(..., VeryPrecise = 1)` and DISCARDS an `SP_Coplanar` result. That difference
is real and Pass B is now a faithful port of it. It does not move Island N=123, and the editor's own
log proves the graph was never the problem: **UED22 reports 580 portals / 163 leaves / 427 nodes for
this build, and native produces exactly 580 / 163 / 427.**

## What was ported (`uedcli-native/src/zones.rs`)

`collect_portals` was a hand-rolled approximation: a `32768`-half-extent quad spanned by an ad-hoc
`plane_axes` basis about the node's stored `FPlane`, clipped to the node's cell by a `1e-4`
Sutherland–Hodgman pass over the ancestor planes, filtered to leaf pairs by the same crude clipper,
with two invented gates (`MIN_AREA = 1.0` on the face and on each fragment, and `front_leaf !=
back_leaf`).

It is now the editor's three functions, decoded from `Editor.dll` (2026-09-06, re-verified
instruction by instruction against `re-raw-zones/passB-makeportals-9750.md`):

- `BuildInfiniteFPoly` (`0xa7ae0`) → `build_infinite_fpoly`: a 4-vertex quad of half-extent
  `WORLD_MAX = 65536` (`0x100a7b9e`, `.rdata 0x100dea10`) on `Points[surf.pBase]` /
  `Vectors[surf.vNormal]` (`0x100a7b2e` / `0x100a7b3a` — the SAME pair `FPoly::SplitWithNode` reads,
  so it reuses `filter_plane`), spanned by `FVector::FindBestAxisVectors` (`Core.dll 0x507b0`).
  Vertex order `(Base ± B) ± A` with `B = Axis1·W`, `A = Axis2·W`, in the binary's grouping.
- `FEditorVisibility::MakePortalsClip` (`0xa9970`) → `make_portals_clip`: clip to the node's own
  cell by classifying against each ancestor with `SplitWithNode(VeryPrecise = 1)` (`0x100a9a4c`
  pushes the `1`) — `SP_Coplanar` discards the poly (`0x100a9a80`), a wrong-side `SP_Front`/
  `SP_Back` discards it whole, a matching-side one keeps it whole with NO cut, and only `SP_Split`
  trims. `>= 14` vertices `SplitInHalf` first and re-enter at the same stack position
  (`0x100a99e6`).
- `FEditorVisibility::MakePortals` (`0xa9750`) → `collect_portals`: the ancestor stack, FRONT child
  first with the side bit clear, then BACK with it set (`0x100a97e8` / `0x100a981e`).
- `AddPortal` (`0xa72a0`): keep every fragment whose two leaves are both non-solid. No area gate,
  no other test.

`Portalize` (`0xaa370`) also re-runs `AssignLeaves` (`0x100aa480`) immediately before `MakePortals`
(`0x100aa4f1`) — native has no equivalent; see the self-portal finding below.

The two-phase leaf-pair filter is `node_landings_precise`/`filter_through`, already a faithful
`FilterThroughSubtree` (`0xa9030`) port from the OceanLab orphan-vert work; Pass B now shares it
with Pass D instead of running its own crude clipper. Pass B' (`collect_zone_barriers`) still uses
the cheap `node_landings`; it reads only leaf PAIRS and is validated against four editor goldens.

**One of the two invented gates had to come back**, now as an explicitly recorded stopgap. Dropping
`front_leaf != back_leaf` made WanChai N=35 stop terminating: 8 of its BSP nodes carry
`iLeaf[0] == iLeaf[1] == 71` (in UED22's own shipped package as much as native's), both filter
phases land there, and `permeating_lights::leaf_portal_map` files the resulting self-portal in BOTH
directions where `AddPortal` files one — so one always clears the `d < 0` gate and the flood loops on
that leaf forever (35M+ `actor_visibility` calls, depth-capped; the build went from 13 s to >25 min).
Board: `portal-graph-builds-self-portals-from-stale`. `MIN_AREA` stayed deleted — every portal on
WanChai N=35 has area ≥ 100, so it was gating nothing.

`FVector::SafeNormal` (`Core.dll 0x51090`) moved from `permeating_lights` to `fpoly::safe_normal`
so both callers share the one port.

## Evidence the portal graph was never the divergence

`Portalize` prints `Portalized: %i portals, %i zone portals (%i fragments), %i leaves, %i nodes`
into `Editor.log`. Captured from a fresh N=123 golden build (a temporary `--log` flag on
`build_ued_import_built_golden.py`, since reverted — it digests into `actor_parity.recipe_
fingerprint()` and would invalidate every cached ref):

```
Log: Found 3 zones
Log: Portalized: 580 portals, 0 zone portals (0 fragments), 163 leaves, 427 nodes
Log: Time = 0.402120 msec per light
Log: BspOptGeom begin
```

Native: 580 portals, 163 leaves, 427 nodes, 3 zones + zone 0. The counts match with the faithful
port; the gate result is byte-for-byte the same as before it (same single `leaves[26]` mismatch,
every other array unchanged), so on this level the port is graph-neutral.

That log ordering also kills a second hypothesis: `Portalize` (portal graph AND the per-light flood)
runs BEFORE `BspOptGeom`, where the model still has 843 points / 95 vectors / 257 polys, while
native runs the flood at light-bake time on the post-`BspOptGeom` model (798 / 84 / 244). Dumping
native's portals for leaves 26 and 27 at BOTH points gives **identical polygons**, so the deferral
does not move this decision.

## Where the divergence actually is

`leaves[26]`: native `(iZone=1, iPermeating=107, -1)`, UED22 `(1, -1, -1)`; `Lights` 1729 vs 1727.
Traced with a temporary `UEDCLI_PERM_TRACE` dump of `actor_visibility`, native marks leaf 26 exactly
once, from light 34 (`Light124`, at `(-4528.35, 4385.68, 64.37)`, `WorldLightRadius` 1675):

```
leaf 85 (seed) --node 193--> leaf 32 --node 344--> leaf 27 --node 351--> leaf 26
```

Every gate on that path clears by a wide margin: seed descent has no `PlaneDot` under 63.6, the
`d < 0 && d > -R` plane gates are -63.6 / -379.9 / -1092.3 against R = 1675, and leaf 26's re-entry
radius gate qualifies at 1162 against 1675. The beam entering leaf 26 is the **unclipped** 27→26
portal quad — `SplitWithPlaneFast` returns `SP_Front` on all six edges of the beam.

The tightest of those six clears by **+1.795**, 7× the `0.25` epsilon, and it is not a floating-point
near-tie: that clip plane passes through the light and the beam's edge along
`(node 344's plane) ∩ (x = -3436)`, so it is fixed by geometry regardless of where along that line
the beam was cut. The constraint reduces to *"is the 27→26 portal quad on leaf 27's side of node
344's plane"*, and the quad's nearest corner is **1.90 units** inside — measured on the REFERENCE
package, whose `points`/`nodes` are byte-identical to native's. All four of that quad's vertices are
real `Model.Points` entries (within 3e-5). Moving the light ±64 units in any direction changes the
margin by less than 0.03, so it is a property of the model, not of the light.

Ruled out by direct disassembly (all now pinned in `test_engine_facts.py`):

- `FPoly::SplitWithPlaneFast` (`Engine.dll 0x151f90`) — the `Positive`/`Negative` flag pair against
  `±0.25`, `SP_Coplanar`/`SP_Front` keep-whole, `SP_Back` reject-whole, and the split loop's
  `PrevStatus` seeding all match native's port exactly.
- `ActorVisibility`'s clip loop (`0x100a7040`-`0x100a71c8`) — `FPlane(Location, Vertex[j],
  Vertex[jPrev])` argument order (the three by-value pushes at `0x100a70b7`/`0x100a70e7`/
  `0x100a7117`), `Poly = Front` on `SP_Split` only, cull on `SP_Back`, `>= 14` break, and
  `NumVertices > 0` before recursing.
- Portal orientation: no node in this build has a surf normal opposed to its stored plane, so
  `Portal.normal` (the node plane) and the editor's `Poly.Normal` (the surf normal) agree; and the
  beam-plane orientation `clip_beam` picks by sign-sum equals the editor's winding-derived one on
  every edge of the decisive beam (no flip taken).

So under the algorithm as decoded, UED22 should mark leaf 26 and does not. What is left is the
editor's actual portal FRAGMENTS: settling it needs a runtime dump of `AddPortal`'s
`(iFrontLeaf, iBackLeaf, FPoly)` triples from a live UED22 `MAP REBUILD` — the same `winedbg` INT3
method the UnrealScript ordering work used — compared against native's 580. Nothing cheaper
discriminates, because every count the editor reports already agrees.

## Follow-up this port unblocks

`permeating_lights::clip_beam` carries one deliberate departure: it orients each beam plane by
sign-sum over the clip poly's own vertices instead of taking `FPlane(Light, clip[j], clip[jPrev])`'s
winding-derived orientation. Its stated justification — "native's portal polys are synthesized by
`zones::collect_portals` from `plane_axes` and carry no winding guarantee" — is now gone:
`BuildInfiniteFPoly`'s quad winds so its winding normal is `-Normal` (`Axis1 x Axis2 = -N`, since
`Axis2 = Axis1 x N`), `SplitWithPlane` preserves that, and `leaf_portal_map` re-winds the reverse
direction exactly as `GetPolyForLeaf` does. Dropping the heuristic is the faithful next step. It is
NOT what fixes leaf 26 — the heuristic takes no flip on any of the six edges of the decisive beam —
and it moves every permeating-light decision on every level, so it wants its own pass with a full
five-level re-verification.

## Files

- `uedcli-native/src/zones.rs` — the port (`build_infinite_fpoly`, `find_best_axis_vectors`,
  `make_portals_clip`, `collect_portals`).
- `uedcli-native/src/fpoly.rs` — `safe_normal`.
- `uedcli/tests/test_engine_facts.py::test_make_portals_builds_a_65536_surf_plane_quad_and_
  classifies_with_split_with_node` — pins the 14 instruction encodings and `WORLD_MAX`.
- `harness/leaf26_margins.py` — the three offline measurements above (seed descent, beam margins,
  portal vertices vs `Model.Points`), run against `ref_N123.dx`.
