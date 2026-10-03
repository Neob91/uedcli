"""`actor survey <name>` -- every raw and CSG-resolved spatial fact about one actor.

The rules this implements are in
`dev/docs/board/to-plan/actor-survey-and-actor-relation-csg-resolved/spec.md`; the measurements
behind the neighborhood algorithm and the csg tier's tolerance are in
`dev/docs/spikes/2026-09-23-actor-survey-csg-kind-and-cost/`. Read both before changing anything
here -- several constants below are load-bearing for reasons that are not visible locally.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from decimal import Decimal

from . import actorgraph, movers, polyalign, query, relation
from .normalize import is_builder_brush
from .texframe import newell
from .writes import aabb_intersects, actor_bounds

# The neighborhood region is the surveyed actor's own world AABB grown by this much. 1.0 uu is the
# spike's own `PAD` (`harness/bounded_cost.py:35`) -- the value every one of its 140 verified
# surveys ran at, so changing it invalidates that evidence. Decimal, not float: `actor_bounds`
# returns Decimals and will not mix with a float.
NEIGHBORHOOD_PAD = Decimal("1")


class ActorNotFoundError(Exception):
    """`actor survey` was given a name the level does not carry. The CLI maps this to exit 2 --
    never a bare KeyError (`CLAUDE.md`)."""

    def __init__(self, name: str):
        super().__init__(f"Actor not found: {name}")
        self.name = name


class ActorHasNoLocationError(Exception):
    """`region_of` was asked to place a non-brush actor that has no `Location`.

    A brush's real position comes from its own vertices (`actor_bounds` needs no `Location`), but a
    non-brush actor's ONLY position is `Location` -- so a missing one is not "at the origin", it is
    unknown. `nearby_point_actors` already skips a location-less CANDIDATE for exactly this reason
    ("a substituted origin would invent a containment fact"); the surveyed actor gets no such skip
    (there's nothing to skip it FROM), so it must raise instead of silently defaulting to `(0,0,0)`
    and fabricating a neighborhood around the world origin. The CLI maps this to exit 2 (Task 18),
    the same as `ActorNotFoundError`."""

    def __init__(self, name: str):
        super().__init__(f"actor {name!r} has no Location -- cannot compute its region")
        self.name = name


def region_of(actor, defaults, pad: Decimal = NEIGHBORHOOD_PAD):
    """`actor`'s REAL world AABB grown by `pad`, in Decimals.

    A brush's real shape is its own transformed vertices, which is what `writes.actor_bounds`
    returns. A non-brush actor is treated as its bare `Location` point -- no collision-cylinder
    extent (`CollisionRadius`/`CollisionHeight` are ignored for point actors everywhere in this
    module, by owner ruling) -- so `actor_bounds`' own zero-size box at `Location` is used as-is.

    Ported from the spike harness's `region_of`, which only ever ran on brushes. The Decimal is not
    incidental -- `writes.aabb_intersects` adds its own Decimal slack and raises TypeError against a
    float bound.

    Raises `ActorHasNoLocationError` for a non-brush actor with no `Location` -- a brush's position
    comes from its own vertices regardless of `Location`, but a non-brush actor's only position IS
    `Location`, and `actor_bounds` falling back to `(0,0,0)` there would fabricate a real position
    for an actor that has none, building a neighborhood around the world origin instead of
    surfacing the real problem (see the exception's own docstring). `defaults` is accepted but
    unused -- kept so every caller's call shape stays the same."""
    if actor.brush is None and actor.location is None:
        raise ActorHasNoLocationError(actor.name)
    lo, hi = actor_bounds(actor)
    return (tuple(c - pad for c in lo), tuple(c + pad for c in hi))


def _meets(actor, region, defaults) -> bool:
    """Does `actor`'s own (unpadded, `pad=0`) region overlap `region`? Shared by `neighborhood`,
    `near_brushes`, and `nearby_point_actors` so the near-test itself lives in one place."""
    return aabb_intersects(region_of(actor, defaults, Decimal(0)), region)


def in_world_csg(actor, class_index) -> bool:
    """Does this actor contribute to the WORLD CSG solve? A Mover and the builder brush are both
    brushes and neither does -- the same filter `preview_native.solve_world_surfaces` applies."""
    return actor.brush is not None and not (movers.is_mover(actor, class_index)
                                            or is_builder_brush(actor))


def neighborhood(level, class_index, surveyed_actor, defaults) -> list:
    """Every BRUSH actor whose own world AABB meets the surveyed actor's region, in TRUNK ORDER --
    plus, always, the level's FIRST world-CSG brush.

    Ported from `bounded_cost.py::neighborhood`. The first-brush clause is not cosmetic and was
    found by the measurement failing without it: `bsp_brush_csg` special-cases a leading `CSG_Add`
    against a node-less world, SEEDING that brush as the world shell (storing every face reversed)
    instead of classifying it (`uedcli-native/src/bspcsg.rs`'s `first_add_seed`). Truncation changes
    which brush is first, so the shortcut fires on the wrong one -- measured on `nsfhq04
    DeusExMover31`, whose truncated solve lost all four `Brush799` faces and gained a `Brush798` one.
    Keeping the level's own first brush first makes the shortcut fire on exactly the brush it fires
    on in the full solve."""
    region = region_of(surveyed_actor, defaults)
    out, have_first = [], False
    for name in level.order:
        a = level.actors[name]
        if a.brush is None:
            continue
        contributes = in_world_csg(a, class_index)
        near = _meets(a, region, defaults)
        if near or (contributes and not have_first):
            out.append(a)
        if contributes:
            have_first = True
    return out


def near_brushes(level, class_index, surveyed_actor, defaults) -> list:
    """`neighborhood` minus the far first brush the seed clause forces in. The first brush is there
    for the SOLVE's correctness; it shares no geometry with the surveyed actor and must not be fed
    to `raw_relation_for` or named in any fact. Same filter the spike harness applies before its own
    raw-tier timing (`bounded_cost.py`'s `near = [...]`)."""
    region = region_of(surveyed_actor, defaults)
    return [a for a in neighborhood(level, class_index, surveyed_actor, defaults)
            if _meets(a, region, defaults)]


def nearby_point_actors(level, surveyed_actor, defaults) -> list:
    """Every NON-BRUSH actor whose own region meets the surveyed actor's region, in trunk order.
    `neighborhood` is brush-only by design (it feeds the CSG solve, which takes brushes), so the
    point-actor fan-out needs this second, cheaper selection.

    An actor with no `Location` is skipped -- it has no position to be contained at, and a
    substituted origin would invent a containment fact.

    The CANDIDATE is tested by its own extent-aware `region_of`, not by its bare `Location`, because
    this list feeds TWO facts. `contains` (Task 16) is satisfied by either test -- enclosing an
    actor's full extent already implies its `Location` sits inside the container's AABB, so the
    narrower test never dropped a real `contains`. `crosses` direction 2 (Task 12) is the one that
    needs the wider test: it asks whether a point actor's collision cylinder reaches INTO the
    surveyed brush, which is true for cylinders whose `Location` sits outside it. Under a
    bare-`Location` filter that crossing appeared when you surveyed the point actor and vanished
    when you surveyed the brush -- exactly the asymmetry `crosses_facts_for` is written to rule
    out.

    `pad=0` on the candidate: the pad is the solve's truncation safety margin, not part of an
    actor's shape, and the surveyed actor's region already carries it. Same call shape
    `neighborhood` and `near_brushes` use for their own candidates."""
    region = region_of(surveyed_actor, defaults)
    out = []
    for name in level.order:
        a = level.actors[name]
        if a.brush is not None or a.location is None:
            continue
        if _meets(a, region, defaults):
            out.append(a)
    return out


@dataclass(frozen=True)
class RawFact:
    """One raw-tier line's worth of information. `src`/`dst` are already in the spec's final
    display direction (`raw_relation_for`'s own job) -- no separate flip step downstream."""
    src: str
    dst: str
    relation: str


@dataclass(frozen=True)
class RawFacts:
    facts: list
    nodes: dict
    skipped: list


def raw_facts_for(level, class_index, name: str, defaults, *,
                  cells: dict | None = None) -> RawFacts:
    """Every raw-tier fact about `name` -- pure authored geometry, over the bounded neighborhood
    (see the module docstring for why bounded). Raises `ActorNotFoundError` for an unknown name, and
    `actorgraph.DegenerateBrushError` when the SURVEYED actor's own brush cannot be decomposed; a
    degenerate NEIGHBOUR is skipped and recorded in `skipped`."""
    if name not in level.actors:
        raise ActorNotFoundError(name)
    cells = {} if cells is None else cells
    surveyed = level.actors[name]
    nodes: dict = {name: actorgraph._node_tag(surveyed, class_index)}
    facts: list[RawFact] = []
    skipped: dict[str, str] = {}

    others = [a for a in near_brushes(level, class_index, surveyed, defaults) if a.name != name]
    points = [a for a in nearby_point_actors(level, surveyed, defaults) if a.name != name]

    if surveyed.brush is not None:
        actorgraph.decompose_convex(surveyed, cache=cells)     # propagates on a bad SURVEYED brush
        for other in others:
            try:
                actorgraph.decompose_convex(other, cache=cells)
            except actorgraph.DegenerateBrushError as e:
                skipped[other.name] = str(e)
                continue
            rel = raw_relation_for(name, surveyed, other.name, other, cells)
            if rel is not None:
                src, dst, relation = rel
                facts.append(RawFact(src=src, dst=dst, relation=relation))
                nodes[other.name] = actorgraph._node_tag(other, class_index)
        for p in points:
            loc = tuple(float(c) for c in p.location)
            if actorgraph.point_in_brush(surveyed, loc, cache=cells):
                facts.append(RawFact(src=name, dst=p.name, relation="encloses"))
                nodes[p.name] = actorgraph._node_tag(p, class_index)
    else:
        if surveyed.location is not None:
            loc = tuple(float(c) for c in surveyed.location)
            for other in others:
                try:
                    if not actorgraph.point_in_brush(other, loc, cache=cells):
                        continue
                except actorgraph.DegenerateBrushError as e:
                    skipped[other.name] = str(e)
                    continue
                facts.append(RawFact(src=other.name, dst=name, relation="encloses"))
                nodes[other.name] = actorgraph._node_tag(other, class_index)

    return RawFacts(facts=facts, nodes=nodes, skipped=sorted(skipped.items()))


def format_raw_line(fact: RawFact, nodes: dict) -> str:
    """One raw-tier line, its verb prefixed `raw:` -- `touches`/`crosses`/`encloses` are now shared
    names with the csg tier (spec, `dev/specs/commands/actor-survey.md`), so the prefix carries
    tier identity; the verb no longer can on its own."""
    return (f"{fact.src} {actorgraph._node_bracket(nodes[fact.src])} --raw:{fact.relation}--> "
            f"{fact.dst} {actorgraph._node_bracket(nodes[fact.dst])}")


# The csg tier's coincidence tolerance, in world units: the engine's own THRESH_POINTS_ARE_NEAR
# (`uedcli-native/src/bspcsg.rs`). Resolved point coordinates are only reproducible to the CSG
# point-dedup thresholds, so nothing finer is a real geometric distinction in a resolved model --
# and every perturbation the bounded-neighborhood truncation can introduce is inside this band
# (spike.md §3 and §4 residual 2). It sits comfortably under the 0.043 uu smallest real penetration
# measured on shipped content, so it suppresses no real fact.
#
# NEVER `actorgraph._TOUCH_EPS` (1e-3) here: that is the RAW tier's tolerance, for authored brush
# vertices, a different geometry space with a different noise floor. Also the padding
# `authored_shape_contains`'s own cell-intersection bounds check uses (Task 15 C2 fix) -- reused
# rather than a new epsilon, per the same discipline.
CSG_TOLERANCE = 0.015


def _order_around(points, normal) -> list:
    """`points` (all on one plane with the given normal) sorted by angle around their own centroid,
    so a fan triangulation over them covers the face exactly once."""
    helper = (0.0, 0.0, 1.0) if abs(normal[2]) < 0.9 else (1.0, 0.0, 0.0)
    u = (helper[1] * normal[2] - helper[2] * normal[1],
         helper[2] * normal[0] - helper[0] * normal[2],
         helper[0] * normal[1] - helper[1] * normal[0])
    ul = (u[0] ** 2 + u[1] ** 2 + u[2] ** 2) ** 0.5 or 1.0
    u = tuple(x / ul for x in u)
    v = (normal[1] * u[2] - normal[2] * u[1],
         normal[2] * u[0] - normal[0] * u[2],
         normal[0] * u[1] - normal[1] * u[0])
    c = tuple(sum(p[i] for p in points) / len(points) for i in range(3))

    def angle(p):
        r = tuple(p[i] - c[i] for i in range(3))
        return math.atan2(sum(r[i] * v[i] for i in range(3)),
                          sum(r[i] * u[i] for i in range(3)))
    return sorted(points, key=angle)


def cell_volume(cell) -> float:
    """The volume of one `actorgraph.ConvexCell`.

    A convex polytope's volume is the sum of tetrahedra from any interior point to each face's
    triangulation. The cell's vertex centroid IS interior (a convex hull's centroid always is), so
    every tetrahedron is non-overlapping and the absolute values sum cleanly -- no winding or
    orientation question to get wrong. Each face is the vertex subset lying on one bounding plane,
    ordered around that plane's normal before fanning."""
    verts = [tuple(float(c) for c in v) for v in cell.vertices]
    if len(verts) < 4:
        return 0.0
    c = tuple(sum(v[i] for v in verts) / len(verts) for i in range(3))
    total = 0.0
    for normal, d in cell.half_spaces:
        n = tuple(float(x) for x in normal)
        on = [v for v in verts
              if abs(sum(n[i] * v[i] for i in range(3)) - float(d)) <= actorgraph._VERTEX_EPS]
        if len(on) < 3:
            continue
        ordered = _order_around(on, n)
        a = ordered[0]
        for i in range(1, len(ordered) - 1):
            b, e = ordered[i], ordered[i + 1]
            ab = tuple(a[k] - c[k] for k in range(3))
            cb = tuple(b[k] - c[k] for k in range(3))
            db = tuple(e[k] - c[k] for k in range(3))
            cross = (cb[1] * db[2] - cb[2] * db[1],
                     cb[2] * db[0] - cb[0] * db[2],
                     cb[0] * db[1] - cb[1] * db[0])
            total += abs(sum(ab[k] * cross[k] for k in range(3))) / 6.0
    return total


def authored_volume(actor, cells: dict) -> float:
    """The total volume of ACTOR's own authored brush shape (every convex cell summed), in cubic
    world units. 0.0 for a non-brush actor -- it authors no volume, and so never competes to be a
    container. Raises `actorgraph.DegenerateBrushError` for a malformed brush."""
    if actor.brush is None:
        return 0.0
    return sum(cell_volume(c) for c in actorgraph.decompose_convex(actor, cache=cells))


def _cell_bounds(cell) -> tuple:
    verts = cell.vertices
    return (tuple(min(v[i] for v in verts) for i in range(3)),
            tuple(max(v[i] for v in verts) for i in range(3)))


def _same_plane(normal, offset: float, other) -> bool:
    """Are `(normal, offset)` and `other` one plane? The same coincidence rule `csg_faces` dedupes
    fragments by: normals aligned (both are already sign-canonical, so aligned means equal) and
    offsets within `CSG_TOLERANCE`."""
    return (abs(normal[0] * other[0][0] + normal[1] * other[0][1] + normal[2] * other[0][2] - 1.0)
            <= 1e-6 and abs(offset - other[1]) <= CSG_TOLERANCE)


def _polytope_from_planes(planes: list[tuple[tuple[float, float, float], float]],
                          bounds: tuple | None) -> "actorgraph.ConvexCell | None":
    """The convex polytope `{p : n.p <= d for (n, d) in planes}`, via H-rep -> V-rep vertex
    enumeration: every plane TRIPLE's intersection point (`actorgraph._intersect_three_planes`),
    kept only when it also satisfies every other plane. `bounds` (`(lo, hi)`, already padded), when
    given, additionally drops a candidate vertex outside it BEFORE the half-space check -- the
    poisoned-unbounded-plane guard (board item `authored-volume-poisoned-by-unbounded-plane`): two
    near-parallel planes intersect at a point whose distance from either blows up as they approach
    parallel, and nothing else here catches a resulting vertex light-years from the real geometry.
    None when fewer than 4 vertices survive (empty or degenerate).

    `planes` is deduped by `_same_plane` first: `_cell_intersection` concatenates both cells'
    half-spaces with no dedup, so two cells sharing an exact (or near-exact, within
    `CSG_TOLERANCE`) coincident plane -- e.g. two coincident boxes -- would otherwise carry that
    plane twice into the returned cell's `half_spaces`, and `cell_volume` fans/sums a face
    contribution per half-space entry, double-counting the shared face. Bug found live: two
    identical 10x10x10 box cells' `_cell_intersection_volume` came back ~2x `cell_volume`."""
    eps = actorgraph._VERTEX_EPS
    deduped: list = []
    for n, d in planes:
        if not any(_same_plane(n, d, p) for p in deduped):
            deduped.append((n, d))
    planes = deduped
    verts: list = []
    for i, j, k in itertools.combinations(range(len(planes)), 3):
        p = actorgraph._intersect_three_planes(planes[i], planes[j], planes[k])
        if p is None:
            continue
        if bounds is not None:
            lo, hi = bounds
            if any(p[m] < lo[m] or p[m] > hi[m] for m in range(3)):
                continue
        if not all(n[0] * p[0] + n[1] * p[1] + n[2] * p[2] <= d + eps for n, d in planes):
            continue
        if not any(math.dist(p, q) < eps for q in verts):
            verts.append(p)
    if len(verts) < 4:
        return None
    return actorgraph.ConvexCell(vertices=verts, half_spaces=planes)


def _cell_intersection(cell_a, cell_b) -> "actorgraph.ConvexCell | None":
    """The convex intersection `cell_a INTERSECT cell_b` as its own polytope (not just its volume)
    -- `_polytope_from_planes` over both cells' half-spaces, bounded by their combined bounding
    boxes padded by `CSG_TOLERANCE` (any real point of the intersection lies inside both cells' own
    boxes, so a candidate outside the padded combined box is provably not a real vertex here). None
    for cells whose boxes don't meet, or a genuinely empty/degenerate intersection."""
    a_lo, a_hi = _cell_bounds(cell_a)
    b_lo, b_hi = _cell_bounds(cell_b)
    lo = tuple(max(a_lo[i], b_lo[i]) - CSG_TOLERANCE for i in range(3))
    hi = tuple(min(a_hi[i], b_hi[i]) + CSG_TOLERANCE for i in range(3))
    if any(lo[i] > hi[i] for i in range(3)):
        return None
    return _polytope_from_planes(list(cell_a.half_spaces) + list(cell_b.half_spaces), (lo, hi))


def _cell_intersection_volume(cell_a, cell_b) -> float:
    """The volume of `cell_a INTERSECT cell_b`. Thin wrapper over `_cell_intersection` -- see that
    function for the vertex-enumeration pipeline and the poisoned-unbounded-plane guard."""
    cell = _cell_intersection(cell_a, cell_b)
    return cell_volume(cell) if cell is not None else 0.0


def _clip_cell(cell, normal, offset: float) -> "actorgraph.ConvexCell | None":
    """`cell` intersected with the single half-space `normal . p <= offset` -- `_cell_intersection`
    with one extra plane instead of a second full cell, bounded by `cell`'s OWN box padded by
    `CSG_TOLERANCE` (no second cell to intersect against). None when the half-space excludes `cell`
    entirely, or the result is degenerate."""
    lo, hi = _cell_bounds(cell)
    bounds = (tuple(c - CSG_TOLERANCE for c in lo), tuple(c + CSG_TOLERANCE for c in hi))
    return _polytope_from_planes(list(cell.half_spaces) + [(normal, offset)], bounds)


def _subtract_cell(piece, cutter) -> list:
    """`piece` minus `cutter`'s convex volume, as a list of disjoint convex pieces (possibly empty).
    Standard convex-polytope subtraction by sequential half-space clipping: for each of `cutter`'s
    own half-spaces in turn, split off whatever of what's left lies STRICTLY OUTSIDE this one plane
    (definitely not in `cutter`, since it fails this plane alone) into the output, and keep only the
    inside-this-plane remainder to test against the next -- `piece` minus a convex region is the
    union of at most `len(cutter.half_spaces)` such fragments. Reuses `_clip_cell`'s own vertex
    enumeration and bounds guard; introduces no new tolerance."""
    remaining = [piece]
    outside: list = []
    for normal, offset in cutter.half_spaces:
        next_remaining = []
        for p in remaining:
            out_part = _clip_cell(p, tuple(-c for c in normal), -offset)
            if out_part is not None:
                outside.append(out_part)
            keep_part = _clip_cell(p, normal, offset)
            if keep_part is not None:
                next_remaining.append(keep_part)
        remaining = next_remaining
    return outside


def authored_shape_contains(container, target, cells: dict) -> bool:
    """Does CONTAINER's own authored shape enclose TARGET entirely?

    A non-brush TARGET is tested at its `Location` (an actor with no Location is never contained --
    a substituted origin would invent the fact). A brush or Mover TARGET is tested on its FULL
    VOLUME, not merely its corner vertices: `container`'s own cells partition its authored shape (a
    valid decomposition's solid leaves don't overlap), so TARGET's volume is fully enclosed iff each
    of its own cells' volume is exactly accounted for by the sum of its intersections with every
    container cell -- `sum(_cell_intersection_volume(target_cell, c) for c in container_cells) ==
    cell_volume(target_cell)`. A vertex-only check (every corner inside) is NECESSARY but not
    SUFFICIENT for a non-convex container: an L-shaped container's reentrant notch can swallow the
    MIDDLE of a target cell whose own corners both sit in the container's two convex arms, on either
    side of the notch -- the corners pass a per-vertex test while a real slice of the target's volume
    sits outside the container entirely. Review finding, Task 15 round 2 (critical).

    Strict full containment is still the deliberate rule (spec): a large Add or Mover that only
    partially pokes out of a Subtract gets no `occupies`, even though `encloses` reports one, and
    majority-of-extent was considered and rejected as its own source of ambiguity -- this upgrade
    changes HOW full containment is tested, not the strictness of the rule itself.

    The volume compare uses a plain relative tolerance (`1e-6`, this module's own bare
    floating-point-dust convention -- e.g. `_same_plane`'s `abs(... - 1.0) <= 1e-6` -- not a new named
    geometric epsilon): float dust from two independent tetrahedral-volume computations, never a
    reason to call a genuinely-poking-out target contained."""
    if container.brush is None:
        return False
    if target.brush is None:
        if target.location is None:
            return False
        p = tuple(float(c) for c in target.location)
        return actorgraph.point_in_brush(container, p, cache=cells)
    container_cells = actorgraph.decompose_convex(container, cache=cells)
    target_cells = actorgraph.decompose_convex(target, cache=cells)
    if not target_cells:
        return False
    for tc in target_cells:
        tc_volume = cell_volume(tc)
        if tc_volume <= 0.0:
            continue
        covered = sum(_cell_intersection_volume(tc, cc) for cc in container_cells)
        if not math.isclose(covered, tc_volume, rel_tol=1e-6, abs_tol=1e-6):
            return False
    return True


def raw_relation_for(name_a, actor_a, name_b, actor_b, cache: dict) -> "tuple[str, str, str] | None":
    """The RCC (region-connection-calculus) relation between two BRUSH actors' own AUTHORED volumes
    -- pure geometry, ignoring CsgOper, trunk order, and Mover-ness entirely (spec, raw tier). None
    for disjoint volumes. Decision procedure (spec's own): mutual full containment -> `coincides`
    (checked FIRST -- takes priority over `encloses`, since identical brushes satisfy
    `authored_shape_contains` both ways); one-way full containment -> `encloses`; interiors
    interpenetrate beyond `_TOUCH_EPS` -> `overlaps`; boundaries meet with no interior penetration ->
    `meets`. Returns `(src, dst, relation)` already in display direction: `coincides`/`overlaps`/
    `meets` are symmetric and lead with `name_a` (the caller's own convention -- always the surveyed
    actor); `encloses` leads with whichever of the two is the container."""
    b_in_a = authored_shape_contains(actor_a, actor_b, cache)
    a_in_b = authored_shape_contains(actor_b, actor_a, cache)
    if a_in_b and b_in_a:
        return (name_a, name_b, "coincides")
    if b_in_a:
        return (name_a, name_b, "encloses")
    if a_in_b:
        return (name_b, name_a, "encloses")

    polys_a = _authored_polys_world(actor_a)
    polys_b = _authored_polys_world(actor_b)
    if _any_polygons_cross(polys_a, polys_b):
        return (name_a, name_b, "crosses")
    if any(_polygons_area_contact(pa, pb, require_opposite_normals=False)
           for pa in polys_a for pb in polys_b):
        return (name_a, name_b, "touches")
    return None


def _plane_of(verts) -> tuple | None:
    """`(unit normal, offset)` for a world-space ring via Newell's method, sign UNCANONICALIZED --
    unlike `_canonical_plane`, which flips the sign to dedup two fragments of one plane and so
    cannot be reused here: `_polygons_area_contact`'s opposite/same-facing distinction needs the
    real facing direction, not an arbitrary canonical one. Returns None for a degenerate ring."""
    n = newell([tuple(float(c) for c in v) for v in verts])
    length = (n[0] ** 2 + n[1] ** 2 + n[2] ** 2) ** 0.5
    if length < 1e-9:
        return None
    unit = tuple(c / length for c in n)
    return unit, sum(unit[i] * float(verts[0][i]) for i in range(3))


def _polygons_cross(verts_a, verts_b) -> bool:
    """Do two planar polygons (world-space vertex rings) lie on non-coplanar planes with their
    interiors (2D, each within its own plane) sharing a point?

    This is `crosses [raw]`/`crosses [csg]`/`carves [csg]`'s shared geometric test (spec,
    `dev/specs/commands/actor-survey.md`). The two planes' line of intersection is found once
    (solved directly from the two plane equations in the `na, nb, d` basis, not by walking edges),
    then clipped to each polygon's own 2D interior by intersecting it against every edge's inward
    half-plane in turn (Cyrus-Beck style) -- exact for a convex polygon, which every polygon this
    module hands in is (a brush face, or one convex cell's face). The two resulting sub-intervals of
    the SAME line are compared directly; they must overlap with real (not edge-touching) length."""
    pa, pb = _plane_of(verts_a), _plane_of(verts_b)
    if pa is None or pb is None:
        return False
    na, oa = pa
    nb, ob = pb
    dot = sum(na[i] * nb[i] for i in range(3))
    if abs(abs(dot) - 1.0) < 1e-6:
        return False                          # coplanar (or parallel, never intersecting)
    dx = na[1] * nb[2] - na[2] * nb[1]
    dy = na[2] * nb[0] - na[0] * nb[2]
    dz = na[0] * nb[1] - na[1] * nb[0]
    dlen = (dx * dx + dy * dy + dz * dz) ** 0.5
    d = (dx / dlen, dy / dlen, dz / dlen)
    denom = 1.0 - dot * dot
    a_coef = (oa - ob * dot) / denom
    b_coef = (ob - oa * dot) / denom
    p0 = tuple(a_coef * na[i] + b_coef * nb[i] for i in range(3))

    def _clip(normal, verts):
        u, v = relation._plane_basis(normal)
        origin = verts[0]

        def to_2d(p):
            delta = tuple(p[i] - origin[i] for i in range(3))
            return (sum(delta[i] * u[i] for i in range(3)), sum(delta[i] * v[i] for i in range(3)))

        p0_2d = to_2d(p0)
        d_2d = (sum(d[i] * u[i] for i in range(3)), sum(d[i] * v[i] for i in range(3)))
        poly_2d = [to_2d(p) for p in verts]
        t_lo, t_hi = -math.inf, math.inf
        n = len(poly_2d)
        for i in range(n):
            ax, ay = poly_2d[i]
            bx, by = poly_2d[(i + 1) % n]
            edx, edy = bx - ax, by - ay
            edge_len = (edx * edx + edy * edy) ** 0.5
            if edge_len < 1e-9:
                continue                       # degenerate edge, contributes no real constraint
            nx, ny = -edy / edge_len, edx / edge_len   # UNIT inward normal (CCW rule), scale-free
            edge_denom = nx * d_2d[0] + ny * d_2d[1]
            numer = (nx * ax + ny * ay) - (nx * p0_2d[0] + ny * p0_2d[1])
            if abs(edge_denom) < 1e-9:
                if numer > CSG_TOLERANCE:
                    return None                # parallel to this edge, strictly outside it
                if numer > -CSG_TOLERANCE:
                    return None                # parallel to this edge AND running along it -- the
                                                # crossing line lies exactly on this boundary edge,
                                                # not through the polygon's interior (the bug this
                                                # fixed: `Brush698`'s wall meeting `Brush144`'s top
                                                # exactly at the wall's own bottom edge was wrongly
                                                # read as a crossing)
                continue                       # parallel to this edge and well inside -- no bound
            t = numer / edge_denom
            if edge_denom > 0:
                t_lo = max(t_lo, t)
            else:
                t_hi = min(t_hi, t)
        if t_lo >= t_hi - 1e-9:
            return None
        return (t_lo, t_hi)

    seg_a = _clip(na, verts_a)
    if seg_a is None:
        return False
    seg_b = _clip(nb, verts_b)
    if seg_b is None:
        return False
    lo, hi = max(seg_a[0], seg_b[0]), min(seg_a[1], seg_b[1])
    return lo < hi - 1e-9


# The smallest contact region that is a region rather than an edge. `CSG_TOLERANCE` is the finest
# distinction the resolved tier makes, so an overlap area below its square is not a real area.
_MIN_CONTACT_AREA = CSG_TOLERANCE ** 2


def _polygons_area_contact(verts_a, verts_b, *, require_opposite_normals: bool) -> bool:
    """Do two planar polygons share a real 2D area (not just a point or an edge) on a common
    plane -- spec's "Area contact"? `require_opposite_normals` is `touches [csg]`/`connects`'s own
    extra condition (same-facing coplanar overlap is `crosses`/`carves` territory there, since
    which side has solid matter matters); `touches [raw]` passes `False` since raw draws no such
    distinction (spec, `touches [raw]`'s own note)."""
    pa, pb = _plane_of(verts_a), _plane_of(verts_b)
    if pa is None or pb is None:
        return False
    na, oa = pa
    nb, ob = pb
    dot = sum(na[i] * nb[i] for i in range(3))
    if abs(abs(dot) - 1.0) > 1e-6:
        return False                          # not coplanar
    # Same plane means oa == ob when the normals agree, but oa == -ob when they're opposite: a
    # plane's offset is relative to ITS OWN normal direction, so flipping the normal flips the
    # sign convention too. Comparing `oa - ob` unconditionally (an earlier version of this
    # function did) rejected every genuine opposite-facing coplanar pair as "not coplanar" --
    # confirmed live on `Brush698`/`Brush699`'s flush adjacency in `nyc_unatco_island`.
    if abs(oa - (ob if dot > 0 else -ob)) > CSG_TOLERANCE:
        return False                          # parallel but offset -- never touches
    if require_opposite_normals and dot > 0:
        return False
    u, v = relation._plane_basis(na)
    origin = verts_a[0]

    def to_2d(p):
        delta = tuple(p[i] - origin[i] for i in range(3))
        return (sum(delta[i] * u[i] for i in range(3)), sum(delta[i] * v[i] for i in range(3)))

    poly_a = relation._ensure_ccw([to_2d(p) for p in verts_a])
    poly_b = relation._ensure_ccw([to_2d(p) for p in verts_b])
    overlap = relation._clip_2d(poly_a, poly_b)
    if len(overlap) < 3:
        return False
    return abs(relation._shoelace_area(overlap)) > _MIN_CONTACT_AREA


def _authored_polys_world(actor) -> list:
    """Every authored polygon of `actor`'s own brush, as a snapped world-space vertex ring --
    `crosses [raw]`/`touches [raw]`'s and the resolved tier's source-side ("brush B") input, which
    is always the brush's own full authored shape, never a resolved/decomposed one."""
    return [[actorgraph._snap_coord(v) for v in polyalign._world_verts(actor, p)]
            for p in actor.brush.polys]


def _any_polygons_cross(polys_a: list, polys_b: list) -> bool:
    return any(_polygons_cross(fa, fb) for fa in polys_a for fb in polys_b
               if len(fa) >= 3 and len(fb) >= 3)


# The resolved tier's own volume floor -- derived from CSG_TOLERANCE the same way _MIN_CONTACT_AREA
# derives an area floor from it (CSG_TOLERANCE ** 2): a cubic volume below CSG_TOLERANCE ** 3 is not
# a real geometric distinction in a resolved model, any more than an area below CSG_TOLERANCE ** 2
# is. Used both to drop float-dust pieces from `_partition_by_brushes` and as `carves`'s own `> eps`
# volume threshold (spec: "a named volume tolerance for carves's > eps, resolved tier -- CARVE_AREA_EPS
# was an area and does not transfer").
CARVE_VOLUME_EPS = CSG_TOLERANCE ** 3


def _piece_centroid(cell) -> tuple:
    """A convex cell's vertex centroid -- always interior to the cell (a convex hull's centroid
    always is), so it is a valid representative point for ANY per-point predicate that is constant
    over the whole cell (see `_partition_by_brushes`)."""
    n = len(cell.vertices)
    return tuple(sum(v[i] for v in cell.vertices) / n for i in range(3))


def _partition_by_brushes(query_cell, brush_actors, ctx: SurveyContext) -> list:
    """`query_cell` split into convex sub-pieces, each fully INSIDE or fully OUTSIDE every one of
    `brush_actors`' own decomposed cells -- an ARRANGEMENT over the query region, not an attribution
    to any one brush. Every surviving piece's membership in every listed brush is therefore constant
    across the whole piece, which is what lets a per-brush point-predicate be evaluated ONCE per
    piece (at its centroid, `_piece_centroid`) and be exactly right for every point in it -- the
    "split by the ordered earlier/later brushes' half-spaces into convex sub-pieces" the spec's
    `occupies` section calls for. Order of `brush_actors` does not matter for the SPLIT itself (only
    for how a caller later reads "last writer" off the pieces); pieces with volume at or below
    `CARVE_VOLUME_EPS` are dropped as float dust, not real geometry."""
    pieces = [query_cell]
    for actor in brush_actors:
        for cutter in actorgraph.decompose_convex(actor, cache=ctx.cells):
            next_pieces = []
            for p in pieces:
                inside = _cell_intersection(p, cutter)
                if inside is not None:
                    next_pieces.append(inside)
                next_pieces.extend(_subtract_cell(p, cutter))
            pieces = next_pieces
    return [p for p in pieces if cell_volume(p) > CARVE_VOLUME_EPS]


@dataclass(frozen=True)
class CsgFace:
    """One resolved PLANE authored by one actor, not one BSP fragment.

    `csg_faces` collapses every surviving fragment of the same owner's same plane into one of these.
    That is both the dedup `H1` asks for (a single authored face routinely splits into many, and a
    naive per-surf loop would report one relationship N times) and the operative form of the spec's
    soundness rule: deciding a fact against a PLANE rather than against the existence of a
    particular fragment means a redundant coplanar face appearing or vanishing in a truncated solve
    cannot change the answer."""
    owner: str
    normal: tuple
    offset: float
    verts: list


def _canonical_plane(verts):
    """`(unit normal, offset)` for a world-space ring, with the normal's SIGN canonicalized so two
    oppositely-wound fragments of one plane produce one key. Returns None for a degenerate ring.

    The sign rule is "the first component whose magnitude exceeds 1e-9 is positive" -- arbitrary,
    but deterministic and orientation-free, which is all a plane IDENTITY needs. Facing direction is
    not lost by this: where a relation needs it (Task 12's depth sign), it is measured against the
    surveyed actor's own geometry, not read off this normal."""
    raw = newell([tuple(float(c) for c in v) for v in verts])
    length = (raw[0] ** 2 + raw[1] ** 2 + raw[2] ** 2) ** 0.5
    if length < 1e-9:
        return None
    n = tuple(c / length for c in raw)
    first = next((c for c in n if abs(c) > 1e-9), 0.0)
    if first < 0:
        n = tuple(-c for c in n)
    v0 = tuple(float(c) for c in verts[0])
    return n, sum(n[i] * v0[i] for i in range(3))


def _ring_meets_region(verts, lo, hi) -> bool:
    """Does a world ring's own AABB overlap the region box -- on ALL THREE axes at once?

    The question a face has to answer is "does this polygon MEET the region", so this is an
    AABB-vs-AABB overlap test: per axis, each box's low end at or below the other's high end, and
    that must hold on EVERY axis (hence `all(...)`, across the three axes of one comparison).
    Same keep/drop decision `bounded_cost.py::face_signature` reaches when it clips each surviving
    surface to the region and keeps whatever still has area, minus the clipping this caller does
    not need: a ring whose AABB misses the box on any axis cannot have any part inside it.
    `CSG_TOLERANCE` of slack on each side so a face exactly flush with the region's edge counts.

    What this replaced, and why: the first draft asked whether ANY vertex had ANY single coordinate
    inside that coordinate's own range, OR-ed across axes. That is not a containment test at all --
    on the 512x64x512 wall fixture, a region around a point on the wall's +Y face also keeps the +X
    face 256 uu away, because that face happens to have a vertex whose y lands in the region's y
    band. It over-selects rather than under-selects, so the cost was wasted candidate planes for
    every relation to re-reject, not missing facts.

    Conservative in one direction only: a ring's AABB can overlap the box while the polygon itself
    does not (a diagonal face clipping a corner). That keeps an extra candidate plane, which the
    per-relation tests then reject on their own geometry -- it never invents a fact."""
    ring_lo = tuple(min(float(v[i]) for v in verts) for i in range(3))
    ring_hi = tuple(max(float(v[i]) for v in verts) for i in range(3))
    return all(ring_lo[i] <= hi[i] + CSG_TOLERANCE and lo[i] <= ring_hi[i] + CSG_TOLERANCE
               for i in range(3))


def csg_faces(probe, region) -> list:
    """Every resolved plane MEETING `region` that an actor authored, one `CsgFace` per (owner, plane).

    A surface with no source actor (`SolvedSurface.actor is None` -- a BSP node that joined to no
    source poly) names nobody and is dropped: a fact must name an actor. Fragments are deduped by
    owner plus plane coincidence within `CSG_TOLERANCE`, by a linear scan per owner rather than by
    rounding to a grid -- a rounded key decides two planes 0.001 uu apart differently depending on
    which side of a bucket boundary they fall, and the neighborhood's face count is small enough
    (hundreds) that the exact test costs nothing.

    `surf.world_verts` is snapped (`actorgraph._snap_coord`) before anything else reads it: it comes
    straight from the native solve's own point pool, which carries the SAME pre-existing authored
    float noise `decompose_convex` snaps for its own world verts (a `PrePivot`/vertex pair that
    should cancel to an exact integer but doesn't quite) -- unsnapped, a resolved face's own edge can
    sit a fraction of a uu off the brush's clearly-intended boundary, which is exactly what let a
    flush-adjacent brush register a nonzero footprint overlap (live UNATCO repro, `Brush186`'s
    Y-extent `576.000162` instead of `576.0`). Snapped BEFORE `_canonical_plane` so the face's own
    normal/offset are derived from the cleaned ring, not the noisy one."""
    lo, hi = (tuple(float(c) for c in region[0]), tuple(float(c) for c in region[1]))
    by_owner: dict = {}
    for surf in probe.world_surfaces:
        if surf.actor is None:
            continue
        verts = [actorgraph._snap_coord(v) for v in surf.world_verts]
        if not _ring_meets_region(verts, lo, hi):
            continue
        plane = _canonical_plane(verts)
        if plane is None:
            continue
        normal, offset = plane
        seen = by_owner.setdefault(surf.actor.name, [])
        if any(abs(sum(normal[i] * f.normal[i] for i in range(3)) - 1.0) <= 1e-6
               and abs(offset - f.offset) <= CSG_TOLERANCE for f in seen):
            continue
        seen.append(CsgFace(owner=surf.actor.name, normal=normal, offset=offset, verts=verts))
    return [f for faces in by_owner.values() for f in faces]


@dataclass(frozen=True)
class CsgFact:
    """One csg-tier line. Bare -- no relation in this tier carries a magnitude (spec, Output
    shape); `crosses` becomes a boolean predicate, deciding existence off `penetration_depth`'s own
    straddle+footprint logic without reporting the number."""
    src: str
    dst: str
    relation: str


def kind_of(actor, class_index) -> str:
    """`query.csg_kind`'s flat kind for a brush actor: one of add/subtract/semisolid/nonsolid/
    intersect/deintersect/mover. `is_mover` is the caller's authoritative answer, never guessed."""
    return query.csg_kind(actor, is_mover=movers.is_mover(actor, class_index))


# The brush kinds the editor's main CSG pass writes. A Nonsolid (`NF_NotCsg`) bounds no solid and
# removes none; an Intersect/Deintersect rewrites its own brush and never the world; a Mover is
# excluded from world CSG entirely (spec's `crosses` table, measured in `test_csg_kind_facts.py`).
# None of them can own a point of the resolved world. A Semisolid does, but in a later pass.
_WORLD_PASS_KINDS = frozenset({"add", "subtract"})


@dataclass(frozen=True)
class SurveyContext:
    """Everything the five csg relations share, built ONCE per survey.

    `neighbors` is the solve set (trunk order, including the level's first world-CSG brush whether
    or not it is near). `near` is the subset that really meets the region -- the only actors any
    fact may name. `probe` is one `build_geometry_bspcsg` call's output; `faces` is its surfaces
    deduped to one entry per (owner, plane); `cells` is the decomposition cache shared with the raw
    tier so no brush is decomposed twice in one survey.

    `csg_order` is `neighbors` reduced to the brushes that write the resolved world and ordered the
    way the editor applies them -- every Add and Subtract in trunk order, then the semisolids, which
    a later pass applies and no Subtract in the trunk can cut (`csgRebuild`'s LOOP 2/LOOP 3, native's
    `detail_pass`). `resolved_matter_of` walks it, and `csg_index` is that list's name -> position
    map so it does not rebuild one per call.

    `aabbs` is `_brush_bounds`' memo: one float AABB per decomposed brush, the prefilter in front of
    every `point_in_brush` the contact search makes. `kinds` memoizes `kind_of` the same way --
    `movers.is_mover` walks the class ancestry on every call, and the contact search asks for a
    brush's kind thousands of times per survey (measured at 22% of the tier's whole runtime).
    `planes` is `_own_planes`' memo, for the same reason.

    `trunk_index` is `level.order`'s name -> position map -- the FULL trunk order, unlike
    `csg_index` which only covers `_WORLD_PASS_KINDS`. A Nonsolid carve victim has no `csg_index`
    entry at all; ordering checks that only ever compare within one loop (`_victim_matter_just_before`,
    `_carves_volume` -- victim-vs-subtract, or subtract-vs-subtract, never semisolid-vs-world-pass)
    read `trunk_index` instead, safely: trunk and LOOP order agree whenever a semisolid is never one
    of the two actors being compared.

    `crossing_index` is the one ordering `crosses [csg]`/`carves [csg]`/`occupies [csg]` need and
    neither `csg_index` nor `trunk_index` gives correctly: both a world-pass kind (add/subtract)
    AND Nonsolid in trunk order (Nonsolid is excluded from `_WORLD_PASS_KINDS` only because it
    writes no solid, not because it processes at a different time -- a later Subtract can still
    carve its faces, same as an Add's), THEN semisolids in their own trunk order. Unlike
    `trunk_index`, comparing a semisolid against a world-pass actor through this map always agrees
    with real LOOP 2/LOOP 3 order, regardless of which one happens to be authored first in the
    file (confirmed against the counterexample that found this: a Semisolid authored before an
    overlapping Add still correctly crosses AS THE TARGET, never the intruder, since it processes
    after)."""
    level: object
    class_index: object
    defaults: object
    name: str
    surveyed: object
    region: tuple
    neighbors: list
    near: list
    points: list
    probe: object
    faces: list
    cells: dict
    csg_order: list
    csg_index: dict
    trunk_index: dict
    crossing_index: dict
    aabbs: dict
    kinds: dict
    planes: dict


def build_context(level, class_index, name: str, defaults, *, cells=None) -> SurveyContext:
    """Build the shared csg-tier context. Raises `ActorNotFoundError` for an unknown name and
    `preview_native.NativePreviewError` when the native extension is missing or the solve fails --
    both mapped to exit 2 by the CLI handler (Task 18)."""
    from .preview_native import solve_world_probe
    if name not in level.actors:
        raise ActorNotFoundError(name)
    surveyed = level.actors[name]
    region = region_of(surveyed, defaults)
    neighbors = neighborhood(level, class_index, surveyed, defaults)
    probe = solve_world_probe(neighbors, class_index)
    kinds = {a.name: kind_of(a, class_index) for a in neighbors}
    csg_order = ([a for a in neighbors if kinds[a.name] in _WORLD_PASS_KINDS]
                 + [a for a in neighbors if kinds[a.name] == "semisolid"])
    crossing_order = ([a for a in neighbors
                        if kinds[a.name] in _WORLD_PASS_KINDS or kinds[a.name] == "nonsolid"]
                       + [a for a in neighbors if kinds[a.name] == "semisolid"])
    return SurveyContext(
        level=level, class_index=class_index, defaults=defaults, name=name, surveyed=surveyed,
        region=region,
        neighbors=neighbors,
        near=[a for a in near_brushes(level, class_index, surveyed, defaults) if a.name != name],
        points=[a for a in nearby_point_actors(level, surveyed, defaults) if a.name != name],
        probe=probe,
        faces=csg_faces(probe, region),
        cells={} if cells is None else cells,
        csg_order=csg_order,
        csg_index={a.name: i for i, a in enumerate(csg_order)},
        trunk_index={n: i for i, n in enumerate(level.order)},
        crossing_index={a.name: i for i, a in enumerate(crossing_order)},
        aabbs={},
        kinds=kinds,
        planes={},
    )


# The spec's own `crosses` table, stated positively. Each row was measured against the native CSG
# core, not reasoned from the kind's name (spike.md §1; regression `test_csg_kind_facts.py`):
#   add        contributes solid                                     -> source and target
#   semisolid  contributes real solid and collides like solid        -> source and target
#   subtract   no solid of its own, but authors real carved faces     -> target only
#   nonsolid   NF_NotCsg: its nodes bound no solid, the walk passes   -> neither
#   intersect/deintersect  contribute nothing whatever                -> neither
#   mover      excluded from world CSG, so nothing can cross INTO it, but it carries a real private
#              UModel of genuine solid matter treated exactly like an Add's (owner ruling, Round 8)
#                                                                     -> source only
_CROSSES_SOURCE_KINDS = frozenset({"add", "semisolid", "mover"})
_CROSSES_TARGET_KINDS = frozenset({"add", "semisolid", "subtract"})


def crosses_source_eligible(actor, class_index, defaults) -> bool:
    """Can this actor's own matter be the INTRUDER on a `crosses` line? A non-brush actor never
    does now -- point actors are treated as bare `Location` points, never a collision cylinder, so
    they carry no matter of their own to cross with. `defaults` is accepted but unused -- kept so
    every caller's call shape stays the same."""
    if actor.brush is None:
        return False
    return kind_of(actor, class_index) in _CROSSES_SOURCE_KINDS


def crosses_target_eligible(actor, class_index) -> bool:
    """Can this actor be the `dst` of a `crosses`/`touches` line -- i.e. does it author a resolved
    face something can be flush against or penetrate? A non-brush actor never does: its collision
    cylinder is not world geometry."""
    if actor.brush is None:
        return False
    return kind_of(actor, class_index) in _CROSSES_TARGET_KINDS


def _source_cells(ctx: SurveyContext, actor) -> list["actorgraph.ConvexCell"] | None:
    """The convex PIECES that stand for `actor`'s own contributed matter, or None when it has none.
    A BRUSH (Mover included -- its private model is treated exactly like an Add's, owner ruling
    Round 8) contributes one `actorgraph.ConvexCell` per `decompose_convex` cell, kept SEPARATE
    rather than flattened together; a NON-BRUSH actor contributes one group, its bare `Location`
    point wrapped in a `ConvexCell` with an EMPTY `half_spaces` -- there is no half-space bound for
    a single point, and `penetration_depth`'s own local-depth clip (see its docstring) reads that
    emptiness as "no known bound, fall back to the plain per-point reach."

    Returning the real `ConvexCell` (not just its bare vertices, as before Task 12's own locality
    fix) is what lets `penetration_depth` clip a brush piece to the region that ACTUALLY overlaps a
    face's footprint before measuring depth, using `half_spaces` -- see that function's docstring
    for why a footprint OVERLAP check alone does not bound the depth NUMBER.

    The grouping is load-bearing for `penetration_depth`, not cosmetic: an L- or U-shaped brush
    decomposes into more than one cell precisely because its overall vertex set is NOT convex --
    taking the hull of every cell's vertices TOGETHER fills in the notch, so a face lying in that
    notch would wrongly register overlap against matter the brush never actually has there. Each
    cell's own hull, tested independently, cannot make this mistake: a `ConvexCell` IS convex, so its
    own hull is its own true silhouette. No current fixture exercises a non-convex brush (every
    scenario brush here is a box, one cell), but `crosses` must stay correct for one regardless.

    Filtered to the SURVIVING matter only: each authored cell is split into convex sub-pieces by
    every Subtract LATER than `actor` in trunk order (`_partition_by_brushes`), and a piece is kept
    only when `resolved_matter_of` still holds at its centroid -- a point-membership filter on the
    straddle points, never a reshape of the convex cells into one (possibly non-convex) hull:
    `resolved_matter_of` of an Add is "authored body minus later subtracts", possibly non-convex, and
    `penetration_depth`'s own per-cell convex footprint (`_convex_hull_2d`) requires each group to
    stay convex. A per-corner-vertex test cannot do this -- a carve interior to a cell, touching none
    of its corners, is the ordinary case, not an edge case (see this function's own worked-example
    regression). A cell with no surviving piece at all contributes nothing crossable.

    An actor with no `Location` contributes nothing rather than being placed at the origin: a
    substituted position would invent a fact (this is the same rule `collision_clearance.py`'s own
    candidate walk applies, skipping any actor whose `location is None`)."""
    if actor.brush is not None:
        cells = actorgraph.decompose_convex(actor, cache=ctx.cells)
        later_subtracts = [a for a in ctx.csg_order[ctx.csg_index.get(actor.name, len(ctx.csg_order)) + 1:]
                           if ctx.kinds[a.name] == "subtract"]
        groups = []
        for cell in cells:
            for piece in _partition_by_brushes(cell, later_subtracts, ctx):
                if resolved_matter_of(ctx, actor, _piece_centroid(piece)):
                    groups.append(piece)
        return groups or None
    if actor.location is None:
        return None
    # Snapped like a brush's own vertices (Bug 1): `actor.location` is exact Decimal parsed straight
    # from T3D text (`model.parse_t3d` is schema-free, architecture.md "Coords"), so it can carry the
    # same class of authored float noise a brush vertex can -- and an unsnapped near-integer Location
    # hits the same exact-zero-area footprint gate this whole fix targets.
    loc = actorgraph._snap_coord(tuple(float(c) for c in actor.location))
    return [actorgraph.ConvexCell(vertices=[loc], half_spaces=[])]


def _convex_hull_2d(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """The CCW-wound convex hull of `points` (Andrew's monotone chain -- exact, no epsilon: every
    decision is a cross-product sign, and collinear points are dropped by the `<= 0` pop rather than
    kept as spurious extra edges).

    `penetration_depth` needs this because the world-space points standing for a source actor's own
    matter (a brush's decomposed-cell corners, or a collision cylinder's sample ring) are NOT stored
    in any 2-D cyclic order once projected onto a face's plane -- only their convex hull is a valid
    simple polygon `relation._clip_2d` can clip. The projection of a convex 3-D shape's vertex set is
    exactly the convex hull of the projected vertices (a standard fact of orthogonal projection), so
    this is exact for every source kind this module produces: `decompose_convex`'s cells are convex,
    and the collision cylinder is convex (its 27-point sampling is Task 11's own already-accepted
    approximation of a circle -- untouched here; this hull step adds no further approximation on top
    of it)."""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


# How far off a face to step when asking which of its two sides is solid. Comfortably clear of
# CSG_TOLERANCE (0.015 uu, the point-dedup resolution limit) so the probe never lands ON the plane,
# and far below the smallest real content feature the spike measured (0.043 uu penetration).
_SIDE_PROBE_STEP = 0.05


def _face_centroid(face: CsgFace) -> tuple:
    n = len(face.verts)
    return tuple(sum(v[i] for v in face.verts) / n for i in range(3))


def face_outward_sign(ctx: SurveyContext, face: CsgFace) -> float | None:
    """`+1` when SOLID lies on the face's `+normal` side, `-1` when it lies on the `-normal` side,
    `None` when the probe finds solid on both sides or neither (a face that bounds no solid here, or
    one whose centroid falls outside the solved region).

    Measured, never inferred from the ring's winding: `bspcsg.rs`'s leading-Add seed deliberately
    stores the world shell's faces REVERSED, and `csg_faces` canonicalizes the normal's sign anyway,
    so winding carries no usable facing. Stepping `_SIDE_PROBE_STEP` off the centroid and asking the
    native solidity query is the same oracle the CSG-kind regression uses."""
    if ctx.probe.solidity is None:
        return None
    c = _face_centroid(face)
    plus = tuple(c[i] + face.normal[i] * _SIDE_PROBE_STEP for i in range(3))
    minus = tuple(c[i] - face.normal[i] * _SIDE_PROBE_STEP for i in range(3))
    solid_plus = ctx.probe.solidity.point_is_solid(plus)
    solid_minus = ctx.probe.solidity.point_is_solid(minus)
    if solid_plus == solid_minus:
        return None
    return 1.0 if solid_plus else -1.0


def _overlap_lateral_planes(overlap: list[tuple[float, float]], u_axis, v_axis,
                            origin) -> list[tuple[tuple[float, float, float], float]]:
    """`overlap` (a CCW-wound 2-D polygon in the `(u_axis, v_axis)` frame anchored at `origin`),
    lifted one 3-D half-space per edge: zero component along `u_axis x v_axis` (the face's own
    normal), so each bounds the LATERAL extent only, leaving the along-normal reach unconstrained --
    intersecting a cell against every one of them (`_clip_cell`, repeated) clips it to the prism over
    `overlap`. Matches `relation._clip_2d`'s own CCW "inside" convention (`edx*(p.y-cy0) -
    edy*(p.x-cx0) >= 0`) rewritten as `dot(n, p) <= d`, the form `_clip_cell` takes.

    `(nu, nv)` is normalized to unit length before it becomes `normal_3d` -- every other half-space
    builder in this module (`decompose_convex`, `_cell_intersection`) hands `_polytope_from_planes`
    unit normals, and `_polytope_from_planes`'s vertex filter uses a fixed ABSOLUTE epsilon
    (`actorgraph._VERTEX_EPS`), so a raw, unnormalized `(edy, -edx)` inflates the real per-plane
    slack to `eps / |edge|`: a short overlap edge -- exactly the hairline-overlap case this whole fix
    targets -- can blow that slack up to several times `CSG_TOLERANCE`. Unit normals also keep
    `_same_plane` (which assumes them, `abs(dot(n, n') - 1.0) <= 1e-6`) working on these planes."""
    planes = []
    n = len(overlap)
    for i in range(n):
        cx0, cy0 = overlap[i]
        cx1, cy1 = overlap[(i + 1) % n]
        edx, edy = cx1 - cx0, cy1 - cy0
        length = (edx * edx + edy * edy) ** 0.5
        if length == 0.0:
            continue           # a duplicate/degenerate vertex pair (Sutherland-Hodgman can emit one
                                # on a tangent clip) contributes no real constraint -- skip it rather
                                # than pass a zero-normal "plane" into `_clip_cell`
        nu, nv = edy / length, -edx / length              # inside: nu*u + nv*v <= d
        d = nu * cx0 + nv * cy0
        normal_3d = tuple(nu * u_axis[k] + nv * v_axis[k] for k in range(3))
        offset_3d = d + sum(normal_3d[k] * origin[k] for k in range(3))
        planes.append((normal_3d, offset_3d))
    return planes


def penetration_depth(ctx: SurveyContext, cells, face: CsgFace) -> float | None:
    """How far a source's own matter reaches past `face` INTO the solid it bounds, or None when it
    does not: the source has to have SOME point past the plane by more than `CSG_TOLERANCE` on the
    solid side, ANOTHER point on the VOID side, AND its own silhouette has to genuinely overlap the
    face's own surviving footprint. `cells` groups the source's points by convex piece (see
    `_source_cells`) -- each piece is tested independently, and the reported depth is the max over
    whichever pieces' own hull actually overlaps this face.

    This is the spec's own definition -- "the intruding geometry's own maximum perpendicular
    distance past the crossed face's plane" -- and it is one shape for every source kind, brush and
    collision extent alike (owner ruling, Round 8). Measuring against the PLANE, not by an isotropic
    clearance, is also what keeps a deeply-buried actor honest: the spike's bisection saturates at
    its own shrink floor there and its `_stats` has to exclude such actors from every percentile.

    **Both-sides check, not just "some point past the plane."** Review finding, Task 12 round 2: a
    source can have every one of its points on the solid side of a face -- e.g. a shelf that just
    happens to sit inside a wall's own footprint, nowhere near the wall's void -- and the old check
    ("some point past the plane, within the footprint") fired anyway, because "past the plane" alone
    doesn't distinguish "genuinely crossing it" from "sitting entirely beyond it already." Confirmed
    live on `shelf_pokes_through_a_niche_wall`: surveying `Additive2` reported
    `Additive4 --crosses--> Additive2`, which the spec's own locality rule
    (`actor-survey-and-actor-relation-csg-resolved/spec.md:315-319`) says must never fire. `crosses`
    means the source's OWN matter spans both sides of the boundary -- some of it still claiming the
    void side, the rest pushing into the solid side it doesn't own -- not merely "some of it is over
    there." So each cell's own points must include one with `past > CSG_TOLERANCE` (solid side) AND
    one with `past < 0` (void side); a cell failing either check contributes no depth, regardless of
    how far past the plane its solid-side point reaches.

    **Per-cell footprint and per-cell straddle, never pooled across cells.** Review finding, Task 12
    round 2, Important #2: pooling every cell's vertices into ONE hull before clipping is wrong for a
    non-convex (L/U-shaped) brush -- the pooled hull fills in a notch neither cell's own matter
    reaches, so a face lying in that notch would wrongly overlap. Each cell is convex
    (`decompose_convex`'s own guarantee), so ITS hull is its true silhouette; testing cells
    independently and taking the max depth over the ones that qualify is exact for any cell count,
    where the old pooled-hull approach was only safe by accident for the single-cell (box) brushes
    every current fixture happens to use.

    Bounded to the face's OWN footprint, because the spec says "within the overlap region" and a
    plane is unbounded where a face is not. Without the bound, a source point nowhere near this
    face -- across the room, past the end of the wall -- still sits on the solid side of the face's
    infinite plane, and `crosses` would fire against an actor the source never reaches.

    The bound is EXACT polygon intersection, not per-point ray-cast membership (owner ruling: "I want
    this exact, not approximate" -- no epsilon-based nudge or inset). A cell's own points are
    projected onto the face's plane and reduced to their convex hull (`_convex_hull_2d`) -- that
    cell's silhouette -- which is then clipped against the face's own stored vertex ring (`ring_uv`)
    with the same Sutherland-Hodgman `relation._clip_2d` this codebase already uses for exact
    footprint overlap (`actorgraph._footprint_overlap_area`, `relation.classify_footprint_2d`). A
    non-empty, non-zero-area clipped polygon is the exact geometric fact "this cell's own matter, in
    projection, meets this face's own surviving footprint" -- there is no boundary tie to resolve,
    because Sutherland-Hodgman produces the true intersection polygon, vertices ON the clip edge
    included, rather than asking a single point "in or out" of a ring it may sit exactly on.

    **Bounded to the LOCAL overlap, not just gated on it.** Round-N finding, live UNATCO repro: a
    footprint OVERLAP check only answers "does this cell's silhouette touch the face's footprint AT
    ALL", a yes/no gate -- it does not bound the depth NUMBER to the region that actually overlaps.
    `max(past)`/`min(past)` over the cell's ENTIRE own point set (every corner, however far from the
    footprint touch) can pull in a corner that has nothing to do with the touch itself: a large,
    elongated brush piece grazing a small target at one hairline corner still carries its own
    far corner, hundreds of uu away, into `max(past)` -- reporting that unrelated distance as the
    "depth" of a graze, and (worse) letting that far corner's own void-side reach satisfy the
    both-sides straddle check for a touch that, locally, may not straddle at all. This is exactly
    the gap this function's own docstring used to flag and defer ("if a rotated case turns up,
    report it rather than reaching for a nearest-owner-style narrowing on your own") -- the
    "axis-aligned source spans its entire silhouette uniformly" argument that used to justify
    skipping this only holds for a source that is a plain axis-aligned BOX; a convex piece left over
    from carving against a non-axis-aligned neighbor is not guaranteed to be one, and real UNATCO
    content is not all axis-aligned.

    Fixed by clipping the cell's own 3-D volume to the LATERAL prism over `overlap` (its footprint
    intersected with the face's own ring, computed above) before ever reading `past` -- reusing
    `_clip_cell` (the same primitive `_partition_by_brushes`/`authored_shape_contains` already use),
    once per edge of `overlap` lifted to a 3-D half-space with zero component along `face.normal`
    (so it bounds the LATERAL extent only, leaving the along-normal reach free). `past` is then read
    off the CLIPPED polytope's own vertices -- exact for any convex cell shape, not just a uniform
    box, because the clip is a genuine 3-D polytope intersection, not a per-point (u,v)-membership
    filter (which does NOT work here: every corner of a box shares the same handful of (u,v)
    footprint locations regardless of depth, so filtering individual corners by whether their OWN
    projection lands inside `overlap` would exclude every one of them just as often as it excludes
    the right ones -- the bound has to come from clipping the shape itself, not from selecting which
    of its existing vertices to keep).

    Only for a group that carries real `half_spaces` (a brush's own decomposed cell): a sampled
    collision cylinder (`_source_cells`'s non-brush branch) has none -- there is no exact half-space
    bound for a sampled circle -- and keeps the plain per-point reach unchanged; that source kind is
    always a small, bounded actor extent and does not exhibit this gap in practice.

    `project_to_plane` defaults its origin to the polygon's first vertex, so the ring and each cell's
    points MUST be projected against the same explicit origin or the two land in unrelated frames
    (that function's own docstring, and the bug it cites).

    This is NOT the nearest-owner-wins filter, and must never be turned into one. That filter would
    compare SEVERAL faces against each other and keep only the closest owner, discarding true facts
    about the rest -- a new rule this plan has no authority to invent. This is a per-face bound
    asking one local question, "does this source's own matter genuinely cross this face", answered
    from that one face's own geometry with no reference to any other face or owner."""
    if not cells:
        return None
    sign = face_outward_sign(ctx, face)
    if sign is None:
        return None
    origin = face.verts[0]
    ring_uv = relation._ensure_ccw(relation.project_to_plane(face.verts, face.normal, origin=origin))
    u_axis, v_axis = relation._plane_basis(relation._norm(face.normal))
    best = None
    for group in cells:
        points = group.vertices
        footprint_uv = _convex_hull_2d(relation.project_to_plane(points, face.normal, origin=origin))
        if len(footprint_uv) < 3:
            continue
        overlap = relation._clip_2d(footprint_uv, ring_uv)
        if len(overlap) < 3 or relation._shoelace_area(overlap) == 0.0:
            continue           # this cell's own silhouette never meets this face's footprint
        depth_points = points
        if group.half_spaces:
            bounded = group
            for normal_3d, offset_3d in _overlap_lateral_planes(overlap, u_axis, v_axis, origin):
                bounded = _clip_cell(bounded, normal_3d, offset_3d)
                if bounded is None:
                    break
            if bounded is None:
                continue        # the 3-D overlap has no real volume (a boundary-only 2-D touch)
            depth_points = bounded.vertices
        past = [sign * (sum(face.normal[i] * p[i] for i in range(3)) - face.offset)
                for p in depth_points]
        cell_max = max(past)
        if cell_max <= CSG_TOLERANCE or min(past) >= 0.0:
            continue           # doesn't reach solid, or never has matter on the void side either
        best = cell_max if best is None else max(best, cell_max)
    return best


# Kind sets for `crosses [csg]`/`carves [csg]`'s shared geometric test (spec,
# `dev/specs/commands/actor-survey.md`) -- separate from `_CROSSES_SOURCE_KINDS`/
# `_CROSSES_TARGET_KINDS` above, which `touches [csg]` still depends on unmodified. "A" is the
# target (the one whose polygon gets crossed/carved), "B" is the intruder.
_CROSSING_A_KINDS = frozenset({"add", "semisolid", "subtract", "nonsolid"})
_CROSSING_B_KINDS = frozenset({"add", "semisolid", "nonsolid", "mover"})


def _csg_order_position(ctx: SurveyContext, actor) -> float:
    """`actor`'s CSG-order position, for the `crosses [csg]`/`carves [csg]`/`occupies [csg]`
    ordering check only -- a Mover's position is defined as AFTER every real brush here (spec's
    Mover note), never a change to `ctx.csg_order`/`ctx.csg_index`/`ctx.trunk_index`/
    `ctx.crossing_index` themselves. Uses `ctx.crossing_index`, not `ctx.trunk_index`: a Semisolid
    always processes after every world-pass brush (LOOP 2 then LOOP 3) regardless of which one it
    was authored before in the file, and raw trunk position gets exactly that comparison backwards
    whenever the two disagree. `crossing_index` is the one ordering that both covers Nonsolid
    (absent from `csg_index`) and keeps semisolid-vs-world-pass comparisons correct."""
    if ctx.kinds.get(actor.name) == "mover":
        return math.inf
    return ctx.crossing_index.get(actor.name, math.inf)


def _resolved_prefix_probe(ctx: SurveyContext, before, *, probe_cache=None):
    """The native CSG probe (surviving world surfaces + point-in-solid oracle), resolved using
    only the neighborhood brushes strictly before `before` in CSG order -- "resolved up until
    right before B" (spec), as one shared solve. `_resolved_prefix_fragments` reads its surfaces;
    `occupies [csg]`'s void test reads its solidity oracle -- both must read the SAME solve, not
    two separate ones that could disagree on where exactly the prefix cuts off.

    `probe_cache`, when given, memoizes the expensive native solve by `before`'s CSG-order
    position -- `crosses_facts_for`/`carves_facts_for`/`connects_facts_for`/`occupies_facts_for`
    each hold `before` fixed across an entire loop over candidate actors, so without this the
    identical solve reran once per candidate instead of once per call. Scoped to one caller's own
    dict, passed in explicitly (never stored on `ctx`, which is reused across unrelated relation
    calls for the whole survey)."""
    from .preview_native import solve_world_probe
    limit = _csg_order_position(ctx, before)
    if probe_cache is not None and limit in probe_cache:
        return probe_cache[limit]
    prefix = [a for a in ctx.neighbors if _csg_order_position(ctx, a) < limit]
    probe = solve_world_probe(prefix, ctx.class_index)
    if probe_cache is not None:
        probe_cache[limit] = probe
    return probe


def _resolved_prefix_fragments(ctx: SurveyContext, actor, before, *, probe_cache=None) -> list:
    """Every surviving world-surface fragment `actor` owns, resolved using only the neighborhood
    brushes strictly before `before` in CSG order -- "A resolved up until right before B" (spec).
    Every fragment, UN-deduplicated by plane: `csg_faces`'s per-(owner, plane) dedup keeps only the
    first fragment it meets and silently drops the rest, which is the exact bug this whole fix
    chases (confirmed live on `Brush693`'s notched top face, `nyc_unatco_island`) -- a straddle
    this relation needs can live in a fragment the dedup never kept."""
    probe = _resolved_prefix_probe(ctx, before, probe_cache=probe_cache)
    return [[actorgraph._snap_coord(v) for v in surf.world_verts]
            for surf in probe.world_surfaces
            if surf.actor is not None and surf.actor.name == actor.name]


def _crosses_relation(ctx: SurveyContext, a, b, *, probe_cache=None) -> bool:
    """Does B cross A -- `crosses [csg]`'s test: A before B in CSG order, and some polygon of A
    (resolved up until right before B) is non-coplanar with, and interior-shares a point with,
    some authored polygon of B."""
    if _csg_order_position(ctx, a) >= _csg_order_position(ctx, b):
        return False
    frags_a = _resolved_prefix_fragments(ctx, a, b, probe_cache=probe_cache)
    if not frags_a:
        return False
    return _any_polygons_cross(frags_a, _authored_polys_world(b))


def _carves_relation(ctx: SurveyContext, victim, subtract, *, probe_cache=None) -> bool:
    """Does `subtract` carve `victim` -- `_crosses_relation`'s test, PLUS total removal.

    Not just `_crosses_relation`: a non-coplanar crossing pair can never exist when `subtract`
    fully encloses `victim` (no boundary crossing is possible there -- the same topological
    argument that makes `crosses` correctly SILENT on full enclosure, since it competes with
    `occupies`). `carves` has no such competing relation, and total removal is legitimate,
    already-tested behavior (`test_carves_fires_for_total_removal_with_no_accompanying_touches`),
    so it needs its own clause: `victim`'s full AUTHORED shape entirely inside `subtract`'s full
    authored shape, independent of resolution order -- reusing `authored_shape_contains`, the raw
    tier's own full-containment test, rather than inventing a second one."""
    if _crosses_relation(ctx, victim, subtract, probe_cache=probe_cache):
        return True
    if _csg_order_position(ctx, victim) >= _csg_order_position(ctx, subtract):
        return False
    return authored_shape_contains(subtract, victim, ctx.cells)


# Grid resolution for sampling a 2D overlap region -- enough to catch an ordinary doorway-sized
# opening positioned anywhere within a much larger shared wall, not just at its centroid
# (confirmed live: `test_connects_finds_a_real_opening_off_the_old_probe_cross`'s off-centre
# doorway, missed by a centroid-only sample the same way the old mechanism's own fixed 5-point
# fan missed it before `_region_grid_probes` widened it).
_CONTACT_GRID_N = 6


def _point_in_convex_2d(poly: list, p) -> bool:
    """Is `p` inside (or on the boundary of) the convex 2D polygon `poly` -- every edge's cross
    product with `p` must agree in sign (CCW winding, same convention `relation._ensure_ccw`
    produces)."""
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        cross = (bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax)
        if cross < -1e-9:
            return False
    return True


def _grid_samples_in_convex_2d(poly: list) -> list:
    """A small grid of 2D points inside convex polygon `poly`, plus its centroid -- the centroid
    alone can miss a real opening that doesn't happen to be centred in a much larger shared
    region; see `_CONTACT_GRID_N`'s own note."""
    n = len(poly)
    cx = sum(p[0] for p in poly) / n
    cy = sum(p[1] for p in poly) / n
    lo_x = min(p[0] for p in poly)
    hi_x = max(p[0] for p in poly)
    lo_y = min(p[1] for p in poly)
    hi_y = max(p[1] for p in poly)
    samples = [(cx, cy)]
    steps = _CONTACT_GRID_N
    for i in range(steps):
        for j in range(steps):
            gx = lo_x + (i + 0.5) * (hi_x - lo_x) / steps
            gy = lo_y + (j + 0.5) * (hi_y - lo_y) / steps
            if _point_in_convex_2d(poly, (gx, gy)):
                samples.append((gx, gy))
    return samples


def _polygon_overlap_points(verts_a, verts_b) -> list:
    """`(world point, unit normal)` sites across the real 2D overlap area between two coplanar
    polygons (a grid, see `_grid_samples_in_convex_2d`), or `[]` if they aren't coplanar or the
    overlap isn't a real area (not just a point or edge) -- the probe sites `_matter_side`
    straddles to DECIDE a `touches`/`connects` fact.

    This replaces area-contact's own normal-direction heuristic for deciding the fact: which
    facing convention means "touch" depends on WHICH side's polygon happens to have survived
    (the matter side's, the carving Subtract's, or neither), not on the relation, and is not
    knowable from the two polygons alone. Confirmed live on two shapes that broke it: two Adds
    butted face-to-face lose BOTH owners' faces at the shared plane
    (`two_adds_butted_face_to_face`), and a self-carved stub's cap belongs entirely to the
    Subtract that cut it, never to the matter actor whose authored body never had a face there
    (`shelf_pokes_through_a_niche_wall`). Finding the overlap is still pure polygon geometry --
    cheap, no CSG solve -- only the yes/no decision moves to a matter-side probe."""
    pa, pb = _plane_of(verts_a), _plane_of(verts_b)
    if pa is None or pb is None:
        return []
    na, oa = pa
    nb, ob = pb
    dot = sum(na[i] * nb[i] for i in range(3))
    if abs(abs(dot) - 1.0) > 1e-6:
        return []                             # not coplanar
    if abs(oa - (ob if dot > 0 else -ob)) > CSG_TOLERANCE:
        return []                             # parallel but offset
    u, v = relation._plane_basis(na)
    origin = verts_a[0]

    def to_2d(p):
        delta = tuple(p[i] - origin[i] for i in range(3))
        return (sum(delta[i] * u[i] for i in range(3)), sum(delta[i] * v[i] for i in range(3)))

    poly_a = relation._ensure_ccw([to_2d(p) for p in verts_a])
    poly_b = relation._ensure_ccw([to_2d(p) for p in verts_b])
    overlap = relation._clip_2d(poly_a, poly_b)
    if len(overlap) < 3 or abs(relation._shoelace_area(overlap)) <= _MIN_CONTACT_AREA:
        return []
    return [(tuple(origin[i] + cx * u[i] + cy * v[i] for i in range(3)), na)
            for cx, cy in _grid_samples_in_convex_2d(overlap)]


def _matter_side(ctx: SurveyContext, actor, point, normal) -> int | None:
    """-1/+1 for the side of the plane through `point` (unit `normal`) `actor`'s resolved matter
    is on, or None when it is on both sides (penetration, not flush contact) or neither (not at
    this plane at all). The two probe points sit `CSG_TOLERANCE` off the plane -- that tolerance
    is the only thing deciding flush-vs-penetrating, matching every other "is this geometry here"
    check in this file."""
    step = CSG_TOLERANCE * 2
    inner = tuple(point[i] - normal[i] * step for i in range(3))
    outer = tuple(point[i] + normal[i] * step for i in range(3))
    at_inner = resolved_matter_of(ctx, actor, inner)
    if at_inner == resolved_matter_of(ctx, actor, outer):
        return None
    return -1 if at_inner else 1


def _was_solid_before(ctx: SurveyContext, subtract, point) -> bool:
    """Was `point` solid at the moment `subtract` ran -- i.e. did its carve remove anything HERE?
    Last writer among the brushes ahead of it in `ctx.csg_order`: an Add or Semisolid means
    matter was there, a Subtract means the space was already void. Where NO earlier brush reaches
    the point the answer is solid, because that is the world `MAP NEW` hands the first CSG brush
    -- carving the default-solid world is what an ordinary level's leading Subtract does, and it
    is a real carve."""
    index = ctx.csg_index.get(subtract.name, len(ctx.csg_order))
    for earlier in reversed(ctx.csg_order[:index]):
        if _in_authored_volume(ctx, earlier, point):
            return ctx.kinds[earlier.name] != "subtract"
    return True


def _at_own_boundary(ctx: SurveyContext, subtract, point, normal) -> bool:
    """Is `point` actually AT `subtract`'s own authored surface -- not floating deep inside (or
    well outside) its volume? `_in_authored_volume` must differ between the two probe points
    straddling the plane; if it doesn't, both land on the same side and the plane is nowhere near
    `subtract`'s real boundary (measured: an Add standing free in the middle of an enclosing
    Subtract's void reads "inside that Subtract's volume" everywhere in the void, firing at
    960uu of clearance on an earlier version of this check that skipped this half --
    `test_touches_does_not_fire_for_an_add_standing_free_in_a_subtracts_void`)."""
    step = CSG_TOLERANCE * 2
    inner = tuple(point[i] - normal[i] * step for i in range(3))
    outer = tuple(point[i] + normal[i] * step for i in range(3))
    return _in_authored_volume(ctx, subtract, inner) != _in_authored_volume(ctx, subtract, outer)


def _is_real_carve_boundary(ctx: SurveyContext, subtract, point, normal) -> bool:
    """Is `point` ON `subtract`'s own exposed carve boundary, with a GENUINE removal there --
    `_at_own_boundary` plus: on the side that IS inside `subtract`'s own volume, was it solid
    before? A no-op Subtract (dropped in empty space, or nested inside an already-void region)
    removes nothing even at its own boundary -- `touches` must reject that (there is no real
    matter-against-removed-matter contact), but `connects` must NOT use this stricter test: two
    Subtracts' voids are continuous whether or not either one's own carve was redundant
    (`test_connects_fires_for_a_fully_nested_redundant_subtract` -- `InnerCarve` removes nothing,
    already void from `OuterRoom`, and still connects to it). `connects` uses `_at_own_boundary`
    alone."""
    step = CSG_TOLERANCE * 2
    inner = tuple(point[i] - normal[i] * step for i in range(3))
    outer = tuple(point[i] + normal[i] * step for i in range(3))
    in_inner = _in_authored_volume(ctx, subtract, inner)
    in_outer = _in_authored_volume(ctx, subtract, outer)
    if in_inner == in_outer:
        return False
    return _was_solid_before(ctx, subtract, inner if in_inner else outer)


def _flush_contact(ctx: SurveyContext, a, b, point, normal, *, allow_void_boundary: bool) -> bool:
    """Do `a` and `b` meet flush at `point` across the plane `normal` straddles?

    Matter against matter: both survive here, and they must be on OPPOSITE sides -- the same side
    is one buried in the other. Matter against a carve boundary (one side's `_matter_side` is
    None because it contributes no matter at all, e.g. a Subtract): the OTHER side merely needs
    matter on ONE side, AND the ambiguous side must be a Subtract that genuinely carved HERE
    (`_is_real_carve_boundary`) -- `_matter_side` alone can't tell "this is a real carve boundary"
    from "this actor simply isn't here at all" (a buried peg's far side, a free-standing shelf
    nowhere near this Subtract's actual carve), since both read as the same unconditional None for
    a Subtract and as the same both-sides-equal None for an absent matter actor.
    `allow_void_boundary` gates this whole case (touches/connects allow it; neither side being
    matter at all is two carve boundaries meeting with nothing solid between, which is
    `connects`'s own territory, not `touches`)."""
    side_a = _matter_side(ctx, a, point, normal)
    side_b = _matter_side(ctx, b, point, normal)
    if side_a is not None and side_b is not None:
        return side_a != side_b
    if not allow_void_boundary:
        return False
    if side_a is not None and side_b is None:
        return _kind(ctx, b) == "subtract" and _is_real_carve_boundary(ctx, b, point, normal)
    if side_b is not None and side_a is None:
        return _kind(ctx, a) == "subtract" and _is_real_carve_boundary(ctx, a, point, normal)
    return False


def _contact_sites(ctx: SurveyContext, a, b) -> list:
    """Every candidate `(point, normal)` site where `a` and `b` might meet -- every coplanar,
    real-area-overlapping pair across BOTH actors' authored polygons, PLUS every one of either
    actor's own authored faces clipped against the OTHER actor's own AABB footprint in that
    face's plane. The second half is load-bearing, not a fallback for a rare case: a self-carved
    stub's cap face belongs entirely to the Subtract that cut it (confirmed live,
    `shelf_pokes_through_a_niche_wall`) -- the matter actor's own authored body, being an ordinary
    uncut box at the time it was authored, NEVER had a face at that plane, carve or no carve, so
    no polygon-to-polygon match can ever exist for that pair. The Subtract's own authored face
    alone is the only candidate plane there IS; clipping it to the matter actor's AABB (rather
    than sampling the Subtract's own, possibly much larger, full footprint) is what keeps the
    probe site landing inside the matter actor's real extent instead of empty space beside it.
    Pure authored geometry either way, no CSG solve -- only `_flush_contact`'s matter-side
    decision needs to ask what's actually there."""
    polys_a = _authored_polys_world(a)
    polys_b = _authored_polys_world(b)
    sites = []
    for pa in polys_a:
        if len(pa) < 3:
            continue
        for pb in polys_b:
            if len(pb) < 3:
                continue
            sites.extend(_polygon_overlap_points(pa, pb))
    sites.extend(_own_face_sites(ctx, polys_a, b))
    sites.extend(_own_face_sites(ctx, polys_b, a))
    return sites


def _own_face_sites(ctx: SurveyContext, polys, other) -> list:
    """Every polygon in `polys`, clipped to `other`'s own AABB footprint projected into that
    polygon's plane, as a grid of `(point, normal)` sites across the clipped region (see
    `_grid_samples_in_convex_2d`'s own note on why not just its centroid) -- the "no matching
    polygon on the other side" half of `_contact_sites` (see its own docstring)."""
    lo, hi = _brush_bounds(ctx, other)
    sites = []
    for poly in polys:
        if len(poly) < 3:
            continue
        plane = _plane_of(poly)
        if plane is None:
            continue
        normal, _offset = plane
        u, v = relation._plane_basis(normal)
        origin = poly[0]

        def to_2d(p):
            delta = tuple(p[i] - origin[i] for i in range(3))
            return (sum(delta[i] * u[i] for i in range(3)), sum(delta[i] * v[i] for i in range(3)))

        corners_3d = [(lo[0], lo[1], lo[2]), (hi[0], lo[1], lo[2]), (lo[0], hi[1], lo[2]),
                      (hi[0], hi[1], lo[2]), (lo[0], lo[1], hi[2]), (hi[0], lo[1], hi[2]),
                      (lo[0], hi[1], hi[2]), (hi[0], hi[1], hi[2])]
        corners_2d = [to_2d(c) for c in corners_3d]
        box_lo = (min(c[0] for c in corners_2d), min(c[1] for c in corners_2d))
        box_hi = (max(c[0] for c in corners_2d), max(c[1] for c in corners_2d))
        box_2d = [(box_lo[0], box_lo[1]), (box_hi[0], box_lo[1]),
                  (box_hi[0], box_hi[1]), (box_lo[0], box_hi[1])]
        poly_2d = relation._ensure_ccw([to_2d(p) for p in poly])
        overlap = relation._clip_2d(poly_2d, relation._ensure_ccw(box_2d))
        if len(overlap) < 3 or abs(relation._shoelace_area(overlap)) <= _MIN_CONTACT_AREA:
            continue
        for cx, cy in _grid_samples_in_convex_2d(overlap):
            point = tuple(origin[i] + cx * u[i] + cy * v[i] for i in range(3))
            sites.append((point, normal))
    return sites


def _touches_relation(ctx: SurveyContext, a, b) -> bool:
    """Does B touch A -- `touches [csg]`'s test: some site where `a`'s and `b`'s authored
    polygons coplanar-overlap has their resolved matter flush, one matter side against the
    other's real carve boundary at worst (never two carve boundaries meeting with nothing solid
    between -- that is `connects`, never this)."""
    return any(_flush_contact(ctx, a, b, point, normal, allow_void_boundary=True)
               for point, normal in _contact_sites(ctx, a, b))


def _any_matter_at(ctx: SurveyContext, point, normal) -> bool:
    """Is there solid matter at either probe point straddling `point`/`normal`, from ANY actor --
    not "is this `a`'s or `b`'s own matter" (neither contributes any, by construction, everywhere
    this is called: both are Subtracts with `_matter_side` already None), but "has some THIRD
    actor refilled this exact spot" (`two_rooms_split_by_an_intact_wall`'s `Wall`, authored after
    both rooms, sealing the gap between them -- two Subtracts both being void-contributors with
    nothing of their own here says nothing about whether a later Add filled the space between
    them). The pooled solidity oracle is the right tool for exactly this "is ANYTHING solid here"
    question -- `resolved_matter_of`'s own docstring warns against it only for "is THIS actor's
    matter here", a different question this never asks."""
    if ctx.probe.solidity is None:
        return False
    step = CSG_TOLERANCE * 2
    inner = tuple(point[i] - normal[i] * step for i in range(3))
    outer = tuple(point[i] + normal[i] * step for i in range(3))
    return ctx.probe.solidity.point_is_solid(inner) or ctx.probe.solidity.point_is_solid(outer)


def _connects_relation(ctx: SurveyContext, a, b) -> bool:
    """Does B connect with A -- `connects [csg]`'s test: some site where `a`'s and `b`'s authored
    polygons coplanar-overlap, or non-coplanar-cross, has void on both sides with nothing solid
    between -- the one shape `touches` must reject (two carve boundaries meeting) and `connects`
    exists for."""
    polys_a = _authored_polys_world(a)
    polys_b = _authored_polys_world(b)
    for pa in polys_a:
        for pb in polys_b:
            if len(pa) < 3 or len(pb) < 3:
                continue
            if _polygons_cross(pa, pb):
                return True
    for point, normal in _contact_sites(ctx, a, b):
        if (_matter_side(ctx, a, point, normal) is None
                and _matter_side(ctx, b, point, normal) is None
                and _at_own_boundary(ctx, a, point, normal)
                and _at_own_boundary(ctx, b, point, normal)
                and not _any_matter_at(ctx, point, normal)):
            return True
    # A fully NESTED Subtract never shares a boundary POINT with its container at all (its own
    # faces sit entirely inside the container's volume, nowhere near the container's own walls),
    # so the loop above can never find a site for it -- yet its void is trivially continuous with
    # the container's, redundant carve or not (`test_connects_fires_for_a_fully_nested_redundant_
    # subtract`, `pillar_in_room`'s `Room`/`Cutter`). Reuses the raw tier's own full-containment
    # test rather than inventing a second one (same reuse `_carves_relation` already does for its
    # own full-enclosure case).
    return authored_shape_contains(a, b, ctx.cells) or authored_shape_contains(b, a, ctx.cells)


def _void_carved_by(ctx: SurveyContext, subtract, points: list, before, *, probe_cache=None) -> bool:
    """Is ANY one of `points` void specifically BECAUSE OF `subtract` -- void in the world
    resolved up until right before `before` (with `subtract` present), and solid in that same
    world with `subtract` excluded? ANY, not EVERY: `points` are the centroids of the pieces
    `_occupies_relation` partitioned the occupant/subtract overlap into, each independently
    homogeneous -- requiring every piece to agree breaks the composability the spec and
    `_occupies_relation`'s own docstring both call for (an occupant seated across two Subtracts'
    voids reports `occupies` against both, independently). Confirmed live: `nyc_unatco_island`'s
    `Brush698`/`Brush570` lost its `occupies` fact because one small sliver of their overlap was
    also covered by `Brush693` (an unrelated floor slab) and genuinely solid there -- that ONE
    piece failing the void check wrongly vetoed the other two pieces, which are real, uncontested
    void `Brush570` carved.

    Still distinguishes "`subtract` is the operative carve here" from "this point merely sits
    inside `subtract`'s own authored volume and happens to be void for some other reason" -- the
    distinction the spec's own "the void `subtract` CARVES" wording draws. Without THIS check, a
    trunk-first, world-enclosing Subtract gets credited for a carve a nested, later Subtract
    actually made, purely because the point sits inside the outer one's authored volume too and
    is, incidentally, also void -- the exact historical bug class `occupies`'s old mechanism had
    an explicit "operative last-writer" condition to prevent (confirmed live: `dx_lum`'s
    `19_Multiport`, world-enclosing `Brush190` was wrongly credited alongside `Brush269`, the real
    carver, for the same niche). That distinction is now evaluated PER POINT, not just per the
    whole list -- a point only counts if `subtract` is its own operative carver, so a piece
    genuinely carved by some OTHER, more local Subtract still can't borrow `subtract`'s credit
    just by sharing the point list with a piece that legitimately can."""
    if not points:
        return True
    probe = _resolved_prefix_probe(ctx, before, probe_cache=probe_cache)
    void_points = [p for p in points
                   if probe.solidity is None or not probe.solidity.point_is_solid(p)]
    if not void_points:
        return False
    from .preview_native import solve_world_probe
    limit = _csg_order_position(ctx, before)
    without_subtract = [a for a in ctx.neighbors
                         if _csg_order_position(ctx, a) < limit and a.name != subtract.name]
    probe_without = solve_world_probe(without_subtract, ctx.class_index)
    if probe_without.solidity is None:
        # No world-CSG brush precedes `before` once `subtract` is excluded -- the empty world
        # `MAP NEW` hands the first CSG brush, which is default-SOLID (`_was_solid_before`'s own
        # base case), not "nothing is solid". `subtract` removing that default solid is exactly
        # the ordinary leading-Subtract carve, and must still count.
        return True
    return any(probe_without.solidity.point_is_solid(p) for p in void_points)


def _occupies_relation(ctx: SurveyContext, subtract, occupant, *, probe_cache=None) -> bool:
    """Does `occupant` occupy `subtract` -- `occupies [csg]`'s test: `subtract` before `occupant`
    in CSG order, and the void `subtract` carves (resolved up until right before `occupant`)
    fully contains `occupant`'s geometry WITHIN THE OVERLAP between the two -- i.e. `subtract` is
    the OPERATIVE carve there (`_void_carved_by`), not merely an enclosing Subtract the point also
    happens to sit inside.

    Deliberately an INTERSECTION test, not `authored_shape_contains`'s full containment: an
    occupant seated across two Subtracts' voids (neither of which alone contains all of it) must
    report `occupies` against BOTH, independently -- composing where full containment structurally
    cannot (confirmed live: `test_occupies_facts_for_composes_across_two_subtracts`'s `Bridge`,
    20uu into each of `RoomA`/`RoomB`, fully inside neither). The spec's own "fully contains"
    wording needs correcting to say this -- flagged, not silently reworded here.

    Brush occupant: `occupant`'s cells intersected with `subtract`'s own cells (no overlap at all
    -> immediate reject), then each resulting piece partitioned against every OTHER prefix brush
    (`_partition_by_brushes`) so the void test is evaluated once per piece, at its centroid, where
    it is exact for the whole piece -- not sampled at the cell's own vertices, which could miss a
    re-filling brush that cuts through a cell's middle without touching any corner.

    Non-brush occupant: its own `Location`, the one point it has."""
    if _csg_order_position(ctx, subtract) >= _csg_order_position(ctx, occupant):
        return False
    if occupant.brush is None:
        if occupant.location is None:
            return False
        point = tuple(float(c) for c in occupant.location)
        if not _in_authored_volume(ctx, subtract, point):
            return False
        return _void_carved_by(ctx, subtract, [point], occupant, probe_cache=probe_cache)
    limit = _csg_order_position(ctx, occupant)
    prefix = [a for a in ctx.neighbors if _csg_order_position(ctx, a) < limit]
    points = []
    found_overlap = False
    for oc in actorgraph.decompose_convex(occupant, cache=ctx.cells):
        for sc in actorgraph.decompose_convex(subtract, cache=ctx.cells):
            overlap = _cell_intersection(oc, sc)
            if overlap is None:
                continue
            found_overlap = True
            points.extend(_piece_centroid(piece)
                          for piece in _partition_by_brushes(overlap, prefix, ctx))
    if not found_overlap:
        return False
    return _void_carved_by(ctx, subtract, points, occupant, probe_cache=probe_cache)


def crosses_facts_for(ctx: SurveyContext) -> list[CsgFact]:
    """`crosses [csg]`: B's authored geometry non-coplanar-crosses A's geometry resolved up until
    right before B, with A before B in CSG order (spec). Fixed-direction -- B (the intruder)
    always leads -- computed both ways: the surveyed actor as B against every A-eligible neighbor,
    and as A against every B-eligible neighbor. Brush-vs-brush only (spec scope); non-brush point
    actors are not a source or target of this relation."""
    facts: dict = {}
    probe_cache: dict = {}

    def record(src, dst):
        facts[(src, dst)] = CsgFact(src=src, dst=dst, relation="crosses")

    def is_a(actor):
        return actor.brush is not None and _kind(ctx, actor) in _CROSSING_A_KINDS

    def is_b(actor):
        return actor.brush is not None and _kind(ctx, actor) in _CROSSING_B_KINDS

    if is_b(ctx.surveyed):
        for a in ctx.near:
            if is_a(a) and _crosses_relation(ctx, a, ctx.surveyed, probe_cache=probe_cache):
                record(ctx.name, a.name)
    if is_a(ctx.surveyed):
        for b in ctx.near:
            if is_b(b) and _crosses_relation(ctx, ctx.surveyed, b, probe_cache=probe_cache):
                record(b.name, ctx.name)

    return [facts[k] for k in sorted(facts)]


# The brush kinds that put real matter in the world. `_WORLD_PASS_KINDS`' Subtract writes the world
# but contributes no matter of its own, and a Mover is outside world CSG entirely while carrying a
# private model of genuine solid matter (spec's `crosses` table, owner ruling Round 8) -- so this is
# neither a subset nor a superset of that set, and both are needed.
_MATTER_KINDS = frozenset({"add", "semisolid", "mover"})


def _brush_bounds(ctx: SurveyContext, actor) -> tuple:
    """`actor`'s decomposed volume's world AABB, in floats, memoized on the context.

    A pure prefilter for `_in_authored_volume`: `actorgraph.point_in_brush` walks every cell's every
    half-space, and the contact search asks it thousands of times per survey against brushes that are
    nowhere near the point. `writes.actor_bounds` is not reused because it answers in Decimals over
    the actor's own polys; this has to compare against float probe points and must agree with the
    cells `point_in_brush` itself tests."""
    cached = ctx.aabbs.get(actor.name)
    if cached is None:
        verts = [v for cell in actorgraph.decompose_convex(actor, cache=ctx.cells)
                 for v in cell.vertices]
        cached = (tuple(min(v[i] for v in verts) for i in range(3)),
                  tuple(max(v[i] for v in verts) for i in range(3)))
        ctx.aabbs[actor.name] = cached
    return cached


def _kind(ctx: SurveyContext, actor) -> str:
    """`kind_of` behind the context's memo -- see `SurveyContext.kinds`."""
    kind = ctx.kinds.get(actor.name)
    if kind is None:
        kind = ctx.kinds[actor.name] = kind_of(actor, ctx.class_index)
    return kind


def _in_authored_volume(ctx: SurveyContext, actor, point) -> bool:
    """`actorgraph.point_in_brush` behind its own AABB. The slack is `actorgraph._VERTEX_EPS` --
    that function's OWN boundary tolerance, so the prefilter can never be tighter than the test it
    guards and can never drop a point the full test would have accepted."""
    lo, hi = _brush_bounds(ctx, actor)
    eps = actorgraph._VERTEX_EPS
    if any(point[i] < lo[i] - eps or point[i] > hi[i] + eps for i in range(3)):
        return False
    return actorgraph.point_in_brush(actor, point, cache=ctx.cells)


def resolved_matter_of(ctx: SurveyContext, actor, point) -> bool:
    """Does `actor`'s OWN matter still occupy `point` once the whole trunk has been applied?

    The per-actor question, not "whose space is this". Under a last-writer rule, where two Adds
    overlap the earlier actor's matter becomes invisible, so a peg buried 1-99 uu into a wall reads
    as resting against the wall rather than inside it (measured at every depth in 1..99, round 4).
    Such a rule is also structurally blind to a Mover or a point actor, neither of which is in
    `csg_order` at all, so neither could ever be named as a side of a contact -- contradicting the
    spec's "not source-restricted" and its "a Mover's private model is treated exactly like an
    Add's".

    The rule here is the editor's own: an Add's matter survives everywhere its authored body reaches
    except where a LATER Subtract removed it. Semisolids need no special case -- `csg_order` already
    places them after every world-pass brush, so nothing after one is a Subtract, which is exactly
    the "no Subtract in the trunk can cut a semisolid" rule. A Subtract contributes no matter of its
    own, so it is never this function's answer; the surface its carve leaves is
    `_is_carve_boundary`'s.

    A Mover is not in `csg_order`: it is excluded from world CSG, so no Subtract touches it and its
    own authored body IS its matter. A non-brush actor's matter is its bare `Location` point --
    `CollisionRadius`/`CollisionHeight` are ignored for point actors everywhere in this module, by
    owner ruling -- compared at `CSG_TOLERANCE`, the same float-noise floor every other "is this
    geometry here" check in this file uses, not an arbitrary tighter one: a caller probing near
    (not exactly at) the actor's `Location` -- `_matter_side`'s `inner`/`outer` points, offset by
    `CSG_TOLERANCE` off a candidate plane, are the actual live callers -- must still reach this
    branch.

    Read from AUTHORED volumes, never from `ctx.probe.solidity`, and the reason is measured rather
    than stylistic. The resolved oracle answers "is this space solid" for the whole world at once --
    every actor's contribution pooled, the world's own default solidity, and `bspcsg.rs`'s
    `first_add_seed` shell, which makes a leading Add's INTERIOR read void and everything outside it
    read solid. On `niche_carved_into_wall` (where `Wall` IS the leading Add) that oracle reports
    `Wall`'s interior as void and the space `Bystander` occupies as solid -- the exact inverse of the
    fact the relation is asking about (`test_resolved_matter_ignores_the_pooled_solidity_oracle`)."""
    if actor.brush is None:
        if actor.location is None:
            return False
        loc = tuple(float(c) for c in actor.location)
        return all(abs(point[i] - loc[i]) < CSG_TOLERANCE for i in range(3))
    kind = _kind(ctx, actor)
    if kind not in _MATTER_KINDS:
        return False
    if not _in_authored_volume(ctx, actor, point):
        return False
    if kind == "mover":
        return True                       # outside world CSG, so no Subtract can cut it
    after = ctx.csg_order[ctx.csg_index.get(actor.name, len(ctx.csg_order)) + 1:]
    return not any(ctx.kinds[a.name] == "subtract" and _in_authored_volume(ctx, a, point)
                   for a in after)


def touches_facts_for(ctx: SurveyContext) -> list[CsgFact]:
    """`touches [csg]`: the surveyed actor's authored geometry and a near brush's authored
    geometry share a site whose resolved matter is flush (spec's intent -- the mechanism is a
    matter-side probe, not polygon Area Contact; see `_touches_relation`'s own docstring for why).
    Symmetric, so ONE pass over the near set suffices (`pair_touches`'s own discipline, restored)
    -- the surveyed actor always leads, no depth annotated. Any brush kind on either side (spec:
    "Given Brush A (ANY) and Brush B (ANY)"); brush-vs-brush only, matching `crosses`/`carves`'s
    scope.

    Not de-duplicated against `crosses`/`carves` for the same pair: those are non-coplanar tests,
    this is coplanar, so a shared actor pair can genuinely clear both (flush on one face, crossing
    through another) -- two independent, both-true facts about different polygon pairs.

    The far side (`other`/`dst`) is gated by `crosses_target_eligible`, same as `crosses`: a
    point actor's collision cylinder is not world geometry and a Mover authors no world face, so
    neither can be NAMED as the far side of a `touches` line, even though both are legitimate
    sources (`props_flush_against_a_room_wall`'s own framing -- flagged there as a real
    asymmetry, not decided by this module)."""
    if ctx.surveyed.brush is None:
        return []
    facts = []
    for other in ctx.near:
        if other.brush is None or not crosses_target_eligible(other, ctx.class_index):
            continue
        if _touches_relation(ctx, ctx.surveyed, other):
            facts.append(CsgFact(src=ctx.name, dst=other.name, relation="touches"))
    return sorted(facts, key=lambda f: f.dst)


def connects_facts_for(ctx: SurveyContext) -> list[CsgFact]:
    """`connects [csg]`: the surveyed Subtract's void is continuous with another Subtract's void
    -- void on both sides of a shared site, nothing solid between (see `_connects_relation`'s own
    docstring). Symmetric, one pass, surveyed actor leads, both Subtractive."""
    if ctx.surveyed.brush is None or _kind(ctx, ctx.surveyed) != "subtract":
        return []
    actorgraph.decompose_convex(ctx.surveyed, cache=ctx.cells)   # propagates on a bad SURVEYED brush
    facts = []
    for other in ctx.near:
        if other.brush is None or _kind(ctx, other) != "subtract":
            continue
        try:
            if _connects_relation(ctx, ctx.surveyed, other):
                facts.append(CsgFact(src=ctx.name, dst=other.name, relation="connects"))
        except actorgraph.DegenerateBrushError:
            continue          # a bad neighbour is skipped, as it is in the raw tier
    return sorted(facts, key=lambda f: f.dst)


# The occupant kinds `occupies [csg]` allows on brush B's side (spec: ADDITIVE/SEMISOLID/
# NONSOLID/MOVER) -- a Subtract/Intersect/Deintersect contributes nothing a void could contain.
_OCCUPIES_OCCUPANT_KINDS = frozenset({"add", "semisolid", "nonsolid", "mover"})


def occupies_facts_for(ctx: SurveyContext) -> list[CsgFact]:
    """`occupies [csg]`: the occupant leads, whichever side is surveyed. Two directions, both
    computed -- the surveyed actor as OCCUPANT (against every Subtract in its neighborhood) and
    as SUBTRACT (against every occupant candidate in its neighborhood). NOT a competition:
    `occupies` fires independently per `(occupant, subtract)` pair -- an occupant seated across
    two Subtracts' voids reports `occupies` against both."""
    facts: list = []
    probe_cache: dict = {}

    def is_occupant(actor) -> bool:
        if actor.brush is None:
            return True
        return _kind(ctx, actor) in _OCCUPIES_OCCUPANT_KINDS

    if ctx.surveyed.brush is None or _kind(ctx, ctx.surveyed) != "subtract":
        if is_occupant(ctx.surveyed):
            subtracts = [a for a in ctx.near if a.brush is not None and _kind(ctx, a) == "subtract"]
            for s in subtracts:
                if s.name != ctx.name and _occupies_relation(ctx, s, ctx.surveyed, probe_cache=probe_cache):
                    facts.append(CsgFact(src=ctx.name, dst=s.name, relation="occupies"))
    if ctx.surveyed.brush is not None and _kind(ctx, ctx.surveyed) == "subtract":
        candidates = list(ctx.near) + list(ctx.points)
        for occupant in candidates:
            if (occupant.name != ctx.name and is_occupant(occupant)
                    and _occupies_relation(ctx, ctx.surveyed, occupant, probe_cache=probe_cache)):
                facts.append(CsgFact(src=occupant.name, dst=ctx.name, relation="occupies"))

    return sorted(facts, key=lambda f: (f.src, f.dst))


# A Subtract can only have removed matter from a kind that HAS matter to remove and is applied
# BEFORE it. Measured (spike.md §1, regression `test_csg_kind_facts.py`):
#   add       carved, with real area loss                                  -> valid target
#   nonsolid  contributes no solid, but its FACES are real world surfaces and a later Subtract
#             removes them with exactly the same area loss as an Add's     -> valid target
#   semisolid listed per spec, but structurally never actually fires: `_csg_order_position` orders
#             via `ctx.crossing_index`, which always places every semisolid after every world-pass
#             brush (LOOP 2 then LOOP 3) regardless of file position -- so "victim before subtract"
#             can never hold when victim is a semisolid. Kept in this set (not excluded) because
#             the order check already enforces the real constraint; excluding it here too would be
#             a second, redundant enforcement of the same fact by a different mechanism, exactly
#             the drift this spec's single ordering primitive is meant to prevent. Confirmed still
#             silent against `test_carves_never_targets_a_semisolid`.
#   subtract/intersect/deintersect/mover  contribute nothing a Subtract could take
_CARVE_TARGET_KINDS = frozenset({"add", "semisolid", "nonsolid"})


def poly_area(verts) -> float:
    """A planar polygon's area, `0.5 * |newell|` -- the same relation `query.py`'s own `poly list`
    area uses (`texframe.newell`'s docstring)."""
    n = newell([tuple(float(c) for c in v) for v in verts])
    return 0.5 * (n[0] ** 2 + n[1] ** 2 + n[2] ** 2) ** 0.5


def _carves_volume(ctx: SurveyContext, s, victim) -> float:
    """The EXACT volume of `victim INTERSECT s INTERSECT {victim's own matter, just before s}` --
    `carves`'s measurement basis (owner ruling), replacing the retired face-area `removed_by`. Same
    exact evaluator as `occupies`: partition the shared `victim INTERSECT s` region by the Subtracts
    strictly between `victim` and `s` in trunk order (the only brushes `_victim_matter_just_before`
    reads), then sum the pieces whose centroid still passes it.

    Ordered via `ctx.trunk_index`, not `ctx.csg_index` -- see `_victim_matter_just_before`'s
    docstring for why a Nonsolid victim needs the full trunk-order position."""
    v_i = ctx.trunk_index.get(victim.name, -1)
    s_i = ctx.trunk_index.get(s.name, len(ctx.trunk_index))
    between_subtracts = [a for a in ctx.csg_order
                          if ctx.kinds[a.name] == "subtract" and v_i < ctx.trunk_index.get(a.name, -1) < s_i]
    total = 0.0
    for v_cell in actorgraph.decompose_convex(victim, cache=ctx.cells):
        for s_cell in actorgraph.decompose_convex(s, cache=ctx.cells):
            overlap = _cell_intersection(v_cell, s_cell)
            if overlap is None:
                continue
            for piece in _partition_by_brushes(overlap, between_subtracts, ctx):
                if _victim_matter_just_before(ctx, victim, s, _piece_centroid(piece)):
                    total += cell_volume(piece)
    return total


def carves_facts_for(ctx: SurveyContext) -> list[CsgFact]:
    """`carves [csg]`: B (Subtractive) carves A when A is before B in CSG order and B's authored
    geometry non-coplanar-crosses A's geometry resolved up until right before B (spec) -- the same
    test `crosses [csg]` uses, named for the specific case of a later void-cutting brush. The
    Subtract (B) always leads, whichever side is surveyed, so both directions are computed.
    Movers excluded entirely -- never carved, never carve (absent from both kind sets)."""
    facts: list = []
    probe_cache: dict = {}

    def is_victim(actor):
        return actor.brush is not None and _kind(ctx, actor) in _CARVE_TARGET_KINDS

    def is_subtract(actor):
        return actor.brush is not None and _kind(ctx, actor) == "subtract"

    if is_subtract(ctx.surveyed):
        for other in ctx.near:
            if is_victim(other) and _carves_relation(ctx, other, ctx.surveyed,
                                                      probe_cache=probe_cache):
                facts.append(CsgFact(src=ctx.name, dst=other.name, relation="carves"))
    elif is_victim(ctx.surveyed):
        for other in ctx.near:
            if is_subtract(other) and _carves_relation(ctx, ctx.surveyed, other,
                                                        probe_cache=probe_cache):
                facts.append(CsgFact(src=other.name, dst=ctx.name, relation="carves"))

    return sorted(facts, key=lambda f: (f.src, f.dst))


@dataclass(frozen=True)
class SurveyResult:
    raw: list
    csg: list
    nodes: dict
    skipped: list
    warning: str | None


def csg_facts_for(ctx: SurveyContext) -> list:
    """Every csg-tier fact about the surveyed actor, in a fixed relation order so the output is
    stable between runs."""
    out: list = []
    for fn in (crosses_facts_for, touches_facts_for, connects_facts_for,
               occupies_facts_for, carves_facts_for):
        out.extend(fn(ctx))
    return out


def survey(level, class_index, name: str, defaults) -> SurveyResult:
    """Both tiers for one actor, over ONE shared decomposition cache and ONE native solve.

    Raises `ActorNotFoundError` (unknown name), `actorgraph.DegenerateBrushError` (the SURVEYED
    actor's own brush), `preview_native.NativePreviewError` (no native extension, or a failed
    solve), and `ActorHasNoLocationError` (the surveyed actor is non-brush with no `Location`). The
    CLI maps every one of them to exit 2 -- none may reach the user as a traceback."""
    if name not in level.actors:
        raise ActorNotFoundError(name)
    cells: dict = {}
    raw = raw_facts_for(level, class_index, name, defaults, cells=cells)
    ctx = build_context(level, class_index, name, defaults, cells=cells)
    csg = csg_facts_for(ctx)
    nodes = dict(raw.nodes)
    for fact in csg:
        for side in (fact.src, fact.dst):
            if side not in nodes and side in level.actors:
                nodes[side] = actorgraph._node_tag(level.actors[side], class_index)
    return SurveyResult(raw=raw.facts, csg=csg, nodes=nodes, skipped=raw.skipped,
                         warning=intersect_deintersect_warning(level.actors[name], class_index))


def format_csg_line(fact: CsgFact, nodes: dict) -> str:
    """One csg-tier line, its verb prefixed `csg:` -- `touches`/`crosses`/`encloses` are now shared
    names with the raw tier (spec, `dev/specs/commands/actor-survey.md`), so the prefix carries
    tier identity; the verb no longer can."""
    return (f"{fact.src} {actorgraph._node_bracket(nodes[fact.src])} --csg:{fact.relation}--> "
            f"{fact.dst} {actorgraph._node_bracket(nodes[fact.dst])}")


def intersect_deintersect_warning(actor, class_index) -> str | None:
    """One stderr line when the SURVEYED actor itself is a placed Intersect/Deintersect brush.

    No other actor's survey warns. Such a brush contributes nothing to the resolved world at all --
    `bspBrushCSG` dispatches it to a tail that rewrites the BRUSH's own model and never touches the
    world (measured: the world is node-identical with and without one, spike.md §2) -- so it cannot
    change anyone else's facts, and a neighborhood scan for one would be pure noise. The spec's
    earlier reason for the warning ("can affect resolution outside a single actor's immediate
    neighborhood") is false; the real reason is narrower and local: its own csg tier is correctly
    empty, and its raw tier treats it as Add-like, which the resolved world does not.

    A stderr warning beside a complete answer, which `CLAUDE.md`'s no-silent-half-answers rule
    would normally refuse -- allowed here because the answer is not partial, and recorded because
    the owner ruled 'warn on Intersect/Deintersect'."""
    if actor.brush is None:
        return None
    kind = kind_of(actor, class_index)
    if kind not in ("intersect", "deintersect"):
        return None
    oper = "CSG_Intersect" if kind == "intersect" else "CSG_Deintersect"
    return (f"actor survey: {actor.name} is a placed {oper} brush — it contributes nothing to the "
            f"resolved world (the editor treats it as a builder-brush operation on its own model), "
            f"so its csg tier carries no fact it sources, and its raw tier treats it as Add-like, "
            f"which the resolved world does not")


def format_lines(result: SurveyResult) -> list:
    """Every stdout line of a survey: the raw block, a blank separator when both tiers have
    something, then the csg block. No per-line tier prefix (relation names are unique across
    tiers, so each line self-identifies by its verb) and no other marker -- the two groups are
    "authored" and "resolved" by fixed order alone."""
    lines = [format_raw_line(f, result.nodes) for f in result.raw]
    csg_lines = [format_csg_line(f, result.nodes) for f in result.csg]
    if lines and csg_lines:
        lines.append("")
    return lines + csg_lines
