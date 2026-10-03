# Robust spatial-relation predicates over UE1 brush geometry

**Date:** 2026-10-03 · **Status:** research only — no decisions taken, nothing implemented.
**Question:** What is the right computational-geometry foundation for `actor survey`'s seven
relations, given inputs are UE1 brushes (plane-based, possibly non-convex, possibly degenerate) and
answers must be stable?

## Summary

- **The spec lives at `dev/specs/commands/actor-survey.md`** — the new Rust root, present at HEAD in this worktree. No `old/dev/specs/` directory exists here. Implementation and tests remain under `old/`.
- **Survey has no parity requirement.** UnrealEd has no survey feature, so no 1998 f32 answer is the specification. This inverts the sibling note `dev/research/bsp-csg-parity-and-robustness.md`, which rules exact predicates *out* of the CSG build path because reproducing the editor's wrong sign is the goal. For survey, correctness and self-consistency are the only bar — exactness is permitted and arguably required.
- **But the csg tier's inputs are parity-bound.** It reads the f32 native solve, whose resolved coordinates are reproducible only to the engine's point-dedup thresholds (`THRESH_POINTS_ARE_SAME` 0.002, `THRESH_POINTS_ARE_NEAR` 0.015, `old/uedcli-native/src/bspcsg.rs`). That is where `CSG_TOLERANCE = 0.015` comes from: the tolerance is forced by the solve, not by content and not by the relation.
- **There is no float-noise band in content.** The 2026-09-23 spike bisected clearance for 1522 collidable actors over six Deus Ex maps: smallest real penetration 0.043 uu, continuous from there to 64 uu. No content-derived tolerance exists.
- **Neither real-level false positive was fixed by moving an epsilon.** One was fixed by canonicalizing input coordinates (`actorgraph._snap_coord`, 0.001, reused from the write path's `CLEAN_EPS`); the other by making a measurement local to the overlap region. These are **precision-model and representation problems** — the class JTS/GEOS answered with a fixed precision model plus snap-rounding.
- **One name collision with the standard vocabulary matters:** uedcli's `crosses` is OGC/DE-9IM's `overlaps`, and DE-9IM's `crosses` is *undefined* between two solids. `9bac057f` renamed raw `overlaps`/`meets` **to** `crosses`/`touches` — i.e. away from the standard.
- **The "DE" in DE-9IM is machinery the spec rebuilds by hand.** A dimension digit (0/1/2/F) instead of a boolean is exactly "a shared corner or a shared edge alone is not area contact". uedcli expresses that as `_MIN_CONTACT_AREA = CSG_TOLERANCE ** 2`. The dimension digit is tolerance-free; the area floor is a tolerance.
- **RCC8 is the better formal anchor than DE-9IM for 3D** — dimension-independent by construction, and its composition table would let the tool *infer* relations instead of testing every pair.
- **No Rust library gives non-convex 3D topological relations with exact predicates under a permissive licence.** `geo`'s DE-9IM `Relate` is 2D-only; CGAL `Nef_3` and libigl booleans are GPL; `parry3d` is permissive and non-convex-capable but epsilon-based and query-shaped; `csgrs` (MIT) now uses Shewchuk-style exact predicates for topology decisions; `fornjot` was archived 2026-06-19.
- **Approximate convex decomposition (V-HACD, CoACD) is the wrong tool** — it changes the answer. `actorgraph.decompose_convex` already does an exact solid-leaf BSP self-split; keep that shape.
- **The 47-scenario corpus ports to Rust mechanically; its expectations do not.** All synthetic, no map files, no fixture files. Expected outcomes live in 150 Python test bodies and English docstrings.

## What we have today

| Path | LOC | Role |
|---|---:|---|
| `dev/specs/commands/actor-survey.md` | 109 | relation spec (new root, at HEAD) |
| `old/uedcli/actor_survey.py` | 2449 | both tiers; all seven relation decisions |
| `old/uedcli/relation.py` | 975 | 2D plane/footprint primitives (`_clip_2d`, `_shoelace_area`); backs `actor relation`, pure Python |
| `old/uedcli/actorgraph.py` | 832 | `decompose_convex`, `ConvexCell`, `point_in_brush`, `penetration_depth`, SAT (`level graph` only) |
| `old/uedcli/profile.py` | 348 | 2D Hertel–Mehlhorn (`convex_pieces`) — builder caps, not survey |
| `old/uedcli/tests/test_actor_survey.py` | 1935 | 150 tests |
| `old/uedcli/tests/survey_scenarios.py` | 1156 | 47 synthetic scenario builders |
| `old/uedcli-native/src/bspcsg.rs`, `collision.rs` | — | f32 CSG solve; BSP `point_is_solid` |

Tier split (`9bac057f`): **raw** = authored geometry only, ignores `CsgOper` and trunk order, needs no
native solve. **csg** = resolved matter after every Add/Subtract/Semisolid resolves in trunk order;
needs the solve. The vocabularies are disjoint, so the shipped output carries no `raw:`/`csg:` prefix
— block order identifies the tier. The spec reintroduces the prefixes as notation.

Native boundary: `actor_survey.py` reaches Rust through exactly **one** function, lazily imported
twice — `preview_native.solve_world_probe` (once per survey in `build_context`; once per distinct
truncation point in `_resolved_prefix_fragments`). Everything else — all seven decisions, the convex
decomposition, every polytope boolean — is CPython f64. The raw tier never touches Rust at all.

## Findings

### 1. The seven relations

| Relation | Tier(s) | Intended meaning | How computed today | Known failure modes |
|---|---|---|---|---|
| `touches` | raw, csg | coplanar faces sharing real **area**; csg adds opposite-facing normals and resolved matter | raw: `_polygons_area_contact` — coplanarity (dot within 1e-6, offset within `CSG_TOLERANCE`), project to a plane basis, Sutherland-Hodgman `_clip_2d`, shoelace area > `_MIN_CONTACT_AREA`. csg: `pair_touches` — no solve; both actors sliced on their *own* version of each candidate plane, region intersected, then centroid+fan probes lifted ±`CSG_TOLERANCE` and classified by `resolved_matter_of` | Probe sampling is a **sample, not a decomposition** — a contact surviving only on a patch smaller than one fan triangle is missed (`:1800-1803`). The far-side matter gate makes a symmetric relation asymmetric: a prop's contact is reported by the prop's survey, not the room's (`:1874-1875`, flagged "the owner's to settle"). Rounds 4 and 5 each *claimed* the boundary was `CSG_TOLERANCE` and each shipped one at `_SIDE_PROBE_STEP` (0.05) |
| `crosses` | raw, csg | two **non-coplanar** faces whose 2D interiors share a point | `_polygons_cross`: reject coplanar, solve the two planes' intersection line, Cyrus–Beck clip to each polygon's interior, require overlapping 1D intervals of length > 1e-9. csg re-solves A with only pre-B neighbours (`_resolved_prefix_fragments`) and takes **every** fragment, un-deduped | Source of both shipped real-level false positives (§3). Interior-vs-boundary: a crossing line lying exactly *on* a boundary edge was read as interior (`:551-558`, fixed). Fragment dedup by (owner, plane) dropped the fragment carrying the straddle — root cause of the original bug, confirmed on `Brush693`/`nyc_unatco_island` (`:1239-1242`). No fixture exercises a non-convex brush (`:945-946`) |
| `encloses` | raw | A's authored shape fully contains B's | `authored_shape_contains`: per-cell volume accounting, summed `_cell_intersection` volume vs `cell_volume` under `math.isclose(rel_tol=1e-6, abs_tol=1e-6)`; a point target degenerates to `point_in_brush` | A **measure** test standing in for a topological one: a 1e-6-relative shortfall is indistinguishable from exact containment, and `_polytope_from_planes`' `_VERTEX_EPS` (1e-3) band sets the real resolution. Conflates strict containment with flush-inside contact (DE-9IM `contains` vs `covers`; RCC8 NTPP vs TPP) — the agent cannot tell "floating free in the room" from "flush against the wall". Poisoned-unbounded-plane class: two near-parallel planes intersect at a blown-up point; found live returning ~2× the true volume for two identical boxes (`:322-331`, now guarded by a padded bbox) |
| `coincides` | raw | mutual full containment | two `authored_shape_contains` calls | inherits every `encloses` failure mode, twice |
| `carves` | csg | B (SUBTRACTIVE) removes matter from A | `_crosses_relation` **OR** order-gated `authored_shape_contains` (the total-removal clause, since a fully-enclosed victim has no boundary crossing) | inherits `crosses` and `encloses` modes. `CARVE_VOLUME_EPS` (`CSG_TOLERANCE ** 3`) is documented as `carves`' own volume threshold but is **not wired** there any more — only `_partition_by_brushes` uses it, and `_carves_volume` has no production caller |
| `connects` | csg | two SUBTRACTIVE voids are continuous | `voids_meet`: AABB reject, the same contact-region pipeline as `pair_touches`, then a **9×9 grid** (`VOID_PROBE_GRID`) sampled against the native `point_is_solid`, then a reachability walk in `_VOID_REACH_STEP` (1.0 uu) steps to each side's interior centroid | A fixed grid can miss an opening narrower than its own spacing — stated as an honest limit that "cannot be solved by sampling alone" (`:1954-1957`). A degenerate neighbour is silently dropped, not reported (`:2153-2158`). One known false positive pinned by fixture `subtract_sealed_inside_a_block_sharing_the_outer_walls_plane` (`:2086-2087`) |
| `occupies` | csg | A's resolved void fully contains B, and A is the last writer | exact, not sampled: `_cell_intersection`, then `_partition_by_brushes` splits the overlap against every other ordered brush so each piece is constant-membership; each piece's centroid tested for `resolved_matter_of` / `_last_writer_excluding` / `_is_void_excluding` | Centroid-per-piece is sound only because the arrangement makes each piece constant-membership — correctness rests entirely on `_partition_by_brushes` being complete, and float-dust pieces are dropped at `CARVE_VOLUME_EPS`. Regression `test_occupies_over_fires_without_the_own_matter_condition_pinned_by_construction` pins an over-fire for `sub1 → A → sub2` |

Dead code worth noting, because it changes what "today" means: `csg_faces`/`CsgFace`/`_canonical_plane`
(the per-(owner, plane) deduped resolved faces, built into the survey context) are **never read by any
of the five csg relations**. Nor are `penetration_depth`, `face_outward_sign`, `authored_volume` or
`_carves_volume` — their only callers are tests. So `crosses` no longer computes a depth, and `carves`
no longer measures a volume.

### 2. The raw/csg tier split, and why "resolved" was needed

Resolution changes five distinct classes of answer. Each is a thing authored geometry cannot decide:

1. **Authored volume ≠ matter.** A Subtract's authored box overlaps every Add later placed in its
   void, so raw-geometry `crosses` "fired for every piece of furniture in every room". Resolution says
   the Subtract has no matter at all; the correct facts are `occupies` or `carves`. The shipped doc now
   states the inverse explicitly — a raw overlap between a Subtract and the Add it carves is expected.
2. **Trunk order.** `carves` and `occupies` are duals for an Add/Subtract pair; whichever ran last
   wins. Raw cannot know, and the old raw tier faked it with an order heuristic.
3. **CSG kind.** Measured: a Semisolid contributes real solid but can never be a `carves` target
   (semisolids are applied after the repartition); a Nonsolid contributes no solid yet its faces
   really are removed; Intersect/Deintersect contribute nothing. Semisolid is 29% and Nonsolid 3% of
   shipped brush actors — "the common case, not a corner".
4. **Absence of a face.** `connects` is structurally the *absence* of a surviving solid face. There is
   no such thing in authored geometry.
5. **The specific resolved-`crosses` fix in `9bac057f`.** The source-cell feed had no resolved filter,
   so for a face a Subtract authored, the "solid" on the far side was the source Add's **own**
   remaining bulk. Live: `WallA --crosses(192uu)--> Doorway` (an ordinary door in a wall),
   `Rock --crosses(462uu)--> RoomA` ("fires on essentially every room in a real level"), and
   `Rock --crosses(1.47e+03uu)--> Crate`. Each also *suppressed* the pair's correct `touches`, because
   the flush test refuses any pair `crosses` claims.

The same board item recorded a soundness scare that is the clearest statement of the stability
requirement: fixture `niche_carved_into_wall` "escapes the same false positive only by accident:
`csg_faces` dedupes `Niche`'s x=64 plane to a fragment that happens to lie outside the wall. Keeping a
different fragment would flip that pair's answer." The spec's own rule — a redundant coplanar face
appearing or vanishing must not change a reported fact — is a **canonicalization** requirement, and
the dedup was the canonicalization that broke it.

### 3. The two false positives, generalised

**FP #1 — authored float noise.** Two UNATCO brushes authored exactly flush. `Brush186`'s Y-extent
computes as `576.000162` instead of `576.0`: T3D parsing is schema-free and never snaps, while
`emit.clean`/`CLEAN_EPS` runs on the **write** path only. The ~1.6e-4 uu sliver produced a nonzero
footprint-overlap polygon, clearing an **exact-zero** area gate (`_shoelace_area(overlap) == 0.0`),
after which the pair straddled the plane and reported `crosses`. Worse, the resolved face's own plane
was derived from the noisy ring. The fix was *not* an area floor — one already existed
(`_MIN_CONTACT_AREA`) and was deliberately not reached for. The fix was `actorgraph._snap_coord` at
0.001 ("same threshold as `emit.clean`, no new tolerance invented") applied at three pipeline entry
points, crucially **before** `_canonical_plane`.

**FP #2 — non-local measurement.** `penetration_depth` reduced a convex cell's reach with `max`/`min`
over its **entire point set**. For a wedge-shaped cell (a leftover from carving against a
non-axis-aligned neighbour) a face at the flush end still reported `crosses`, because a distant deep
corner supplied the depth. The footprint overlap was used as a yes/no **gate**, never as a **bound**.
The fix clips the cell to the lateral prism over the overlap polygon (`_overlap_lateral_planes` +
`_clip_cell`) before measuring. The commit also rules out the naive repair: filtering which existing
vertices to keep cannot work, because every corner of a box shares the same footprint locations
regardless of depth.

**Generalisation.** Neither is an epsilon problem in the sense of "the constant was wrong":

| Failure | Surface symptom | Actual class |
|---|---|---|
| FP #1 | a sub-milli-uu quantity defeats an exact-zero predicate | **precision model** — the read path had no canonical form while the write path did. Fixed by snap-rounding at ingest |
| FP #2 | depth off by hundreds of uu | **representation** — matter represented as a loose point set and reduced globally, for a predicate that is local |
| fragment dedup (`:1239-1242`) | the answer depends on which coplanar fragment survived | **representation** — lossy canonicalization |
| crossing line on a boundary edge (`:551-558`) | boundary contact read as interior crossing | **definition** — interior and boundary not separated in the primitive |
| rounds 4/5 (`test_only_csg_tolerance_moves_the_contact_boundary`) | documented boundary ≠ shipped boundary, twice | **multiple epsilons** — with no single precision model, nobody knows which constant decides |

The dominant class is **representation / precision model**, which is also the diagnosis JTS and GEOS
reached for 2D overlay: "The constructive nature of overlay operations makes them particularly
susceptible to the robustness issues which are notorious in geometric algorithms using floating-point
numerics", answered by "snap-rounding noding provides fully robust noding by rounding and snapping
linework to a fixed-precision grid", after which "fixed-precision overlay is now **guaranteed** to be
**fully robust**". The single `_snap_coord` call is a partial version of that idea: it snaps
coordinates but not derived planes, not intersection points, and not consistently across the tiers
(raw runs on a 1e-3 band, csg on 0.015).

### 4. Primitives actually in use

Present, hand-rolled: convex decomposition as a **solid-leaf BSP self-split**
(`actorgraph.decompose_convex`, yielding `ConvexCell(vertices, half_spaces)`); H-rep→V-rep polytope
enumeration (`_polytope_from_planes` — plane triples plus a half-space filter, `O(planes^3)`); convex
polytope booleans (`_cell_intersection`, `_clip_cell`, `_subtract_cell`) and a full arrangement
(`_partition_by_brushes`); exact tetra-fan volumes (`cell_volume`); half-space classification
everywhere as `dot(n,p) <= d + eps`; Sutherland-Hodgman 2D clipping (`relation._clip_2d`, the single
implementation, reused at nine sites); shoelace and Newell areas; Andrew's monotone chain 2D hull.

Absent: Weiler–Atherton; **any spatial index** (no grid, octree, BVH or kd-tree anywhere — the only
index in play is the native BSP behind `point_is_solid`, and every prefilter is a hand-rolled AABB);
SAT, which exists in `actorgraph` but is used only by `level graph`, never by survey; and
Hertel–Mehlhorn, which exists only in 2D at `old/uedcli/profile.py:312` (`convex_pieces` — ear-clip
then greedy merge across shared diagonals, capped at `MAX_FPOLY_VERTS` = 16, for builder cap faces).

Coordinate types: `Decimal` appears **only** in the neighborhood AABB layer (`NEIGHBORHOOD_PAD`,
`region_of`, `writes.aabb_intersects`). Every geometric computation is CPython f64 with explicit
`float(c)` conversions at ~20 sites; the native solve underneath is f32 end-to-end, so resolved
vertices re-enter Python at f32 precision. `Fraction` and exact rational arithmetic: **zero
occurrences**. "Exact" in the docstrings always means "a true polygon intersection rather than an
epsilon fudge", never rational.

Epsilon inventory — the strongest argument for a precision model is its length:

| Constant | Value | Gates |
|---|---|---|
| `CSG_TOLERANCE` | 0.015 | coplanar offset equality, fragment plane dedup, padded clip bounds, the `touches` contact boundary, the flush-vs-penetrate probe offset, point-actor matter radius |
| `_MIN_CONTACT_AREA` | `CSG_TOLERANCE ** 2` = 2.25e-4 | minimum contact area for raw `touches`, csg `touches`, `connects` |
| `CARVE_VOLUME_EPS` | `CSG_TOLERANCE ** 3` = 3.375e-6 | float-dust pieces in `_partition_by_brushes` |
| `_SIDE_PROBE_STEP` | 0.05 | off-face step in `face_outward_sign` — twice shipped as the *real* `touches` boundary |
| `_VOID_REACH_STEP` | 1.0 | `connects` reachability walk |
| `VOID_PROBE_GRID` | 9 | `connects` grid resolution ("never a second geometric tolerance") |
| `NEIGHBORHOOD_PAD` | `Decimal("1")` | neighborhood AABB growth |
| `actorgraph._VERTEX_EPS` | 1e-3 | `point_in_brush` boundary band, `_polytope_from_planes` vertex dedup |
| `actorgraph._SPLIT_EPS` / `_SNAP_EPS` / `_TOUCH_EPS` | 1e-4 / 0.001 / 1e-3 | BSP split, coordinate snap, raw-tier coincidence |
| `relation._PARALLEL_EPS` / `_PLANE_EPS` / `_TOUCH_EPS` / `_AREA_EPS` / `_GAP_EPS` | 1e-3 / 0.5 / 1e-3 / 1e-6 / 1e-6 | `actor relation` plane and footprint classification |
| unnamed | 1e-6, 1e-9, 1e-12 | coplanarity dots, degenerate normals, parallel denominators, interval emptiness |

The module carries an explicit anti-mixing rule ("NEVER `actorgraph._TOUCH_EPS` here: that is the RAW
tier's tolerance … a different geometry space with a different noise floor") and a derive-don't-invent
rule — every new tolerance derived from `CSG_TOLERANCE` or `_TOUCH_EPS`, with the convention that a
*k*-dimensional measure gets `CSG_TOLERANCE ** k`. That is good discipline for an epsilon regime. It
is not a substitute for a precision model, and the twice-shipped `_SIDE_PROBE_STEP` bug is the proof.

### 5. DE-9IM / Egenhofer / RCC8 — and where uedcli agrees

DE-9IM classifies a pair by the dimension of the nine pairwise intersections of each geometry's
interior, boundary and exterior, with values in {0,1,2,F}. It descends from Egenhofer's boolean 9IM
(512 outcomes) via Clementini's dimensional extension (6561). It is the model behind OGC Simple
Feature Access / ISO 19125, implemented by JTS, GEOS, PostGIS, GDAL and `geo`. **The published model
is 2D only** — Wikipedia records no 3D extension, and the point-set definition generalises to R³
without any standard having named the result.

| uedcli | uedcli meaning | Nearest standard | Verdict |
|---|---|---|---|
| `raw:touches` | coplanar face pair, ≥ area overlap, **normals ignored** | DE-9IM `touches` ∪ part of `overlaps` | **Differs, and dangerously** — ignoring normals means same-facing coplanar overlap (interiors overlapping) is reported under the same word as true boundary contact. In DE-9IM those are opposite cells of the matrix |
| `csg:touches` | area contact, **opposite-facing** normals, resolved matter | DE-9IM `touches` (`FT*******` / `F**T*****`); RCC8 **EC** | **Agrees**, and is *stricter*: uedcli requires the boundary∩boundary intersection to be 2-dimensional. DE-9IM states that directly with a dimension digit; uedcli states it with `_MIN_CONTACT_AREA` |
| `raw:crosses`, `csg:crosses` | non-coplanar face interiors share a point | DE-9IM **`overlaps`** (`T*T***T**`); RCC8 **PO** | **Name conflict.** OGC `crosses` is defined only when dimensions differ, or for line/line — for two solids it is undefined. uedcli's `crosses` is the standard's `overlaps`. `9bac057f` renamed raw `overlaps` → `crosses`, i.e. *away* from the standard |
| `raw:encloses` | A's authored shape fully contains B's | DE-9IM `contains` / `covers`; RCC8 **TPPi / NTPPi** | **Agrees in spirit, under-resolved.** Volume-equality containment cannot separate strict `contains` (NTPP) from flush-inside `covers` (TPP). The standard separates them, and the distinction is agent-relevant |
| `raw:coincides` | mutual containment | DE-9IM `equals` (`T*F**FFF*`); RCC8 **EQ** | **Agrees**; different name only |
| `csg:carves` | B is SUBTRACTIVE and removes A's matter | none | **Correctly outside the standard** — a CSG-authorship fact, not a topological one |
| `csg:connects` | two voids are continuous | RCC8 **C** (connected) applied to the *voids*, not the brushes | **Agrees**, and the standard already names the trick: relate the carved regions, not the carvers |
| `csg:occupies` | A's resolved void contains B, and A is last writer | DE-9IM `contains`/`covers` on (void of A, B) plus an authorship predicate | **Half-agrees** — the geometric half is `contains`; the "last writer" half is CSG semantics |
| — | absent | DE-9IM `disjoint` / RCC8 **DC** | uedcli reports facts, not absence. Fine for a report; a gap if relations are ever composed |

Two conclusions:

**Adopt the model, not the names.** The interior/boundary/exterior split plus a dimension digit is
precisely the machinery the repo has twice rebuilt ad hoc — the `_MIN_CONTACT_AREA` area floor, and
the `:551-558` fix for a crossing line lying on a boundary edge. Expressing each relation as a
constraint on an intersection matrix makes those cases structural rather than tolerance-gated, and it
makes mutual exclusivity ("a pair is never both `touches` and `crosses`") provable instead of enforced
by an explicit exclusion list.

**Do not rename on autopilot.** OGC semantics would hurt an agent-facing tool in two ways: `crosses`
is undefined for solid/solid, so the standard offers no word for the thing survey most needs to say;
and `overlaps`/`crosses` carry dimension-dependence rules that are a footgun for a reader who only
ever sees solids. **RCC8 is the better formal anchor** — eight base relations (DC, EC, PO, EQ, TPP,
NTPP, TPPi, NTPPi), defined for regions in any topological space and therefore 3D-valid as written,
with a composition table and path-consistency reasoning that could let `actor survey` *infer* facts
from known ones rather than testing every pair. The honest framing: uedcli already has an RCC8-shaped
vocabulary (EQ = `coincides`, EC = `csg:touches`, PO = `crosses`, TPPi/NTPPi = `encloses`) plus three
CSG-semantic relations the standards have no word for.

### 6. Robustness foundations for 3D

| Approach | What it buys for *stable relation answers* | Licence |
|---|---|---|
| **Fixed precision model + snap-rounding at ingest** (JTS/GEOS OverlayNG) | Removes FP #1's cause outright: no hairline overlap can exist if every coordinate lies on a grid. Makes answers deterministic and symmetric. Half-present already as `_snap_coord` | concept only; JTS EPL-2.0/EDL-1.0, GEOS LGPL-2.1 — no code needed |
| **Shewchuk adaptive exact predicates** (`orient3d` etc.; staged float filters escalating to exact only on an ambiguous sign) | Exact *sign* for coplanarity and side tests, so the classification step carries no epsilon. Does **not** fix noisy input — exactness on wrong coordinates is still a wrong answer | Shewchuk C **public domain**; `robust` MIT/Apache-2.0; `robust-predicates` MIT |
| **Plane-based exact representation** (Thibault & Naylor; Nehring-Wirxel, Trettner & Kobbelt) | A vertex *is* the intersection of its three original planes, so only exact **predicates** are needed, never exact **constructions**. "Unconditionally robust." Matches UE1's own primary representation and uedcli's own `half_spaces`-carrying cells | papers only |
| **CGAL `Nef_3`** (selective Nef complexes over half-spaces) | The only off-the-shelf thing that does all of this at once: exact arithmetic, non-manifold support, lower-dimensional features, interior/closure/boundary/regularization operators, point location by vertex/edge/facet/volume | **GPL** — blocker |
| **libigl `mesh_boolean`** | exact booleans via CGAL; winding-number inside/outside tolerates self-intersecting input | core MPL-2.0, but the boolean lives under `igl::copyleft::cgal` → GPL in practice |
| **Cork / Carve / QuickCSG** | triangle-soup booleans | Carve GPL-2.0; Cork LGPL/GPL-ish — verify per fork |
| **Interval arithmetic / filtered predicates** | certified sign, or "unknown"; a cheap near-tie detector for diagnostics | — |
| **Approximate convex decomposition** (V-HACD, CoACD) | nothing here — see §8 | V-HACD BSD-3-Clause (deprecated, archived); CoACD MIT |

Direct contrast with the sibling note: `dev/research/bsp-csg-parity-and-robustness.md` concludes that
exact predicates are **harmful in the CSG build path**, because reproducing UnrealEd's wrong sign is
the specification there. That reasoning does not transfer. Survey answers a question the editor never
answered, so there is no wrong sign to reproduce — only self-consistency to preserve. The two notes
agree on the mechanism (plane-based representation is the right model) and differ only on whether
exactness is allowed, because the requirement differs.

### 7. Rust crate landscape

| Crate | Non-convex 3D | Exactness | Tolerance queries | Licence | Maintenance | Fit |
|---|---|---|---|---|---|---|
| `parry3d` 0.31 | yes — `TriMesh`, `Compound`, `Polyline`, `HeightField`, `Voxels`, `ConvexPolyhedron` | floating-point; no exact predicates documented | **yes** — distance, contact with a prediction margin, closest points, point projection, `TriMeshFlags`/pseudo-normals for containment | Apache-2.0 | active (2026-09) | Best permissive source of *proximity* primitives, and the spatial index the module lacks. Query-shaped, not relation-shaped: gives "are these within d", not "are the boundaries coincident in a 2-dimensional set" |
| `rapier3d` 0.36 | via `parry3d` (re-exported) | as `parry3d` | as `parry3d` | Apache-2.0 | active (2026-09) | Wrong layer — simulation. Use `parry3d` directly |
| `nalgebra` / `glam` | n/a | f32/f64 | n/a | Apache-2.0 / MIT-Apache-2.0 | active | linear algebra only; `parry3d` already pulls `nalgebra` |
| `csgrs` | yes — indexed triangle meshes over three kernels | **exact-arithmetic predicates** (adaptive, Shewchuk-derived) for topology decisions; sampled geometry explicitly approximate | — | MIT | active (1247 commits) | Closest permissive thing to an exact 3D boolean kernel. Boolean-shaped, not relation-shaped, and a heavy dependency stack |
| `geo` (`Relate`, `IntersectionMatrix`) | **2D only** | robust predicates in places | — | MIT OR Apache-2.0 | active | **The reference implementation of the vocabulary** — read it for DE-9IM semantics; unusable for solids |
| `geos` bindings | **2D only** (GEOS C API) | GEOS precision models | `DWithin`-style | crate MIT; GEOS **LGPL-2.1** | active | same: a semantics reference, plus a C++ LGPL dependency |
| `spade` 2.15 | **2D only** (Delaunay / CDT) | "exact geometric predicate evaluation" | — | MIT OR Apache-2.0 | active (2026-09) | useful if a 2D CDT is ever needed for contact regions |
| `robust` 1.2 / `robust-predicates` 0.1.4 | predicates only | **adaptive exact** `orient3d`, `insphere` | — | MIT OR Apache-2.0 / MIT | `robust` healthy; `robust-predicates` single-owner, 0% documented | **Directly usable.** `robust` is the safer of the two |
| `truck` | b-rep + NURBS; `truck-shapeops` booleans | floating-point | — | Apache-2.0 | active (2872 commits) | Over-scoped for planar brushes; b-rep/NURBS buys nothing here |
| `fornjot` | b-rep, "simple very models" only | — | — | 0BSD | **archived 2026-06-19**, author states the goals were never reached | Not an option |

The gap is real and worth stating plainly: **no crate provides non-convex 3D topological relations
with exact predicates under a permissive licence.** The pieces exist separately — `robust` for signs,
`parry3d` for proximity and broad-phase, `geo` for semantics — and the glue (plane-based exact
representation plus a DE-9IM-shaped core) would be uedcli's own.

### 8. Convex decomposition of non-convex brushes

UE1 brushes are plane-based `FPoly` lists and may be non-convex (the `staircase` builder ships one;
`level doctor` accepts it and UnrealEd builds it). Every volume-level relation therefore needs a
decomposition.

- **What the repo does now is right in kind.** `decompose_convex` is an exact solid-leaf BSP
  self-split: split the brush by its own planes, keep the solid leaves, enumerate each leaf's
  vertices. An already-convex brush falls out as exactly one cell — the trivial case of the same
  recursion, not a special path. It raises `DegenerateBrushError` when no solid leaf survives, which
  is the correct answer for a self-intersecting or non-manifold `PolyList`.
- **Approximate decomposition (V-HACD, CoACD) is disqualified by definition, not by quality.** Both
  trade geometric fidelity for hull count against a concavity threshold; V-HACD 4.0 makes the user
  *specify* the hull count (default 32), and V-HACD is itself deprecated and archived in favour of
  CoACD. A decomposition whose union is not exactly the original volume cannot answer "does A fully
  contain B" or "do these touch" — the error lands in the answer, not in a tolerance.
- **Exact 3D convex decomposition is cheap here and expensive in general.** Chazelle's bounds — Ω(n²)
  convex parts in the worst case, and NP-hardness for minimum convex decomposition of polyhedra with
  holes — are the classical result, *not re-verified this session; check before relying on it.* It
  does not bite: brushes are small (a `cube` is 6 quads, `MAX_FPOLY_VERTS` caps a face at 16
  vertices), and the BSP self-split's cost is bounded by plane count, not by optimality.
- **2D Hertel–Mehlhorn stays where it is.** `profile.convex_pieces` solves a different problem —
  emitting *as few as possible* engine-legal convex cap faces, using only original ring diagonals so
  the solid stays watertight with no T-junctions. It is an output-shaping algorithm, not a predicate
  input. Do not reach for it in 3D.
- **Practical note on where it lives.** The expensive tier is **raw**, where `actorgraph.build_graph`'s
  O(brushes²) decomposition plus SAT already costs 12× a full native CSG solve at 208 brushes.

### 9. The tolerance question

`touches` is inherently a tolerance predicate — but only because of where its inputs come from, and
the measurements say so precisely:

- **Content has no noise band.** 1522 collidable actors, six maps: smallest real penetration 0.043 uu
  (0.052 among blocking actors), distribution continuous to 64 uu. "So no tolerance derived from
  content exists … a tolerance large enough to suppress the by-design cases (p90 = 12.7 uu) would
  suppress real mistakes too." The spike's remedy was a tighter **source gate**
  (`bCollideActors && bBlockActors`, dropping the max from 436 → 64.2 uu), not a tolerance.
- **The engine sets the floor.** Resolved coordinates are reproducible only to the CSG point-dedup
  thresholds, so the csg tier's coincidence tolerance is 0.015 uu — comfortably under 0.043, so it
  never suppresses a real fact, and large enough to absorb anything truncation or a different BSP
  split could move.
- **Authored coordinates carry *less* noise than resolved ones**, and the write path already defines
  their canonical form (`CLEAN_EPS` 0.001). The raw tier's 1e-3 band is therefore the right scale for
  authored geometry, and the two tiers legitimately differ — which is exactly why survey needs **two
  precision models, declared**, rather than fourteen epsilons.

Published approaches to making tolerance predicates consistent, and why naive epsilons produce this
exact failure class:

- **Snap-rounding / fixed precision models** (Hobby; Goodrich et al.; JTS/GEOS OverlayNG). Round every
  coordinate *and every derived intersection* to a grid, then compute exactly on the grid. Topology
  collapse — segments and points becoming coincident after rounding — is handled explicitly rather
  than hidden. GEOS's claim is unusually strong: fixed-precision overlay is "guaranteed to be fully
  robust". The reason naive epsilons fail is structural: an epsilon at one comparison makes that
  comparison tolerant but leaves every *derived* quantity noisy — which is literally FP #1, where
  snapping the ring was not enough until it was done *before* the plane was derived. Multiple
  independent epsilons also break symmetry and transitivity: "within 0.015 of coplanar" is not an
  equivalence relation, so three faces can be pairwise-coplanar-ish and mutually inconsistent, and
  the answer then depends on comparison order. That is the `csg_faces` dedup bug — and note the code
  already rejects a *rounded* dedup key for the mirror-image reason: "a rounded key decides two
  planes 0.001 uu apart differently depending on which side of a bucket boundary they fall".
- **Regularisation** (CGAL Nef: `interior()` then `closure()`). Normalises away dangling
  lower-dimensional features so a "solid" is always the closure of its interior. Relevant because UE1
  brushes genuinely carry degenerate faces, and survey currently raises `DegenerateBrushError` or
  silently drops a neighbour instead.
- **Exact predicates plus a precision model** is the combination that works: snap-round at ingest to
  fix *what* is compared, then use exact signs to fix *how*. Either alone leaves a hole — exactness on
  noisy input, or grid-snapped input compared with floats.
- **Simulation of Simplicity** (Edelsbrunner & Mücke) is worth naming only to reject: symbolic
  perturbation makes degeneracies never occur, and in survey degeneracies — flush faces, shared
  planes, coincident brushes — are the *questions*, not obstacles.

### 10. The corpus, and porting it to Rust

47 scenario builders, all `def name() -> Scenario`, docstring-as-spec, bodies that list actors.
Geometry is always builder primitives — `(size_xyz, center_xyz)` axis-aligned boxes via
`builders.cube` — with two exceptions: five rotated scenarios that bake a float Z-rotation into
vertices, and one hand-built degenerate brush (a single 3-vertex polygon bounding no solid). CSG order
is list order; kinds arrive via `csg="add"|"subtract"`, `poly_flags`, an `oper_brush` escape hatch for
`CSG_Intersect`/`CSG_Deintersect`, and `mover_class`. **100% synthetic: zero map loads, zero fixture
files, no `Path(` or `open(` anywhere.** Real-level cases appear as provenance in docstrings
(`19_Multiport`, `Brush190`/`Brush196`/`Brush269`/`Brush184`; `Brush118`/`Brush113`) or as transcribed
*numbers* — the UNATCO repro's `576.000162` is a literal in a test, not a loaded level.

Portability verdict: **geometry yes, expectations no.**

| Ports cleanly | Blocks |
|---|---|
| 45 of 47 scenarios are pure scalar data — name, size, location, csg kind, poly flags, class, mover class — serialisable as JSON/TOML | Expectations are **prose**. Every "must select" / "must not fire" lives in an English docstring; the machine-checkable form is spread across 150 test bodies. This is the dominant cost: re-extract per *test*, not per scenario |
| `builders.cube` is 6 hardcoded quads — a dozen lines in Rust | Coordinates route through `Decimal(str(c))` and `emit.clean` onto the Decimal grid "like a parsed level". Tolerance tests use 0.002/0.014/0.016 uu offsets. Serialise as **strings**, not JSON numbers |
| CSG order is list order | The 5 rotated scenarios exist to test float dust (1.9e-13 uu² at 30°). Serialise the **resulting vertices**, not (size, degrees), or Rust measures something else |
| `kind_table_scenario` covers the whole kind lattice in one fixture | **76 of 150 tests `importorskip("uedcli_native")`.** The scenarios do not need the native ext; the *assertions* do. Fixtures without the solve are inert |
| | 13 tests `monkeypatch` module constants (`CSG_TOLERANCE`, `_SIDE_PROBE_STEP`) or stub `decompose_convex` to force `DegenerateBrushError`. White-box; needs equivalent injection seams in Rust |
| | `oper_brush`'s prop-ordering hack encodes a Python-specific first-match-vs-last-wins disagreement between two readers; the invariant may not exist in Rust |

No property-based testing (`hypothesis` count: 0) — "property" coverage is `@pytest.mark.parametrize`
sweeps over depth, clearance and angle. Golden output is three structural string assertions, no
snapshots. Symmetry and mutual exclusion *are* tested
(`test_touches_is_reported_from_either_side_of_the_pair`,
`test_touches_and_crosses_are_mutually_exclusive_for_one_pair`,
`test_connects_does_not_fire_the_other_direction_either`) — the right instinct, and the natural home
for real property-based tests in Rust if the foundation changes.

## Options

| Option | Pros | Cons |
|---|---|---|
| **A. Port as-is** — f64, the fourteen epsilons, the same hand-rolled polytope code | Zero design risk; the 150 tests are the spec and port 1:1 against the same answers. Preserves every shipped ruling | Ports the bug class with the code. The twice-shipped `_SIDE_PROBE_STEP` boundary and the fragment-dedup soundness hole are structural, not incidental. "Stable answers" stays unachieved |
| **B. Declare two precision models and snap at every boundary** — authored grid at 0.001 (`CLEAN_EPS`), resolved grid at 0.015 (`THRESH_POINTS_ARE_NEAR`); snap coordinates **and** derived planes/intersections | Smallest change that addresses the measured root cause. Both grids already exist and are already justified by measurement. Makes each tier's tolerance a declared property rather than a code convention. GEOS's result says this is where the robustness comes from | Needs an audit of every derivation site, not just the three existing snap sites. Snapping a derived plane is harder than snapping a point. Does not by itself make the predicates exact |
| **C. B + exact predicates** (`robust` for `orient3d` and plane-side signs) | Removes epsilon from the classification step entirely; on a snapped grid the signs are then both exact *and* meaningful. MIT/Apache, no licence friction, tiny dependency | Two changes at once, each needing its own verification. Exact signs on a grid still need the grid chosen right, so B is a prerequisite |
| **D. Plane-based exact representation end-to-end** — integer/rational plane coefficients, vertices defined as plane triples, predicates only | The literature's answer, "unconditionally robust", and it matches both UE1's own representation and uedcli's `half_spaces`-carrying cells. Degenerate and coincident-plane cases become structural | Largest change by far. The csg tier's inputs still arrive as f32 from the solve, so exactness stops at that boundary unless the planes are reconstructed. Real risk of a rewrite that changes many shipped answers at once |
| **E. Lean on `parry3d`** for proximity, broad-phase and point containment | Permissive, maintained, non-convex-capable, and supplies the AABB/BVH index the module entirely lacks | Epsilon-based and query-shaped. Gives "within distance d", not "boundaries coincide in a 2-dimensional set". Would be a primitives dependency, never the relation layer |
| **F. Build a DE-9IM/RCC8-shaped core** and derive all seven relations as constraints on one matrix | Mutual exclusivity, symmetry and the interior/boundary distinction become provable rather than enforced by exclusion lists. One computation per pair instead of five pipelines. Enables composition/inference and a `disjoint` answer. Would retire the two near-duplicate contact pipelines (board item `pair-touches-and-planar-void-contact-share-25`) | A genuine redesign of the relation layer, and the three CSG-semantic relations (`carves`, `occupies`' authorship half, `connects`' void framing) sit outside the model and must be layered on. The vocabulary question — keep uedcli names or adopt standard ones — becomes unavoidable |

## Proposal (owner's call — not decided)

**B, then C, with F as the shape the Rust port is aimed at — and D kept as the thing B and C make
reachable later.**

The measurements point one way: content has no noise band, the only real tolerance is forced by the
f32 solve, and both shipped false positives were representation failures an epsilon could not have
fixed. So declare the two precision models and snap everything entering a predicate including derived
planes (B); then make the signs exact with `robust` (C), which is free of licence friction and cannot
change an answer that was already unambiguous. Treat **F** as the target design — express each
relation as a constraint on an interior/boundary/exterior matrix with a dimension digit, because that
is the machinery the repo keeps rebuilding by hand and getting subtly wrong.

On vocabulary: propose **keeping uedcli's seven names** (the spec, docs, tests, board and skills all
use them, and OGC has no word for solid-vs-solid `crosses` anyway), while documenting the §5 mapping
in the spec and anchoring on **RCC8** rather than DE-9IM when a formal statement is needed, since RCC8
is dimension-independent as published. One substantive semantic gap worth raising separately:
`encloses` conflates strict containment with flush-inside containment (NTPP vs TPP), and that is a
distinction an agent would use.

## Open questions / what to verify next

- Does `raw:touches` ignoring normals cause real confusion in practice, or is it only a naming
  concern? The spec states it deliberately; DE-9IM merges two opposite matrix cells to do it.
- Is board item `crosses-over-reports-depth-for-a-rotated-source` actually closed by `cc3b594e`'s
  local-overlap clipping? Same mechanism, but the item was never moved to `done/`. Re-run
  `two_cubes_face_to_face` at 0/17/30/45°.
- Can a derived plane be snapped consistently, or does snapping the ring and recomputing the plane
  (what `cc3b594e` does) remain the only sound order?
- `csg_faces`/`CsgFace`/`penetration_depth`/`_carves_volume` have no production callers. Intended
  future wiring, or should the port drop them?
- Chazelle's convex-decomposition bounds were not re-verified this session (SIAM J. Comput. 13(3),
  1984 is the reference). Do they bite at `MAX_FPOLY_VERTS`-capped brush sizes?
- Measure before choosing E: the module has **no** spatial index, and board item
  `actor-survey-neighborhood-selection-is-o-level` records 855 ms of neighborhood selection against
  7.6 ms of solve on `wanchai`. That is the live cost problem, not the predicates.
- `relation.py` carries five more epsilons on a different scale (`_PLANE_EPS` = 0.5). Is `actor
  relation` in scope for the same precision model, or does it stay separate?

## Sources

- https://en.wikipedia.org/wiki/DE-9IM — the 9-intersection matrix; Egenhofer boolean 9IM (512 outcomes) vs Clementini dimensional extension (6561); named predicate patterns; the model addresses 2D only.
- https://postgis.net/docs/ST_Relate.html — DE-9IM pattern strings (`touches` `FT*******`/`F**T*****`, `overlaps` `T*T***T**`, `contains` `T*****FF*`, `equals` `T*F**FFF*`) and the dimension-dependence of `crosses`/`overlaps`.
- https://postgis.net/workshops/postgis-intro/spatial_relationships.html — PostGIS's own wording, incl. `ST_Crosses`' "dimension one less than the maximum dimension of the two source geometries" and its supported dimension pairs (no solid/solid).
- https://libgeos.org/ — GEOS implements the OGC Simple Features model; LGPL (page references 2.1); predicate list.
- https://docs.rs/geo/latest/geo/algorithm/relate/trait.Relate.html — `geo`'s DE-9IM `Relate`, MIT OR Apache-2.0, 2D types only. The `IntersectionMatrix` page 404'd: full predicate list **unverified**.
- https://lin-ear-th-inking.blogspot.com/2020/ and .../2020/06/jts-overlayng-tolerant-topology.html — the robustness diagnosis and snap-rounding fix; "fixed-precision overlay is now **guaranteed** to be **fully robust**"; topology collapse.
- https://www.cs.cmu.edu/~quake/robust.html — Shewchuk's adaptive predicates: correct determinant sign, staged work, **public-domain** C, extended-precision-register caveat.
- https://docs.rs/robust/latest/robust/ — `robust` 1.2.0, direct transcript of Shewchuk, MIT OR Apache-2.0; `orient2d`/`orient3d`/`incircle`/`insphere` with input-orientation caveats.
- https://docs.rs/robust-predicates/latest/robust_predicates/ — 0.1.4, MIT, single owner, 0% documented; Shewchuk lineage not explicitly claimed on the page.
- https://arxiv.org/abs/2103.02486 — Nehring-Wirxel, Trettner & Kobbelt, *Fast Exact Booleans for Iterated CSG using Octree-Embedded BSPs*: plane-based geometry + integer arithmetic, "unconditionally robust"; exact **predicates** suffice because vertices are plane intersections, never constructed.
- https://doc.cgal.org/latest/Nef_3/index.html — selective Nef complexes, sphere maps, non-manifold edge-uses, lower-dimensional features, `interior`/`closure`/`boundary`/`regularization`, point location; exact-kernel requirement.
- https://doc.cgal.org/latest/Manual/packages.html, https://www.cgal.org/license.html — kernels LGPL; `Nef_3`, 2D Nef polygons, Polygon Mesh Processing and the AABB tree all **GPL**.
- https://libigl.github.io/tutorial/ — booleans live under the copyleft/external modules; CGAL-exactness and winding-number details **unverified** there (consistent with the sibling note).
- https://docs.rs/parry3d/latest/parry3d/ plus its `query` and `shape` pages — Apache-2.0, 0.31.1 (2026-09-18); intersection, distance, contact, closest points, time of impact; `TriMesh`, `Compound`, `ConvexPolyhedron`, `Polyline`, `HeightField`, `Voxels`; `TriMeshFlags`, `TriMeshPseudoNormals`. Exactness claimed nowhere.
- https://docs.rs/rapier3d/latest/rapier3d/ — Apache-2.0, 0.36.0 (2026-09-25); depends on and re-exports `parry3d`; simulation-shaped.
- https://github.com/timschmidt/csgrs — MIT; indexed triangle meshes over three kernels; "topology-sensitive decisions use `Real` and the Hyper predicate stack" (adaptive exact, Shewchuk-derived); active.
- https://github.com/ricosjp/truck — Apache-2.0; b-rep + NURBS; `truck-shapeops` provides solid booleans; active.
- https://github.com/hannobraun/fornjot — 0BSD; **archived 2026-06-19**, "goals were never reached", simple models only.
- https://docs.rs/spade/latest/spade/ — MIT OR Apache-2.0, 2.15.1 (2026-09-20); 2D Delaunay/CDT with "exact geometric predicate evaluation"; no 3D.
- https://docs.rs/geos/latest/geos/ — MIT crate wrapping the GEOS C API (GEOS itself LGPL); prepared geometries and predicates; dimensionality not stated on the page (GEOS is 2D).
- https://en.wikipedia.org/wiki/Region_connection_calculus — RCC8's eight base relations, defined for regions "in Euclidean space, or in a topological space"; composition table and path-consistency; RCC5, RCC23.
- https://github.com/kmammou/v-hacd — BSD-3-Clause; "near" convex parts; exact decomposition avoided as impractical; 4.0 requires a user-specified hull count (default 32); **deprecated and archived** in favour of CoACD.
- https://github.com/SarahWeiii/CoACD — MIT; approximate, concavity-threshold driven; no stated guarantee of exact volume coverage.
- https://sfcgal.gitlab.io/SFCGAL/ — "a C++ wrapper library around CGAL with the aim of supporting ISO 19107:2013 and OGC Simple Features Access 1.2 for 3D operations". The 3D predicate list and licence were **not** on the page.
- https://postgis.net/docs/ST_3DIntersects.html — `ST_3DIntersects` and `ST_3DDWithin` exist; **no 3D DE-9IM relate** documented; SFCGAL backend removed in PostGIS 3.0.
- Chazelle, "Convex partitions of polyhedra: a lower bound and worst-case optimal algorithm", SIAM J. Comput. 13(3), 1984 — **not re-verified this session**; cited for the Ω(n²) worst-case part count and NP-hardness of minimum convex decomposition with holes.
- Internal: commits `9bac057f`, `cc3b594e`, `884b0d34`, `6437e36e`, `b60b471c`, `2675e93a`; `old/dev/docs/spikes/2026-09-23-actor-survey-csg-kind-and-cost/spike.md`; `old/dev/docs/board/to-plan/actor-survey-and-actor-relation-csg-resolved/`; `old/dev/docs/board/done/actor-survey-csg-tier-resolved-geometry-and/plan.md`; `dev/research/bsp-csg-parity-and-robustness.md`.
