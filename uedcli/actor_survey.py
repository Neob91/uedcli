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

from . import actorgraph, movers, query, relation
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


class CollisionPropertyError(Exception):
    """A collision extent property (`CollisionRadius`/`CollisionHeight`) resolved to a value the
    engine could never use -- NaN, +/-Infinity, or negative -- once it was actually GIVEN (as
    opposed to absent, which `_to_decimal` already treats as 0). `Decimal("NaN")`/`Decimal("Infinity")`
    parse without error, so a bare numeric-format check let a malformed value either raise a bare
    `decimal.InvalidOperation` out of `aabb_intersects`' NaN comparisons, silently build an unbounded
    region (Infinity), or silently invert an AABB (a negative radius) -- three different wrong
    outcomes from one ungated value. Raised naming the actor, the property, and the offending value
    rather than guessing a substitute; the CLI maps it to exit 2 (Task 18), the same as
    `uprops.SchemaError`."""

    def __init__(self, actor_name: str, prop: str, value):
        super().__init__(f"actor {actor_name!r}: {prop}={value!r} is not a valid non-negative, "
                         f"finite number")
        self.actor_name = actor_name
        self.prop = prop
        self.value = value


def _to_decimal(text, default: Decimal = Decimal(0)) -> Decimal:
    """`text` as a Decimal, or `default` when it is absent or not a number -- the Decimal twin of
    the spike harness's `_to_float` (`collision_clearance.py:71`). It never raises on malformed
    TEXT: a garbled property value must not put a traceback in front of the user (`CLAUDE.md`).

    A value that PARSES but is NaN, +/-Infinity, or negative is a different failure -- those are
    not malformed text, and a collision extent can never legitimately be any of them -- so this
    function does not filter them; `_validated_extent` below does, naming the actor/property/value.
    Silently defaulting an out-of-domain number here (rather than in the caller that knows which
    property it was) would hide which property was malformed."""
    try:
        return Decimal(str(text).strip())
    except (TypeError, ValueError, ArithmeticError):
        return default


def _validated_extent(actor_name: str, prop: str, raw) -> Decimal:
    """`raw` as a non-negative, finite Decimal, or `CollisionPropertyError` naming `actor_name`/
    `prop`/the offending value.

    Shared by `_collision_half_extent` (region sizing) and `collision_extent` (Task 11's crossing
    gate) so a malformed `CollisionRadius`/`CollisionHeight` -- NaN, +/-Infinity, negative -- cannot
    resolve to two different answers depending on which caller asked: region sizing raising while
    the crossing gate silently read it as "does not collide", or vice versa. Same one-gate discipline
    `_blocks_movement` already applies to the collide/block boolean pair."""
    value = _to_decimal(raw)
    if not value.is_finite() or value < 0:
        raise CollisionPropertyError(actor_name, prop, raw)
    return value


def _blocks_movement(actor, defaults) -> bool:
    """Does `actor` carry a collision volume the engine treats as MATTER -- `bCollideActors` AND
    `bBlockActors` both `True`?

    Instance property else class default, the same resolution `serve/scene.py::_actor_radii` uses
    for these fields -- including its `field`/`field_or` split, whose `is not None` test keeps a
    present-but-EMPTY value from being read as "absent" and silently replaced by the class default.
    These boolean gates are what need it.

    `bCollideActors` alone is not a claim about matter: shipped triggers that block nothing
    routinely carry a `CollisionRadius` of 520-630 uu so they can span a room. Ungated, surveying
    one would build a region over 1000 uu across and solve whatever neighborhood that region selects
    -- a cost the spike never measured (its 140 surveys ran on 1-uu-padded regions). Across 1522
    collidable shipped actors, requiring `bBlockActors` too drops the worst by-design overlap from
    436 uu to 64 uu (spike.md §3).

    This is the ONLY place the gate is written. Its two callers answer in different shapes --
    `_collision_half_extent` below in Decimal half-extents for region sizing, `collision_extent`
    (Task 11) in floats-or-None for the crossing gate -- but they must agree on WHETHER an actor
    collides at all. A second copy of the gate would let an edit to one drift from the other
    silently.

    `uprops.SchemaError` from an unresolvable class propagates -- guessing "does not collide" would
    be a substituted default. The CLI maps it to exit 2 (Task 18)."""
    instance = {k.casefold(): v for k, v in actor.props}
    class_defaults = defaults.for_class(actor.cls).defaults

    def field_or(name: str, default: str) -> str:
        low = name.casefold()
        value = instance[low] if low in instance else class_defaults.get((low, 0))
        return value if value is not None else default

    return (str(field_or("bCollideActors", "False")).strip() == "True"
            and str(field_or("bBlockActors", "False")).strip() == "True")


def _collision_half_extent(actor, defaults) -> tuple[Decimal, Decimal, Decimal]:
    """`(CollisionRadius, CollisionRadius, CollisionHeight)` when `actor` has a real BLOCKING
    collision volume (`_blocks_movement`), else `(0, 0, 0)`.

    The engine's collision volume is a CYLINDER: a circle of radius `CollisionRadius` in the XY
    plane, extruded in Z to half-height `CollisionHeight`. The project owner confirmed this
    directly, from first-hand Unreal Engine 1 experience, and `collision_extent` (Task 11) carries
    the disassembly that backs it. An earlier draft of this plan called it an axis-aligned box,
    sourced from a comment in `uedcli-native/src/collision.rs` that was never checked against the
    game binaries — do not reintroduce that claim or that citation.

    This function still returns THREE half-extents because its one caller, `region_of`, wants a
    bounding box and nothing else. A cylinder of radius R and half-height H has exactly the same
    axis-aligned bounding box as a box of half-extents (R, R, H), so no change is needed here: the
    region only has to be a conservative envelope for selecting candidate brushes and faces, never
    the true collision shape. Where the true shape does matter — testing whether the actor's own
    volume overlaps solid — the sampling is cylindrical (`cylinder_sample_points`, Task 11).

    An actor with no blocking collision volume resolves to `(0, 0, 0)`, which makes `region_of` fall
    back to the zero-size box at `Location`.

    `uprops.SchemaError` from an unresolvable class propagates -- guessing zero would be a
    substituted default. The CLI maps it to exit 2 (Task 18)."""
    if not _blocks_movement(actor, defaults):
        return Decimal(0), Decimal(0), Decimal(0)
    instance = {k.casefold(): v for k, v in actor.props}
    class_defaults = defaults.for_class(actor.cls).defaults

    def field(name: str):
        low = name.casefold()
        return instance[low] if low in instance else class_defaults.get((low, 0))

    def extent(name: str) -> Decimal:
        return _validated_extent(actor.name, name, field(name))

    radius = extent("CollisionRadius")
    return radius, radius, extent("CollisionHeight")


def region_of(actor, defaults, pad: Decimal = NEIGHBORHOOD_PAD):
    """`actor`'s REAL world AABB grown by `pad`, in Decimals.

    A brush's real shape is its own transformed vertices, which is what `writes.actor_bounds`
    returns. A non-brush actor's real shape is its collision cylinder, whose bounding box is
    `Location +/- (R, R, H)` from `_collision_half_extent` -- so that is added on top of the
    zero-size box `actor_bounds` gives a point actor. `pad` is then the SAME uniform padding in both
    cases; there is no separate point-actor padding. Without this a flush-mounted prop's region
    would be 2 uu across whatever its collision cylinder measures, and the wall it is mounted
    against would fall outside it.

    Ported from the spike harness's `region_of`, which only ever ran on brushes. The Decimal is not
    incidental -- `writes.aabb_intersects` adds its own Decimal slack and raises TypeError against a
    float bound, which is also why `_collision_half_extent` returns Decimals rather than floats.

    Raises `ActorHasNoLocationError` for a non-brush actor with no `Location` -- a brush's position
    comes from its own vertices regardless of `Location`, but a non-brush actor's only position IS
    `Location`, and `actor_bounds` falling back to `(0,0,0)` there would fabricate a real position
    for an actor that has none, building a neighborhood around the world origin instead of
    surfacing the real problem (see the exception's own docstring)."""
    if actor.brush is None and actor.location is None:
        raise ActorHasNoLocationError(actor.name)
    lo, hi = actor_bounds(actor)
    if actor.brush is None:
        ext = _collision_half_extent(actor, defaults)
        lo = tuple(c - e for c, e in zip(lo, ext))
        hi = tuple(c + e for c, e in zip(hi, ext))
    return (tuple(c - pad for c in lo), tuple(c + pad for c in hi))


def _meets(actor, region, defaults) -> bool:
    """Does `actor`'s own (unpadded, `pad=0`) region overlap `region`? Shared by `neighborhood`,
    `near_brushes`, and `nearby_point_actors` so the near-test itself lives in one place -- matching
    the one-shared-helper discipline `_blocks_movement` already applies to the collision gate."""
    return aabb_intersects(region_of(actor, defaults, Decimal(0)), region)


def in_world_csg(actor, class_index) -> bool:
    """Does this actor contribute to the WORLD CSG solve? A Mover and the builder brush are both
    brushes and neither does -- the same filter `preview_native.solve_world_surfaces` applies."""
    return actor.brush is not None and not (movers.is_mover(actor, class_index)
                                            or is_builder_brush(actor))


def seed_brush_name(level, class_index) -> str | None:
    """The name of the level's FIRST world-CSG-contributing brush in trunk order, or None if it has
    none.

    NOT `level.order[0]` and NOT `neighborhood(...)[0]`: a Mover or the builder brush can sit ahead
    of it and neither contributes, so the brush `bsp_brush_csg` actually seeds the world shell from
    (`uedcli-native/src/bspcsg.rs`'s `first_add_seed`) is often at a later index. Anything that must
    reason about "the first brush" -- `neighborhood`'s never-truncate clause, `removed_by`'s
    never-drop guard -- has to mean THIS one, so it is named once here rather than re-derived from
    an index at each site."""
    return next((n for n in level.order if in_world_csg(level.actors[n], class_index)), None)


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
    to `classify_pair` or named in any fact. Same filter the spike harness applies before its own
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
    """One raw-tier line's worth of information, already in `actor survey`'s OWN presentation form.
    A separate type from `actorgraph.Edge` for one reason: `level graph` spells the third relation
    `carved_by` with the ADD leading, and this verb spells it `carves` with the SUBTRACT leading
    (spec, Round 6). Keeping the rename in the type conversion rather than in the formatter means
    nothing downstream can accidentally print the other spelling."""
    src: str
    dst: str
    relation: str
    matched_pair: tuple[int, int] | None
    area_estimate: float | None


@dataclass(frozen=True)
class RawFacts:
    facts: list
    nodes: dict
    skipped: list


def _flip(fact: RawFact) -> RawFact:
    """Swap a symmetric fact's two sides, carrying `matched_pair` with them. The pair is glued to
    `(src, dst)` POSITIONALLY, so a rename-only flip would render a real face selector against the
    wrong brush (spec, Output shape)."""
    pair = None if fact.matched_pair is None else (fact.matched_pair[1], fact.matched_pair[0])
    return RawFact(src=fact.dst, dst=fact.src, relation=fact.relation,
                   matched_pair=pair, area_estimate=fact.area_estimate)


def _from_edge(edge, surveyed: str) -> RawFact:
    """One `actorgraph.Edge` in this verb's own presentation form.

    The `_flip` branch below is what GUARANTEES a symmetric fact leads with the surveyed actor. It
    happens not to fire through `raw_facts_for`, which always passes the surveyed actor as
    `classify_pair`'s `name_a` -- but that is an invariant of the CALL ORDER, not of this function,
    so the branch stays and is pinned directly by
    `test_from_edge_flips_a_symmetric_fact_when_the_surveyed_actor_is_the_edges_dst`."""
    if edge.relation == "carved_by":
        # level graph: Edge(src=Add, dst=Subtract, relation="carved_by") -- the victim leads.
        # actor survey: the agent leads, and the word is `carves`.
        return RawFact(src=edge.dst, dst=edge.src, relation="carves",
                       matched_pair=None, area_estimate=None)
    fact = RawFact(src=edge.src, dst=edge.dst, relation=edge.relation,
                   matched_pair=edge.matched_pair, area_estimate=edge.area_estimate)
    if edge.relation == "touches" and fact.dst == surveyed:
        return _flip(fact)                       # symmetric: the surveyed actor leads
    return fact


def raw_facts_for(level, class_index, name: str, defaults, *,
                  cells: dict | None = None) -> RawFacts:
    """Every raw-tier fact about `name`, computed over the BOUNDED NEIGHBORHOOD.

    Deliberately not `actorgraph`'s whole-level graph builder: that walks every brush pair in the
    level, is `O(brushes^2)`, and the spike measured it at 12x a full CSG solve on a 208-brush level
    and unfinishable above that (spike.md §4). This runs the SAME `classify_pair` over
    `near_brushes(...)` instead -- a median 31 ms per survey in the same measurement.

    Raises `ActorNotFoundError` for an unknown name, and `actorgraph.DegenerateBrushError` when the
    SURVEYED actor's own brush cannot be decomposed -- unlike `level graph`, which skips a bad brush
    and carries on over the rest of the level, a single-actor report has nothing left to say. A
    degenerate NEIGHBOUR is skipped and recorded in `skipped`, exactly as the whole-level builder's
    own per-brush skip does.
    """
    if name not in level.actors:
        raise ActorNotFoundError(name)
    cells = {} if cells is None else cells
    surveyed = level.actors[name]
    order_index = {n: i for i, n in enumerate(level.order)
                   if level.actors[n].brush is not None}
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
            for edge in actorgraph.classify_pair(name, surveyed, other.name, other,
                                                  order_index=order_index,
                                                  class_index=class_index, cache=cells):
                facts.append(_from_edge(edge, name))
                nodes[other.name] = actorgraph._node_tag(other, class_index)
        # The same point-actor containment fan-out the whole-level graph builder does, scoped to the
        # surveyed brush: every point actor whose Location falls inside its volume.
        for p in points:
            loc = tuple(float(c) for c in p.location)
            if actorgraph.point_in_brush(surveyed, loc, cache=cells):
                facts.append(RawFact(src=name, dst=p.name, relation="contains",
                                      matched_pair=None, area_estimate=None))
                nodes[p.name] = actorgraph._node_tag(p, class_index)
    else:
        # The surveyed actor IS a point: the same fan-out seen from the other side. `contains` is
        # fixed-direction, so the containing brush still leads.
        if surveyed.location is not None:
            loc = tuple(float(c) for c in surveyed.location)
            for other in others:
                try:
                    if not actorgraph.point_in_brush(other, loc, cache=cells):
                        continue
                except actorgraph.DegenerateBrushError as e:
                    skipped[other.name] = str(e)
                    continue
                facts.append(RawFact(src=other.name, dst=name, relation="contains",
                                      matched_pair=None, area_estimate=None))
                nodes[other.name] = actorgraph._node_tag(other, class_index)

    return RawFacts(facts=facts, nodes=nodes, skipped=sorted(skipped.items()))


def format_raw_line(fact: RawFact, nodes: dict) -> str:
    """One `raw `-prefixed line, in `actorgraph.format_text`'s exact grammar. `:idx` and the area
    annotation ride ONLY a `touches` fact that found a real matched face pair; `contains`/`carves`
    print bare names with no annotation (spec, Output shape)."""
    has_idx = fact.relation == "touches" and fact.matched_pair is not None
    src = f"{fact.src}:{fact.matched_pair[0]}" if has_idx else fact.src
    dst = f"{fact.dst}:{fact.matched_pair[1]}" if has_idx else fact.dst
    rel = fact.relation
    if fact.relation == "touches" and fact.area_estimate is not None:
        rel = f"touches({fact.area_estimate:.4g}uu^2)"
    return (f"raw {src} {actorgraph._node_bracket(nodes[fact.src])} --{rel}--> "
            f"{dst} {actorgraph._node_bracket(nodes[fact.dst])}")


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


def _cell_intersection_volume(cell_a, cell_b) -> float:
    """The volume of the convex intersection `cell_a INTERSECT cell_b`, both `actorgraph.ConvexCell`s.

    Same H-rep -> V-rep -> tetrahedral-volume pipeline `decompose_convex`/`cell_volume` already use
    (every vertex of the intersection is where 3 of the combined half-spaces meet, kept only when it
    also satisfies every other one) -- but with one addition `actorgraph._cell_vertices` does NOT
    have: a bounds sanity check on each candidate vertex BEFORE the half-space check runs. Board item
    `authored-volume-poisoned-by-unbounded-plane` records why that matters: two
    near-parallel planes intersect at a point whose distance from either plane blows up as they
    approach parallel, and nothing in `_cell_vertices` catches a resulting vertex that lands light-
    years from either actor's own geometry -- silently inflating a reported volume by many orders of
    magnitude. `actorgraph.py` is foundational, shipped, widely-used code and is deliberately NOT
    touched here; this is a fresh, LOCAL vertex search (reusing only the pure linear-algebra solver
    `actorgraph._intersect_three_planes`, never the unguarded `_cell_vertices` loop), so the guard
    lives where the new call site is.

    The guard itself is not a new invented tolerance: any real point of `cell_a INTERSECT cell_b`
    lies inside BOTH cells' own bounding boxes, by definition of intersection -- so a candidate
    outside their combined box (padded by the module's own `CSG_TOLERANCE`, not a new constant) is
    provably not a real vertex of this intersection and is dropped before it can reach anything.

    Returns `0.0` for cells whose bounding boxes don't meet at all (the common case -- most cell
    pairs in a survey don't overlap) and for a genuinely empty or degenerate intersection (fewer than
    4 surviving vertices) -- both ordinary outcomes here, not errors."""
    a_lo, a_hi = _cell_bounds(cell_a)
    b_lo, b_hi = _cell_bounds(cell_b)
    lo = tuple(max(a_lo[i], b_lo[i]) - CSG_TOLERANCE for i in range(3))
    hi = tuple(min(a_hi[i], b_hi[i]) + CSG_TOLERANCE for i in range(3))
    if any(lo[i] > hi[i] for i in range(3)):
        return 0.0
    planes = list(cell_a.half_spaces) + list(cell_b.half_spaces)
    eps = actorgraph._VERTEX_EPS
    verts: list = []
    for i, j, k in itertools.combinations(range(len(planes)), 3):
        p = actorgraph._intersect_three_planes(planes[i], planes[j], planes[k])
        if p is None:
            continue
        if any(p[m] < lo[m] or p[m] > hi[m] for m in range(3)):
            continue        # cannot be a real vertex of cell_a INTERSECT cell_b -- see docstring
        if not all(n[0] * p[0] + n[1] * p[1] + n[2] * p[2] <= d + eps for n, d in planes):
            continue
        if not any(math.dist(p, q) < eps for q in verts):
            verts.append(p)
    if len(verts) < 4:
        return 0.0
    return cell_volume(actorgraph.ConvexCell(vertices=verts, half_spaces=planes))


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
    partially pokes out of a Subtract gets no csg `contains`, even though raw `contains` reports one,
    and majority-of-extent was considered and rejected as its own source of ambiguity -- this upgrade
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
    (hundreds) that the exact test costs nothing."""
    lo, hi = (tuple(float(c) for c in region[0]), tuple(float(c) for c in region[1]))
    by_owner: dict = {}
    for surf in probe.world_surfaces:
        if surf.actor is None:
            continue
        if not _ring_meets_region(surf.world_verts, lo, hi):
            continue
        plane = _canonical_plane(surf.world_verts)
        if plane is None:
            continue
        normal, offset = plane
        seen = by_owner.setdefault(surf.actor.name, [])
        if any(abs(sum(normal[i] * f.normal[i] for i in range(3)) - 1.0) <= 1e-6
               and abs(offset - f.offset) <= CSG_TOLERANCE for f in seen):
            continue
        seen.append(CsgFace(owner=surf.actor.name, normal=normal, offset=offset,
                             verts=[tuple(float(c) for c in v) for v in surf.world_verts]))
    return [f for faces in by_owner.values() for f in faces]


@dataclass(frozen=True)
class CsgFact:
    """One csg-tier line. `depth_uu` is set on `crosses` and on nothing else -- the spec gives that
    one relation an annotation and leaves every other csg line bare."""
    src: str
    dst: str
    relation: str
    depth_uu: float | None = None


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

    `seed` is the NAME of the level's first world-CSG brush -- the one `bsp_brush_csg` turns into
    the world shell instead of classifying. It is carried explicitly rather than read back as
    `neighbors[0].name`, because `neighbors` is in trunk order and index 0 can perfectly well be a
    Mover or the builder brush, neither of which contributes to world CSG. Anything that must not
    disturb the seed (`removed_by`) compares against this.

    `aabbs` is `_brush_bounds`' memo: one float AABB per decomposed brush, the prefilter in front of
    every `point_in_brush` the contact search makes. `kinds` memoizes `kind_of` the same way --
    `movers.is_mover` walks the class ancestry on every call, and the contact search asks for a
    brush's kind thousands of times per survey (measured at 22% of the tier's whole runtime).
    `planes` is `_own_planes`' memo, for the same reason."""
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
    seed: str | None
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
        seed=seed_brush_name(level, class_index),
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
    """Can this actor's own matter be the INTRUDER on a `crosses` line? A non-brush actor qualifies
    only when it has a real blocking collision cylinder (see `collision_extent`)."""
    if actor.brush is None:
        return collision_extent(actor, defaults) is not None
    return kind_of(actor, class_index) in _CROSSES_SOURCE_KINDS


def crosses_target_eligible(actor, class_index) -> bool:
    """Can this actor be the `dst` of a `crosses`/`touches` line -- i.e. does it author a resolved
    face something can be flush against or penetrate? A non-brush actor never does: its collision
    cylinder is not world geometry."""
    if actor.brush is None:
        return False
    return kind_of(actor, class_index) in _CROSSES_TARGET_KINDS


def collision_extent(actor, defaults) -> tuple[float, float] | None:
    """`(radius, height)` when `actor` has a real BLOCKING collision volume, else None.

    The engine collides a CYLINDER: radius `CollisionRadius` in the XY plane, half-height
    `CollisionHeight` in Z. The project owner confirmed this directly, from first-hand Unreal
    Engine 1 experience. An earlier draft called it an axis-aligned box on the strength of a comment
    in `uedcli-native/src/collision.rs` that was never checked against the game binaries -- do not
    reintroduce that claim or that citation.

    Confirmed since, statically, against this repo's own `uned/UED22/Engine.dll` (ImageBase
    0x10000000). `AActor::SetCollisionSize` (RVA 0x12e8b0) stores its two float args to [this+0x190]
    and [this+0x194], pinning CollisionRadius/CollisionHeight; `ULevel::FarMoveActor` (RVA 0x15ff80)
    writes Location.X/Y/Z to [actor+0xd0/0xd4/0xd8]. `UPrimitive::PointCheck` (RVA 0x1935d0, reached
    from `FCollisionHash::ActorPointCheck` at 0x125380 through vtable slot [eax+0x54]) then tests,
    at VA 0x10193611-0x10193682:

        (Extent.Z + CollisionHeight)^2 > dz^2                      -- Z alone
        (Extent.X + CollisionRadius)^2 > dx*dx + dy*dy             -- XY as ONE circular sum

    `AActor::IsOverlapping` (RVA 0x12d3d0) has the same shape for actor-vs-actor at 0x1012d457. Two
    details recorded because they are not guessable: the comparisons are STRICT (`jbe` -> miss, so
    exact contact is a miss), and `Extent.Y` is never read at all -- a query box is collapsed to a
    cylinder using its X half-extent as the radius. The broad phase (`FCollisionHash`) is an AABB
    grid, which is what a reader skimming the collision code can mistake for a box collision test.
    This covers actor-primitive collision only; `UModel`/`UMesh` line and point checks were not
    examined. RVA 0x1aeba0, the address `collision.rs` cites, is genuinely `UModel::PointCheck` --
    BSP world geometry, not actor collision, so it was never evidence for this question either way.

    The gate is `_blocks_movement` (Task 7) -- the SAME function `_collision_half_extent` calls, not
    a second copy of it, so region sizing and the crossing gate cannot drift apart. It is TIGHTER
    than `_actor_radii`'s, and deliberately so: that function gates on `bCollideActors` alone, which
    is right for a GUI overlay but admits room-spanning trigger volumes. `_blocks_movement` also
    requires `bBlockActors` -- the engine's own name for "this actor's extent occupies space others
    cannot" -- which spike.md §3 measured as the gate that removes the entire deep tail (max
    penetration 436 uu -> 64 uu, p90 52 uu -> 12.7 uu across 1522 shipped actors). It carries the
    `is not None` split that keeps a present-but-EMPTY property from reading as absent.

    A zero radius or height is not a volume -- `_blocks_movement` answers "claims to block", this
    adds "and has a size" -- so those return `None` rather than `(0.0, ...)`. NaN, +/-Infinity, and
    negative are a different failure and never reach that check: `_validated_extent` (shared with
    `_collision_half_extent`, so the two functions cannot disagree about whether a value is usable)
    raises `CollisionPropertyError` on them first.

    Radius and height resolve instance-property-else-class-default, exactly as
    `serve/scene.py::_actor_radii` does it.

    `uprops.SchemaError` from an unresolvable class propagates: the gate cannot be answered, and
    guessing "does not collide" would be a substituted default. The CLI maps it to exit 2."""
    if not _blocks_movement(actor, defaults):
        return None
    instance = {k.casefold(): v for k, v in actor.props}
    class_defaults = defaults.for_class(actor.cls).defaults

    def field(name: str):
        low = name.casefold()
        return instance[low] if low in instance else class_defaults.get((low, 0))

    radius = _validated_extent(actor.name, "CollisionRadius", field("CollisionRadius"))
    height = _validated_extent(actor.name, "CollisionHeight", field("CollisionHeight"))
    if radius == 0 or height == 0:
        return None
    return float(radius), float(height)


# How many evenly spaced angles the collision cylinder's curved surface is sampled at, per Z level.
RING_SAMPLES = 8


def cylinder_sample_points(loc, radius: float, height: float) -> list:
    """The 27 sample points of the collision cylinder centred at `loc`: at each of three Z levels
    (`-height`, `0`, `+height`), the point on the axis plus `RING_SAMPLES` points evenly spaced
    around the circle of radius `radius`, the first at +X and each 45 degrees on from the last.

    This REPLACES the spike harness's `_sample_points` (`collision_clearance.py:40-47`), which laid
    a 3x3x3 grid over an axis-aligned box -- a shape the engine does not collide with (see
    `collision_extent`). The difference is not cosmetic: a box corner stands `radius * sqrt(2)` from
    the axis, 41% further out than any part of the real cylinder, so box sampling reports the actor
    inside a diagonal wall it never touches.

    8 ring points and 3 Z levels are chosen to MATCH the box version's granularity, not to improve
    on it. The box put 9 points on each of 3 Z levels (4 corners, 4 edge midpoints, 1 centre); this
    puts 9 on each of the same 3 levels (8 ring points, 1 axis point). The total stays 27, so the
    cost of the `any_point_solid` call below is unchanged. The 45-degree step also lands a sample
    exactly on the cylinder's extreme point for any face whose normal is axis-aligned or a 45-degree
    XY diagonal -- every face in this plan's fixtures, and the great majority in shipped levels.

    Two limits, stated rather than smoothed away. The first is inherited from the box version: 27
    points can miss a solid slab thinner than the sample spacing. The second is the ring's own
    price: against a face whose XY normal falls BETWEEN two ring angles, the deepest sample sits
    short of the cylinder's true extreme point by up to `radius * (1 - cos(pi / RING_SAMPLES))` =
    `0.0761 * radius` -- 1.2 uu at the 16-uu radius the fixtures use -- so a depth can under-report
    by that much. Under-reporting is the safe direction: the box's `sqrt(2)` corner OVER-reported,
    inventing penetration, which is what made it wrong rather than merely coarse."""
    out = []
    for iz in (-1, 0, 1):
        z = loc[2] + iz * height
        out.append((loc[0], loc[1], z))
        for k in range(RING_SAMPLES):
            angle = 2.0 * math.pi * k / RING_SAMPLES
            out.append((loc[0] + radius * math.cos(angle),
                        loc[1] + radius * math.sin(angle), z))
    return out


def extent_reaches_solid(ctx: SurveyContext, loc, radius: float, height: float) -> bool:
    """Does the collision cylinder at `loc` reach into RESOLVED SOLID matter? The spike's own
    `_box_free` test (`collision_clearance.py:50`) at delta = 0, negated, with its box sample
    swapped for `cylinder_sample_points`, run through the native query in one call.

    This is the crossing GATE only. The spike's `signed_clearance` bisection around it is
    deliberately NOT ported: its only extra output was an isotropic magnitude, and that magnitude
    saturates at the shrink floor for a 'buried' actor -- which is exactly why the harness's own
    `_stats` (line 194) excludes buried actors from every percentile. The spec measures a `crosses`
    depth against the crossed face's own plane instead (Task 12), where there is nothing to
    saturate."""
    if ctx.probe.solidity is None:
        return False                      # an empty world has no solid to reach
    return ctx.probe.solidity.any_point_solid(cylinder_sample_points(loc, radius, height))


def _source_cells(ctx: SurveyContext, actor) -> list[list[tuple[float, float, float]]] | None:
    """The world-space points that stand for `actor`'s own contributed matter, grouped by convex
    PIECE, or None when it has none. A BRUSH (Mover included -- its private model is treated exactly
    like an Add's, owner ruling Round 8) contributes one group per `decompose_convex` cell, kept
    SEPARATE rather than flattened together; a NON-BRUSH actor contributes one group, the 27 sample
    points of its collision cylinder.

    The grouping is load-bearing for `penetration_depth`, not cosmetic: an L- or U-shaped brush
    decomposes into more than one cell precisely because its overall vertex set is NOT convex --
    taking the hull of every cell's vertices TOGETHER fills in the notch, so a face lying in that
    notch would wrongly register overlap against matter the brush never actually has there. Each
    cell's own hull, tested independently, cannot make this mistake: a `ConvexCell` IS convex, so its
    own hull is its own true silhouette. No current fixture exercises a non-convex brush (every
    scenario brush here is a box, one cell), but `crosses` must stay correct for one regardless.

    An actor with no `Location` contributes nothing rather than being placed at the origin: a
    substituted position would invent a fact (this is the same rule `collision_clearance.py`'s own
    candidate walk applies, skipping any actor whose `location is None`)."""
    if actor.brush is not None:
        cells = actorgraph.decompose_convex(actor, cache=ctx.cells)
        return [[tuple(float(c) for c in v) for v in cell.vertices] for cell in cells]
    ext = collision_extent(actor, ctx.defaults)
    if ext is None or actor.location is None:
        return None
    radius, height = ext
    loc = tuple(float(c) for c in actor.location)
    return [cylinder_sample_points(loc, radius, height)]


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

    Per-point testing is retained ONLY for the actual depth NUMBER, once overlap and straddle are
    established: the reported depth is `max(past)` over the qualifying cell's own points (the
    existing "signed distance past the plane on the solid side" computation, unchanged). This is
    exact for every source kind this module ships (a brush's own convex cell, or the collision
    cylinder), because both are geometrically convex and every one of this project's face normals and
    source shapes is axis-aligned: the farthest-reaching cross-section of an axis-aligned convex
    source, measured along an axis-aligned face normal, spans that source's ENTIRE silhouette (not
    just one corner) -- so whenever the silhouette meets the face's footprint at all, the true deepest
    point is reachable somewhere inside that meet, and `max(past)` over the cell's point set never
    overstates it. A source or a face at an arbitrary (non-axis-aligned) angle could in principle have
    its single deepest point fall outside the actual overlap region, over-reporting the depth; nothing
    in this plan's fixtures exercises that, and it is not solved here -- if a rotated case turns up,
    report it rather than reaching for a nearest-owner-style narrowing on your own.

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
    ring_uv = relation._ensure_ccw(relation.project_to_plane(face.verts, face.normal,
                                                             origin=face.verts[0]))
    best = None
    for points in cells:
        footprint_uv = _convex_hull_2d(relation.project_to_plane(points, face.normal,
                                                                 origin=face.verts[0]))
        if len(footprint_uv) < 3:
            continue
        overlap = relation._clip_2d(footprint_uv, ring_uv)
        if len(overlap) < 3 or relation._shoelace_area(overlap) == 0.0:
            continue           # this cell's own silhouette never meets this face's footprint
        past = [sign * (sum(face.normal[i] * p[i] for i in range(3)) - face.offset) for p in points]
        cell_max = max(past)
        if cell_max <= CSG_TOLERANCE or min(past) >= 0.0:
            continue           # doesn't reach solid, or never has matter on the void side either
        best = cell_max if best is None else max(best, cell_max)
    return best


def crosses_facts_for(ctx: SurveyContext) -> list[CsgFact]:
    """`crosses`: a solid actor's own matter extends past a resolved surviving face belonging to
    another actor, into space it does not itself claim.

    Fixed-direction -- the intruder always leads -- so this computes BOTH directions:

    * the surveyed actor as the INTRUDER, when it is source-eligible: test its own matter against
      every eligible face in the neighborhood.
    * the surveyed actor as the TARGET, always: scan the neighborhood for source-eligible actors
      whose matter lands past one of the SURVEYED actor's own faces. A source-ineligible surveyed
      actor (a Subtract, say) has no outgoing `crosses` at all, but can perfectly well be the `dst`
      of someone else's -- the spec's own worked example is exactly that shape.

    At most one fact per (src, dst): a wall is many fragments and several planes, and one
    relationship is one line."""
    facts: dict = {}
    if ctx.probe.solidity is None:
        return []

    def record(src, dst, depth):
        key = (src, dst)
        prev = facts.get(key)
        if prev is None or depth > prev.depth_uu:
            facts[key] = CsgFact(src=src, dst=dst, relation="crosses", depth_uu=depth)

    # Direction 1: the surveyed actor intrudes.
    if crosses_source_eligible(ctx.surveyed, ctx.class_index, ctx.defaults):
        cells = _source_cells(ctx, ctx.surveyed)
        if cells:
            for face in ctx.faces:
                if face.owner == ctx.name:
                    continue
                target = ctx.level.actors.get(face.owner)
                if target is None or not crosses_target_eligible(target, ctx.class_index):
                    continue
                depth = penetration_depth(ctx, cells, face)
                if depth is not None:
                    record(ctx.name, face.owner, depth)

    # Direction 2: somebody else intrudes on the surveyed actor.
    if crosses_target_eligible(ctx.surveyed, ctx.class_index):
        own_faces = [f for f in ctx.faces if f.owner == ctx.name]
        if own_faces:
            for other in ctx.near:
                if not crosses_source_eligible(other, ctx.class_index, ctx.defaults):
                    continue
                cells = _source_cells(ctx, other)
                if not cells:
                    continue
                for face in own_faces:
                    depth = penetration_depth(ctx, cells, face)
                    if depth is not None:
                        record(other.name, ctx.name, depth)
            # Point actors too. This is why `nearby_point_actors` (Task 7) filters candidates by
            # their own extent-aware region: a collision cylinder can reach into the surveyed
            # brush from a `Location` outside it, and a bare-`Location` filter drops those --
            # making the fact visible from one side of the pair and not the other.
            for p in ctx.points:
                if not crosses_source_eligible(p, ctx.class_index, ctx.defaults):
                    continue
                cells = _source_cells(ctx, p)
                if not cells:
                    continue
                for face in own_faces:
                    depth = penetration_depth(ctx, cells, face)
                    if depth is not None:
                        record(p.name, ctx.name, depth)

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
    own authored body IS its matter. A non-brush actor's matter is its blocking collision cylinder --
    radius in XY as one circular sum, half-height in Z, the shape `collision_extent`'s disassembly
    pins -- and the comparison is STRICT there for the same reason `UPrimitive::PointCheck` is
    (exact contact is a miss).

    Read from AUTHORED volumes, never from `ctx.probe.solidity`, and the reason is measured rather
    than stylistic. The resolved oracle answers "is this space solid" for the whole world at once --
    every actor's contribution pooled, the world's own default solidity, and `bspcsg.rs`'s
    `first_add_seed` shell, which makes a leading Add's INTERIOR read void and everything outside it
    read solid. On `niche_carved_into_wall` (where `Wall` IS the leading Add) that oracle reports
    `Wall`'s interior as void and the space `Bystander` occupies as solid -- the exact inverse of the
    fact the relation is asking about (`test_resolved_matter_ignores_the_pooled_solidity_oracle`)."""
    if actor.brush is None:
        ext = collision_extent(actor, ctx.defaults)
        if ext is None or actor.location is None:
            return False
        radius, height = ext
        loc = tuple(float(c) for c in actor.location)
        return ((point[0] - loc[0]) ** 2 + (point[1] - loc[1]) ** 2 < radius ** 2
                and abs(point[2] - loc[2]) < height)
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


def _plane_frame(normal, offset: float) -> tuple:
    """`(origin, u_axis, v_axis)` for the plane `normal . p == offset`.

    The origin is the foot of the world origin on the plane, so the frame is a function of the plane
    ALONE. Every slice of every actor against this plane therefore lands in one comparable 2-D frame
    -- the trap `relation.project_to_plane`'s own docstring records, where two independently
    defaulted origins put two footprints in unrelated frames. The origin also only ever moves along
    `normal`, which is perpendicular to both axes, so shifting it (see `_cell_slice`) leaves every
    `(u, v)` coordinate unchanged."""
    u_axis, v_axis = relation._plane_basis(relation._norm(normal))
    return tuple(normal[i] * offset for i in range(3)), u_axis, v_axis


def _clip_half_plane(poly: list, a: float, b: float, c: float) -> list:
    """`poly` clipped to the half-plane `a*u + b*v <= c` -- Sutherland-Hodgman against one edge, the
    2-D twin of `actorgraph._clip_polygon`'s single half-space step. Exact: every decision is the
    sign of a linear form, with no tolerance."""
    out: list = []
    for i in range(len(poly)):
        cur, prev = poly[i], poly[i - 1]
        cur_d = a * cur[0] + b * cur[1] - c
        prev_d = a * prev[0] + b * prev[1] - c
        if (cur_d <= 0.0) != (prev_d <= 0.0):
            t = prev_d / (prev_d - cur_d)
            out.append((prev[0] + t * (cur[0] - prev[0]), prev[1] + t * (cur[1] - prev[1])))
        if cur_d <= 0.0:
            out.append(cur)
    return out


def _cell_slice(cell, normal, offset: float, u_axis, v_axis) -> list | None:
    """The 2-D region of the plane `(normal, offset)` one convex cell covers, or None when the cell
    does not reach within `CSG_TOLERANCE` of that plane.

    This is the locality bound, and it is what every earlier round was missing. A contact is between
    two actors that are BOTH at the plane, over a region with real area -- not between one actor's
    shadow and a plane it is nowhere near. Round 5 bounded the source by its SILHOUETTE, a projection
    that carries no distance at all, which is why an Add reported `touches` against the Subtract
    enclosing it with 960 uu of clearance.

    The cell's signed span along `normal` decides both questions at once. When the plane cuts the
    cell (`lo <= 0 <= hi`) the region is the cell's exact cross-section there. When it does not, the
    cell's own nearest extreme is `lo` or `hi`; the plane must be within `CSG_TOLERANCE` of that --
    this single comparison IS the relation's contact tolerance, the only thing deciding a gap or an
    overlap of `g` uu -- and the region is the cross-section at that extreme, i.e. the cell's own
    face resting against the plane. Shifting the evaluation plane moves the frame origin along
    `normal` only, so the `(u, v)` coordinates stay in the shared frame (`_plane_frame`).

    A half-space parallel to the plane constrains nothing in 2-D: it is a scalar feasibility test,
    already answered by the span, so it is skipped. `1e-9` is that test's numerical zero, the same
    bare float-dust threshold `_canonical_plane` uses to decide whether a normal component is zero.

    The seed rectangle is the cell's own projected bounding box grown by 1 uu, which strictly
    contains every cross-section of that cell; the clip then carves the true region out of it. That
    1 uu is a bounding box, not a tolerance -- any larger value gives the identical answer."""
    nx, ny, nz = normal
    heights = [nx * v[0] + ny * v[1] + nz * v[2] - offset for v in cell.vertices]
    lo, hi = min(heights), max(heights)
    delta = 0.0 if lo <= 0.0 <= hi else (lo if lo > 0.0 else hi)
    if abs(delta) > CSG_TOLERANCE:
        return None
    ox, oy, oz = (nx * (offset + delta), ny * (offset + delta), nz * (offset + delta))
    ux, uy, uz = u_axis
    vx, vy, vz = v_axis
    uv = [((v[0] - ox) * ux + (v[1] - oy) * uy + (v[2] - oz) * uz,
           (v[0] - ox) * vx + (v[1] - oy) * vy + (v[2] - oz) * vz) for v in cell.vertices]
    lo_u, hi_u = min(p[0] for p in uv), max(p[0] for p in uv)
    lo_v, hi_v = min(p[1] for p in uv), max(p[1] for p in uv)
    poly = [(lo_u - 1.0, lo_v - 1.0), (hi_u + 1.0, lo_v - 1.0),
            (hi_u + 1.0, hi_v + 1.0), (lo_u - 1.0, hi_v + 1.0)]
    for (hx, hy, hz), d_i in cell.half_spaces:
        a = hx * ux + hy * uy + hz * uz
        b = hx * vx + hy * vy + hz * vz
        if abs(a) <= 1e-9 and abs(b) <= 1e-9:
            continue
        poly = _clip_half_plane(poly, a, b, d_i - (hx * ox + hy * oy + hz * oz))
        if len(poly) < 3:
            return None
    return poly


def plane_slices(ctx: SurveyContext, actor, normal, offset: float) -> list:
    """Every 2-D region of the plane `(normal, offset)` that `actor`'s own volume reaches, one per
    convex piece -- empty when it reaches none.

    Pieces are kept SEPARATE for the reason `_source_cells` already records: the hull of an L- or
    U-shaped brush's cells pooled together fills in the notch, inventing coverage the brush does not
    have there.

    A NON-BRUSH actor has no cells, so its region is the projected hull of its collision cylinder's
    sample points -- a silhouette, wider than the cylinder's true cross-section at a tangent plane,
    where that cross-section degenerates to a line and would report no contact at all. The distance
    the silhouette drops is not lost: a non-brush actor is only ever a contact's MATTER side, and
    `_matter_side` probes the cylinder itself at `CSG_TOLERANCE` off the plane, which is the same
    question `_cell_slice`'s span test answers for a brush."""
    u_axis, v_axis = relation._plane_basis(relation._norm(normal))
    if actor.brush is None:
        groups = _source_cells(ctx, actor)
        if not groups:
            return []
        origin = tuple(normal[i] * offset for i in range(3))
        out = []
        for points in groups:
            hull = _convex_hull_2d(relation.project_to_plane(points, normal, origin=origin))
            if len(hull) >= 3:
                out.append(hull)
        return out
    return [region for region in
            (_cell_slice(cell, normal, offset, u_axis, v_axis)
             for cell in actorgraph.decompose_convex(actor, cache=ctx.cells))
            if region is not None]


def _same_plane(normal, offset: float, other) -> bool:
    """Are `(normal, offset)` and `other` one plane? The same coincidence rule `csg_faces` dedupes
    fragments by: normals aligned (both are already sign-canonical, so aligned means equal) and
    offsets within `CSG_TOLERANCE`."""
    return (abs(normal[0] * other[0][0] + normal[1] * other[0][1] + normal[2] * other[0][2] - 1.0)
            <= 1e-6 and abs(offset - other[1]) <= CSG_TOLERANCE)


def _own_planes(ctx: SurveyContext, actor) -> list:
    """The sign-canonical planes bounding `actor`'s own convex pieces, deduped, memoized on the
    context -- one actor is compared against every near brush in turn, and recomputing its own
    planes for each of them was 12% of the tier's runtime."""
    cached = ctx.planes.get(actor.name)
    if cached is not None:
        return cached
    out: list = []
    for cell in actorgraph.decompose_convex(actor, cache=ctx.cells):
        for n_i, d_i in cell.half_spaces:
            length = (n_i[0] ** 2 + n_i[1] ** 2 + n_i[2] ** 2) ** 0.5
            if length < 1e-9:
                continue
            normal = (n_i[0] / length, n_i[1] / length, n_i[2] / length)
            offset = d_i / length
            if next((c for c in normal if abs(c) > 1e-9), 0.0) < 0:
                normal, offset = (-normal[0], -normal[1], -normal[2]), -offset
            if not any(_same_plane(normal, offset, p) for p in out):
                out.append((normal, offset))
    ctx.planes[actor.name] = out
    return out


def contact_planes(ctx: SurveyContext, a, b) -> list:
    """Every candidate contact plane for the pair: the planes bounding either actor's own convex
    pieces, deduped by the same coincidence rule `csg_faces` uses.

    Read from the actors' OWN geometry, never from the resolved snapshot, and that is what fixes the
    case five rounds never tested: two Adds butted face to face with identical footprints consume
    each other's face on the shared plane, so NEITHER owner has a surviving fragment there, and a
    candidate list drawn from `ctx.faces` has nothing to offer the predicate at all. An authored
    boundary is not consumed by anything.

    A decomposition's internal split planes come along, since `ConvexCell` does not distinguish them
    from real faces. They cost a rejected candidate and nothing else: at an internal split the
    actor's own volume lies on both sides, so neither `_matter_side` nor `_is_carve_boundary` can
    attribute a contact to it.

    A non-brush actor contributes none -- a collision cylinder has no flat boundary to author a
    contact plane with -- so a prop's contact is always found on the brush side of the pair."""
    planes = list(_own_planes(ctx, a)) if a.brush is not None else []
    if b.brush is not None:
        planes += [p for p in _own_planes(ctx, b)
                   if not any(_same_plane(p[0], p[1], q) for q in planes)]
    return planes


def _self_consistent_plane(ctx: SurveyContext, actor, normal, offset: float) -> tuple:
    """`actor`'s OWN version of the plane closest to `(normal, offset)`, when it genuinely authors
    one coincident with it, else `(normal, offset)` unchanged.

    Fixes a real, shipped bug found by review: `contact_planes` dedupes two actors' own
    independently-computed versions of one coincident plane (`_same_plane`'s own `1e-6`
    normal-alignment tolerance) down to a SINGLE representative, then callers fed that one
    candidate to `plane_slices` for BOTH actors. But `_cell_slice`'s near-parallel-face skip
    (`abs(a) <= 1e-9 and abs(b) <= 1e-9`) is tuned for a plane truly self-consistent with the cell
    it slices -- a face of the actor that DIDN'T own the chosen candidate can be almost, but not
    exactly, parallel to it (rotation trig noise on the order of 1e-7 uu on this module's own
    rotated fixtures, a full three orders of magnitude inside `_same_plane`'s 1e-6 tolerance but
    six orders outside `_cell_slice`'s 1e-9 one), and that near-miss slips past the skip and clips
    the whole cross-section away. Confirmed live: a real, ordinary 28000 uu^2 flush contact between
    two differently-sized rotated Adds vanished at 17 deg / 30 deg (not 0 deg / 45 deg, where the
    trig happens to cancel exactly) -- silently, with no error, no existing fixture catching it
    because every prior rotated `touches` test pairs two IDENTICAL-size boxes.

    The fix is this lookup, used at every `plane_slices` call site that might receive a candidate
    plane belonging to the OTHER actor: always slice an actor on a plane that actor itself
    authored, never a foreign one. `_reproject_uv` then puts two actors' own (very slightly
    different) planes back into one shared frame afterward, by an exact change of basis rather
    than by clipping -- immune to the precision trap above because it never asks `_cell_slice`
    to judge near-parallel-but-not-quite against an unfamiliar plane."""
    if actor.brush is None:
        return normal, offset
    for n, o in _own_planes(ctx, actor):
        if _same_plane(n, o, (normal, offset)):
            return n, o
    return normal, offset


def _reproject_uv(points_uv, from_frame, to_frame) -> list:
    """`points_uv` (given in `from_frame`'s own (u, v) coordinates) re-expressed in `to_frame`'s --
    a pure change of basis through the shared world-space point, never a half-space clip. See
    `_self_consistent_plane` for why two actors' own versions of one coincident plane must each be
    sliced on their own terms and only brought into a common frame AFTERWARD, by this function."""
    o_from, u_from, v_from = from_frame
    o_to, u_to, v_to = to_frame
    out = []
    for u, v in points_uv:
        p = tuple(o_from[i] + u * u_from[i] + v * v_from[i] for i in range(3))
        out.append((sum((p[i] - o_to[i]) * u_to[i] for i in range(3)),
                    sum((p[i] - o_to[i]) * v_to[i] for i in range(3))))
    return out


def _matter_side(ctx: SurveyContext, actor, inner, outer) -> int | None:
    """`-1`/`+1` for the side of the plane `actor`'s own surviving matter is on, or None when it is
    on both sides or on neither.

    "Both" is penetration -- the actor has pushed through the boundary, which is `crosses`, not
    `touches`. "Neither" is an actor that is not at this plane at all. The two probe points sit
    `CSG_TOLERANCE` off the plane, so the relation's own tolerance is the only thing deciding it:
    matter within `CSG_TOLERANCE` of the plane is flush against it, matter beyond that penetrates.
    There is no separate probe step, which is what let round 5's effective tolerance be
    `_SIDE_PROBE_STEP` (0.05 uu) rather than the 0.015 uu the spec names."""
    at_inner = resolved_matter_of(ctx, actor, inner)
    if at_inner == resolved_matter_of(ctx, actor, outer):
        return None
    return -1 if at_inner else 1


def _was_solid_before(ctx: SurveyContext, subtract, point) -> bool:
    """Was `point` solid at the moment `subtract` ran -- i.e. did its carve remove anything HERE?

    Last writer among the brushes ahead of it in `csg_order`: an Add or Semisolid means matter was
    there, a Subtract means the space was already void. Where NO earlier brush reaches the point the
    answer is solid, because that is the world `MAP NEW` hands the first CSG brush -- carving the
    default-solid world is what an ordinary level's leading Subtract does, and it is a real carve."""
    index = ctx.csg_index.get(subtract.name, len(ctx.csg_order))
    for earlier in reversed(ctx.csg_order[:index]):
        if _in_authored_volume(ctx, earlier, point):
            return ctx.kinds[earlier.name] != "subtract"
    return True


def _is_carve_boundary(ctx: SurveyContext, actor, inner, outer) -> bool:
    """Is this plane, here, the boundary of `actor`'s own carve -- a surface its Subtract really
    made?

    A Subtract owns no matter, so it can never be a contact's matter side; what it authors is the
    surface, and something resting against that surface is the fact the spec insists on ("a
    Subtract's carve legitimately touches the resolved boundary it stopped at"). Two conditions,
    and the second is as load-bearing as the first.

    **Its authored volume must separate the two probe points** -- the plane bounds the carve here.
    That is the whole answer to an Add floating inside an enclosing Subtract: the Add's faces are
    adjacent to that Subtract's void at any distance, which is true and is not a contact, but they
    are nowhere near the carve's own boundary, so the Subtract is never attributable there and the
    pair produces nothing at 1 uu of clearance or at 960.

    **And the carve must be REAL at this point** (`_was_solid_before`). An authored boundary in
    space that was already void removed nothing and created no surface, so nothing can rest against
    it. Without this, a Subtract that carves nothing at all is a `touches` target from all six of
    its authored planes, and so is the far end of the spec's own routine idiom -- an oversized
    corridor run deliberately past the room it opens into, to avoid a coplanar seam -- at any
    distance from anything it actually removed. Both measured; both are now regression tests."""
    if actor.brush is None or _kind(ctx, actor) != "subtract":
        return False
    at_inner = _in_authored_volume(ctx, actor, inner)
    if at_inner == _in_authored_volume(ctx, actor, outer):
        return False
    return _was_solid_before(ctx, actor, inner if at_inner else outer)


def _contact_at(ctx: SurveyContext, a, b, inner, outer) -> bool:
    """Do `a` and `b` meet across the plane these two probe points straddle?

    Three shapes, and every one of the spec's cases is one of them:

    * **matter against matter** -- both actors survive here, and they must be on OPPOSITE sides. Two
      actors' matter on the SAME side of a plane is one buried in the other, the case no depth or
      distance measured at that plane can see: a peg 1 uu into a wall and a peg 100 uu into it both
      have every point on the wall's inner side.
    * **matter against a carve boundary** -- one actor's matter rests against the surface the other's
      Subtract left. Either side of it, deliberately: a carve victim is on the outside of the hole,
      and a Mover or a prop resting against a room's wall is on the inside of it.
    * **anything else** -- no fact. Two carve boundaries meeting is two Subtracts sharing a plane
      with nothing solid between them, which the spec rules `connects` and never `touches`; that
      falls out of requiring one side to be real matter, rather than from a kind table."""
    side_a = _matter_side(ctx, a, inner, outer)
    side_b = _matter_side(ctx, b, inner, outer)
    if side_a is not None and side_b is not None:
        return side_a != side_b
    if side_a is not None:
        return _is_carve_boundary(ctx, b, inner, outer)
    if side_b is not None:
        return _is_carve_boundary(ctx, a, inner, outer)
    return False


def _occupied_bounds(ctx: SurveyContext, actor) -> tuple:
    """`actor`'s own world AABB as floats -- its decomposed volume for a brush, its collision
    cylinder for a non-brush actor. `pair_touches`' first gate: two actors further apart than
    `CSG_TOLERANCE` on any axis cannot be flush anywhere, and `near_brushes`' own 1 uu pad admits
    plenty that are."""
    if actor.brush is not None:
        return _brush_bounds(ctx, actor)
    ext = collision_extent(actor, ctx.defaults)
    if ext is None or actor.location is None:
        return ((1.0, 1.0, 1.0), (-1.0, -1.0, -1.0))       # empty box: meets nothing
    radius, height = ext
    loc = tuple(float(c) for c in actor.location)
    half = (radius, radius, height)
    return (tuple(loc[i] - half[i] for i in range(3)), tuple(loc[i] + half[i] for i in range(3)))


# The smallest contact region that is a region rather than an edge. `CSG_TOLERANCE` is the finest
# distance the resolved model reproduces, so a patch of plane whose area is below that distance
# SQUARED cannot be told from a line or a point -- and an edge-to-edge or corner-to-corner meeting is
# not a touch. Derived from the one tolerance this relation has; not a second epsilon. The exact
# `== 0` it replaces only cancelled on axis-aligned integer coordinates: two 45-degree prisms meeting
# at exactly one edge left 1.9e-13 uu^2 of float dust behind and reported a contact, while the same
# shape unrotated correctly reported none.
_MIN_CONTACT_AREA = CSG_TOLERANCE ** 2


def _region_probes(region: list) -> list:
    """The `(u, v)` points a contact region is tested at: its centroid, plus the centroid of each
    triangle in a fan from it.

    One point is not enough, and the shape that proves it is the most ordinary wall in any level --
    two butted Adds with a doorway carved through the shared seam. The contact region is the whole
    seam, the doorway removes its middle, and the region's OWN centroid lands inside the doorway, so
    a single probe finds no matter on either side and the wall reports no contact with the wall it
    is built against (measured; now a regression test).

    Every point is strictly interior to the region, which is convex, and each is put through the
    same full contact test -- so more points can only find a contact that is really there.
    `touches` asks whether the two actors meet SOMEWHERE on the region, not everywhere on it.

    This is a sample, not a decomposition: a contact surviving only on a patch smaller than one fan
    triangle can still be missed. Deciding the region exactly would mean clipping it by every other
    brush's cross-section, which is a non-convex polygon subtraction this module has no need of
    elsewhere. Missing a fact is the safe direction."""
    n = len(region)
    cu = sum(p[0] for p in region) / n
    cv = sum(p[1] for p in region) / n
    return [(cu, cv)] + [((cu + region[i][0] + region[(i + 1) % n][0]) / 3.0,
                          (cv + region[i][1] + region[(i + 1) % n][1]) / 3.0) for i in range(n)]


def pair_touches(ctx: SurveyContext, a, b) -> bool:
    """Is there a plane where `a` and `b` meet flush, with no penetration?

    Symmetric in its two actors by construction, which is what makes one loop in `touches_facts_for`
    enough where every earlier round needed two survey directions to see a contact whose surviving
    face sits on only one side.

    For each candidate plane, each actor is sliced on ITS OWN self-consistent version of that plane
    (`_self_consistent_plane`) -- never the other actor's, a precision trap `_cell_slice`'s
    near-parallel-face skip can fall into (see that function's own docstring for the measured
    case) -- and the two slices reprojected into one shared frame (`_reproject_uv`) before being
    reduced to the region of that plane each actor's own volume actually reaches; the contact
    region is the intersection of the two and must be bigger than `_MIN_CONTACT_AREA` -- two rooms
    whose coplanar walls meet only along a shared edge produce a sliver and no fact. `_contact_at`
    then names the two sides at each of `_region_probes`' points, and the relation holds if any of
    them is a contact.

    No CSG solve. Every question here is asked of authored geometry, which is why the cost is a few
    polygon clips and a handful of point-in-brush probes per near actor rather than one truncated
    solve per near actor (round 5: 562 ms of solves in a 638 ms survey, against a 46 ms worst-case
    budget for the whole tier)."""
    (a_lo, a_hi), (b_lo, b_hi) = _occupied_bounds(ctx, a), _occupied_bounds(ctx, b)
    if any(a_lo[i] > b_hi[i] + CSG_TOLERANCE or b_lo[i] > a_hi[i] + CSG_TOLERANCE
           for i in range(3)):
        return False
    for normal, offset in contact_planes(ctx, a, b):
        na, oa = _self_consistent_plane(ctx, a, normal, offset)
        slices_a = plane_slices(ctx, a, na, oa)
        if not slices_a:
            continue
        nb, ob = _self_consistent_plane(ctx, b, normal, offset)
        slices_b = plane_slices(ctx, b, nb, ob)
        if not slices_b:
            continue
        frame_a = _plane_frame(na, oa)
        origin, u_axis, v_axis = frame_a
        frame_b = _plane_frame(nb, ob)
        for poly_a in slices_a:
            for poly_b_raw in slices_b:
                poly_b = _reproject_uv(poly_b_raw, frame_b, frame_a)
                region = relation._clip_2d(relation._ensure_ccw(poly_a),
                                            relation._ensure_ccw(poly_b))
                if len(region) < 3 or abs(relation._shoelace_area(region)) <= _MIN_CONTACT_AREA:
                    continue
                for u, v in _region_probes(region):
                    point = tuple(origin[i] + u * u_axis[i] + v * v_axis[i] for i in range(3))
                    inner = tuple(point[i] - na[i] * CSG_TOLERANCE for i in range(3))
                    outer = tuple(point[i] + na[i] * CSG_TOLERANCE for i in range(3))
                    if _contact_at(ctx, a, b, inner, outer):
                        return True
    return False


def touches_facts_for(ctx: SurveyContext) -> list[CsgFact]:
    """`touches`: the surveyed actor is flush against another actor's resolved boundary, with no
    penetration.

    Symmetric, so the surveyed actor always leads (spec, Directionality) and no depth is annotated.
    NOT source-restricted, unlike `crosses` -- a Subtract's carve legitimately stopping at the
    resolved boundary it never cut is exactly the fact worth reporting. The OTHER side must still
    author a resolved face, so `crosses_target_eligible` gates it: a Nonsolid bounds no solid, an
    Intersect/Deintersect contributes nothing, and a non-brush actor's collision cylinder is not
    world geometry. That gate is on the far side only, so a prop's contact is reported by the prop's
    own survey and not by the room's -- an asymmetry in a symmetric relation, inherited and still the
    owner's to settle.

    ONE pass over the near set, because `pair_touches` is symmetric in its two actors. Earlier rounds
    needed two directions because they enumerated candidate faces from the resolved snapshot, where a
    flush contact routinely leaves a surviving face on only one side -- and, when both sides consume
    each other's face, on neither. Candidate planes now come from the actors' own authored geometry,
    which nothing consumes.

    A pair `crosses` claims is never also reported here. The exclusion is per PAIR and direction-free
    -- `crosses` names the intruder and this relation names the surveyed actor, so comparing ordered
    pairs would let the same two actors be `crosses` one way and `touches` the other (round 4's
    per-face gate did exactly that). Where `crosses` itself is wrong the suppression follows it:
    board item `crosses-fires-on-a-subtract-s-carve-victim` records the one known case, a blind
    pocket carved into a wall, with a strict `xfail` pinning the `touches` fact it costs."""
    if ctx.probe.solidity is None:
        return []
    crossed = {frozenset((f.src, f.dst)) for f in crosses_facts_for(ctx)}
    facts = []
    for other in ctx.near:
        if not crosses_target_eligible(other, ctx.class_index):
            continue
        if frozenset((ctx.name, other.name)) in crossed:
            continue
        if pair_touches(ctx, ctx.surveyed, other):
            facts.append(CsgFact(src=ctx.name, dst=other.name, relation="touches"))
    return sorted(facts, key=lambda f: (f.src, f.dst))


def shared_region(ctx: SurveyContext, a, b) -> tuple | None:
    """The intersection of two actors' world AABBs, grown by `CSG_TOLERANCE`, or None when they do
    not meet at all -- a cheap reject before either real geometric test below runs.

    `_brush_bounds(ctx, actor)` (the module's own memoized, cells-agreeing AABB), not
    `writes.actor_bounds` -- that function's own docstring already names this exact trap: it
    "answers in Decimals over the actor's own polys", and this has to compare against float probe
    points and agree with the cells `point_in_brush` itself tests. Floats throughout, in `ctx` for
    the memo -- this is not `aabb_intersects`."""
    a_lo, a_hi = _brush_bounds(ctx, a)
    b_lo, b_hi = _brush_bounds(ctx, b)
    lo = tuple(max(a_lo[i], b_lo[i]) - CSG_TOLERANCE for i in range(3))
    hi = tuple(min(a_hi[i], b_hi[i]) + CSG_TOLERANCE for i in range(3))
    if any(lo[i] > hi[i] for i in range(3)):
        return None
    return lo, hi


# How finely a candidate contact region's own (already clipped, already real) 2-D extent is
# sampled when testing for VOIDNESS -- never a second geometric tolerance, purely a resolution
# choice, and NOT shared with `touches`' `_region_probes` (tuned for a different question and a
# proven, six-round history this function does not disturb). Denser than a fixed 5-point fan, and
# review found that matters: a real, ordinary-sized opening (a 200x200 uu doorway in a much larger
# shared wall) can sit off every one of `_region_probes`' 5 fixed points and be missed even though
# it is not narrow at all -- POSITION-dependent, not just size-dependent. `n` odd so the grid lands
# on the region's own bounding-box centre, same reasoning as the old `CONNECT_GRID`.
VOID_PROBE_GRID = 9


def _region_grid_probes(region: list, n: int = VOID_PROBE_GRID) -> list:
    """An `n x n` grid of `(u, v)` points over `region`'s own bounding box, filtered to the points
    that actually fall inside the convex polygon `region` (CCW-wound, as every caller here already
    produces via `relation._ensure_ccw`/`relation._clip_2d`).

    Scoped to the REAL clipped region -- typically room-sized, not the whole level -- rather than a
    world-space AABB, which is what made the original grid-sampling `voids_meet` too coarse to be
    useful: sampling the entire shared bounding box at a fixed low count. Sampling the much smaller,
    already-known-real region at equal or higher density is cheap (candidate regions surviving the
    `_MIN_CONTACT_AREA` gate are few).

    Every point is STRICTLY interior to `[lo, hi]` on each axis (`(k + 1) / (n + 1)`, never `k /
    (n - 1)`) -- matching `_region_probes`' own discipline, and load-bearing, not cosmetic: a grid
    that includes the exact box edge lands a sample exactly on a neighbouring actor's own boundary
    (e.g. a wall whose extent exactly matches the region here), where the resolved solidity oracle's
    boundary tie-break can read "not solid" for a point that is genuinely surrounded by solid
    everywhere else -- measured live: `two_rooms_split_by_an_intact_wall`'s region corner sampled
    exactly onto the Wall's own corner and read void, wrongly firing `connects` across an intact
    wall. Staying strictly inside costs nothing a real opening needs, since an opening of any
    reportable size has interior points too.

    Honest limit, stated rather than claimed away: any FIXED grid can still miss an opening narrower
    than its own spacing -- this cannot be solved by sampling alone, only by testing against the
    opening's own geometry, which this function has no access to (only the resolved solidity
    ORACLE, a point query, `probe.solidity.point_is_solid`)."""
    lo_u = min(p[0] for p in region)
    hi_u = max(p[0] for p in region)
    lo_v = min(p[1] for p in region)
    hi_v = max(p[1] for p in region)

    def axis(lo, hi):
        span = hi - lo
        if span <= 0.0:
            return [lo]
        return [lo + span * (k + 1) / (n + 1) for k in range(n)]

    def inside(u, v) -> bool:
        m = len(region)
        return all((region[(i + 1) % m][0] - region[i][0]) * (v - region[i][1]) -
                   (region[(i + 1) % m][1] - region[i][1]) * (u - region[i][0]) >= -1e-9
                   for i in range(m))

    return [(u, v) for u in axis(lo_u, hi_u) for v in axis(lo_v, hi_v) if inside(u, v)]


def _planar_void_contact(ctx: SurveyContext, a, b) -> bool:
    """Do `a` and `b` share a real (positive-AREA) patch of authored boundary that is VOID there?

    This is `pair_touches`'s own technique (Task 13, round 6 -- the fix that finally closed
    `touches`'s edge/corner and vanished-shared-face defects; `_self_consistent_plane`/
    `_reproject_uv` -- shared with `pair_touches`, see their docstrings -- the fix that closed its
    rotated-differently-sized-actor precision defect): every candidate plane from `contact_planes`
    (either actor's own face, exactly `pair_touches`' own candidate set), each actor's own reach
    onto that plane (`plane_slices`, on each actor's own self-consistent version of it), the two
    reprojected into one shared frame and clipped together exactly (`relation._clip_2d`), and the
    region rejected unless its area clears `_MIN_CONTACT_AREA` -- the same tolerance-derived
    threshold, not a second epsilon. What differs from `pair_touches` is the question asked of the
    surviving region: whether the shared patch itself is VOID, not which actor's matter is on which
    side -- a coincident carved plane is exactly the case with no surviving solid to be flush
    against (module docstring, `_contact_at`'s third bullet).

    This is also what makes an edge- or corner-only meeting (`two_cubes_meeting_at_one_edge`) a
    non-fact here even before any solidity probe runs: the two actors' own cross-sections at the
    only candidate plane(s) touching that edge overlap in a zero-area sliver, so `_MIN_CONTACT_AREA`
    rejects it exactly as it already does for `touches`.

    **This single mechanism also covers full nesting and a general partial merge -- no separate
    volume test is needed.** An earlier round of this function used `_own_planes(ctx,a)` x
    `_own_planes(ctx,b)` filtered to MUTUALLY coincident planes only, plus a separate centroid-based
    3-D containment test for the no-coincident-plane case (nesting). Review found that centroid test
    regressed the spec's own "partial merge" case -- it only fires when the shared volume covers
    roughly half of one actor's own extent, and a genuine, real 100x280x200 uu^3 overlap well under
    that fraction (confirmed void on both sides by direct point checks) produced no fact at all.

    The fix is to stop restricting candidates to MUTUALLY-owned planes and use `contact_planes`'
    full set (either actor's own face, exactly as `pair_touches` already does) instead. This is
    sound for a reason grounded in H-polytope geometry, not a heuristic: whenever two convex
    volumes' intersection has positive measure (a shared 2-D patch on a coincident plane, OR a
    genuine 3-D overlap), AT LEAST ONE of the two actors' own bounding half-space planes is a real
    boundary facet of that intersection -- every facet of an intersection of half-spaces lies on one
    of the ORIGINAL half-spaces, by construction. So testing every one of `a`'s and `b`'s own planes
    (not just the ones they happen to share) is complete: a real overlap of ANY shape always shows
    up as positive area on SOME candidate, and `plane_slices` genuinely reports an actor's own
    INTERIOR cross-section (not just its boundary face) wherever the plane cuts through the middle
    of its cell (`_cell_slice`'s own `lo <= 0 <= hi` branch) -- which is exactly how a nested or
    partially-merged actor's full cross-section at another actor's own face plane is recovered
    (verified: `redundant_nested_subtract`'s `InnerCarve` face at `plane_slices(ctx, OuterRoom,
    *that_plane)` returns `OuterRoom`'s full local cross-section there, not an empty result). No
    false positive risk either: a candidate plane one actor doesn't genuinely reach still fails
    `plane_slices`' own span test (`_cell_slice`), so a hit here is always real evidence of a
    positive-area shared, authored cross-section -- exactly the soundness argument `pair_touches`
    already relies on for its own broader candidate set.

    The voidness probe (`_region_grid_probes`, not `_region_probes`) is denser and scoped to the
    real clipped region for the same review-found reason: a doorway carved through an otherwise
    solid shared patch is a genuine opening of real size, and `_region_probes`' fixed 5-point fan
    (tuned for `touches`' different question) can miss one that doesn't happen to sit under the
    centroid or a corner-fan midpoint -- POSITION-dependent, not just size-dependent. See that
    function's own docstring for what a grid can and cannot promise."""
    for normal, offset in contact_planes(ctx, a, b):
        na, oa = _self_consistent_plane(ctx, a, normal, offset)
        slices_a = plane_slices(ctx, a, na, oa)
        if not slices_a:
            continue
        nb, ob = _self_consistent_plane(ctx, b, normal, offset)
        slices_b = plane_slices(ctx, b, nb, ob)
        if not slices_b:
            continue
        frame_a = _plane_frame(na, oa)
        origin, u_axis, v_axis = frame_a
        frame_b = _plane_frame(nb, ob)
        for poly_a in slices_a:
            for poly_b_raw in slices_b:
                poly_b = _reproject_uv(poly_b_raw, frame_b, frame_a)
                region = relation._clip_2d(relation._ensure_ccw(poly_a),
                                            relation._ensure_ccw(poly_b))
                if len(region) < 3 or abs(relation._shoelace_area(region)) <= _MIN_CONTACT_AREA:
                    continue
                for u, v in _region_grid_probes(region):
                    point = tuple(origin[i] + u * u_axis[i] + v * v_axis[i] for i in range(3))
                    if not ctx.probe.solidity.point_is_solid(point):
                        return True
    return False


# `voids_meet` decides continuity by LOCAL SOLIDITY only, never by the resolved model's zone
# numbers: the zone flood is a whole-model pass, so zone numbers are not reproducible under the
# bounded-neighborhood solve (spike.md §4 residual 3), and two rooms can share a zone without their
# voids meeting at all. No survey relation may read one -- `test_connects_reads_no_zone_number`
# pins this by grepping `voids_meet`'s and `connects_facts_for`'s own source, so the rationale lives
# HERE, outside both function bodies, rather than in either docstring.
def voids_meet(ctx: SurveyContext, a, b) -> bool:
    """Are `a`'s and `b`'s void regions continuous -- no surviving solid between them?

    `shared_region` is a fast reject only (disjoint AABBs can share nothing); the actual decision is
    `_planar_void_contact`'s single real-geometric-intersection test -- never a sampled grid over
    that box. A prior grid-sampling version of this function is what a live review caught missing a
    rotated coincident seam entirely (0/125 grid samples on a real 15/15-point seam) and false-firing
    on an edge/corner touch; a second review round found the fix's own replacement centroid-based
    volume test then missed the spec's "partial merge" case. Both are the same defect class `touches`
    needed six rounds to close, and both are closed here the way `touches` closed them: by testing
    the real region, not guessing at it with a fixed grid or a single representative point."""
    if ctx.probe.solidity is None:
        return False
    if shared_region(ctx, a, b) is None:
        return False
    return _planar_void_contact(ctx, a, b)


def connects_facts_for(ctx: SurveyContext) -> list[CsgFact]:
    """`connects`: the surveyed Subtract's void is continuous with another Subtract's void.

    Subtract-only on both sides, symmetric, so the surveyed actor leads. No depth and no `:idx` --
    the fact is the absence of a face, and there is no face to name.

    Gated by `_kind(ctx, actor) == "subtract"`, never the raw `query.csg_is_subtract` -- a Mover
    carries no `CsgOper` at all and is excluded from world CSG entirely (`kind_of`'s own docstring),
    so it has no void to be continuous with regardless of what its `CsgOper` prop (if any) happens to
    spell; every other csg-tier eligibility gate in this module (`crosses_target_eligible`,
    `_is_carve_boundary`) already goes through `_kind`/`kind_of` for exactly this reason.

    The SURVEYED actor's own decomposition is forced up front, unguarded -- matching
    `raw_facts_for`'s own rule that a degenerate SURVEYED brush propagates (a single-actor report has
    nothing left to say) while only a degenerate NEIGHBOUR is skipped. A neighbour whose decomposition
    fails inside `voids_meet` is silently dropped, not recorded: `CsgFact`/`connects_facts_for`
    return a bare `list[CsgFact]`, and neither `crosses_facts_for` nor `touches_facts_for` tracks a
    skipped csg-tier neighbour either (board item `csg-tier-raises-on-a-degenerate-neighbour-brush`
    covers the cross-cutting gap for the csg tier as a whole) -- adding a `skipped` channel to this
    one relation alone, ahead of that item, would be scope beyond what this task asked."""
    if ctx.surveyed.brush is None or _kind(ctx, ctx.surveyed) != "subtract":
        return []
    actorgraph.decompose_convex(ctx.surveyed, cache=ctx.cells)   # propagates on a bad SURVEYED brush
    out = []
    for other in ctx.near:
        if _kind(ctx, other) != "subtract":
            continue
        try:
            if voids_meet(ctx, ctx.surveyed, other):
                out.append(CsgFact(src=ctx.name, dst=other.name, relation="connects"))
        except actorgraph.DegenerateBrushError:
            continue          # a bad neighbour is skipped, as it is in the raw tier
    return sorted(out, key=lambda f: f.dst)


# Relative tolerance for the containment volume comparison. Named, not an inline literal, and
# RELATIVE rather than absolute: a level's Subtract volumes span many orders of magnitude, so a
# fixed epsilon would be meaningless at one end and dominant at the other. Matches `relation.py`'s
# own `_close`-style convention for the same problem on areas (spec: a genuine tie must break on
# trunk order, not on float noise).
VOLUME_TOLERANCE_REL = 1e-6


def volume_tolerance(a: float, b: float) -> float:
    return VOLUME_TOLERANCE_REL * max(1.0, abs(a), abs(b))


def volumes_tied(a: float, b: float) -> bool:
    return abs(a - b) <= volume_tolerance(a, b)


def containment_winner(ctx: SurveyContext, target, candidates) -> str | None:
    """Which of `candidates` (Subtract actors) owns `target`, or None when none does.

    The spec's rule: every candidate whose own AUTHORED shape fully contains `target` competes, and
    the one with the SMALLEST authored volume wins; a genuine tie within the relative tolerance
    breaks toward the LATER one in trunk order. A volume comparison, not a strict-subset/nesting
    test -- it stays correct when a carve brush is deliberately oversized past what it carves into,
    which is routine (to avoid coplanar faces) and which a subset rule silently gets wrong.

    Gated by `_kind(ctx, c) == "subtract"`, never the raw `query.csg_is_subtract` -- the same trap
    `connects_facts_for` already guards against (`test_connects_does_not_treat_a_mover_as_a_subtract`,
    a critical review finding there): a Mover carrying a stray `CsgOper=CSG_Subtract` prop (never
    emitted by any builder, but not forbidden on an imported actor block) would otherwise pass the
    raw prop check and wrongly compete to be a container, even though a Mover is excluded from world
    CSG entirely and authors no carve of its own. `connects_facts_for` gates the same way for the
    same reason. `carves_facts_for` still gates on the raw `query.csg_is_subtract` prop, but is not
    exposed to the same failure mode: its own answer comes from a counterfactual SOLVE
    (`removed_by`), and dropping a Mover from that solve changes nothing (a Mover never
    participates in world CSG), so a stray `CsgOper=CSG_Subtract` on one costs a wasted solve, never
    a wrong fact."""
    order = {n: i for i, n in enumerate(ctx.level.order)}
    best_name, best_volume = None, None
    for c in candidates:
        if c.name == target.name or _kind(ctx, c) != "subtract":
            continue
        try:
            if not authored_shape_contains(c, target, ctx.cells):
                continue
            volume = authored_volume(c, ctx.cells)
        except actorgraph.DegenerateBrushError:
            continue
        if best_volume is None or volume < best_volume - volume_tolerance(volume, best_volume):
            best_name, best_volume = c.name, volume
        elif volumes_tied(volume, best_volume) and order[c.name] > order[best_name]:
            best_name, best_volume = c.name, volume
    return best_name


def _containment_candidates(ctx: SurveyContext) -> list:
    """Every Subtract that could own something here: the surveyed actor when it is one, plus every
    Subtract in its neighborhood. Gated by `_kind`, not the raw `query.csg_is_subtract` -- see
    `containment_winner`'s docstring. Intersect/Deintersect are excluded the same way (`_kind` never
    reports either of them as `"subtract"`), which is also why they can never be a container."""
    out = [a for a in ctx.near if a.brush is not None and _kind(ctx, a) == "subtract"]
    if ctx.surveyed.brush is not None and _kind(ctx, ctx.surveyed) == "subtract":
        out.append(ctx.surveyed)
    return out


def contains_facts_for(ctx: SurveyContext) -> list[CsgFact]:
    """`contains`: the container (a Subtract) leads, whichever side is surveyed.

    Two directions, both computed:
    * the surveyed actor as CONTAINER, when it is a Subtract: every brush, Mover and point actor in
      its neighborhood whose full extent (or Location) its authored shape encloses, and which it
      WINS against every other competing Subtract.
    * the surveyed actor as CONTAINED, always: whichever Subtract in its neighborhood wins it.

    Not narrower than the raw tier, which fans containment out both ways already -- `build_graph`
    emits one edge per containing brush, and Task 8's raw tier reuses that shape."""
    candidates = _containment_candidates(ctx)
    facts: list = []

    if ctx.surveyed.brush is not None and _kind(ctx, ctx.surveyed) == "subtract":
        targets = [a for a in ctx.near if a.name != ctx.name] + list(ctx.points)
        for target in targets:
            if containment_winner(ctx, target, candidates) == ctx.name:
                facts.append(CsgFact(src=ctx.name, dst=target.name, relation="contains"))

    owner = containment_winner(ctx, ctx.surveyed, candidates)
    if owner is not None and owner != ctx.name:
        facts.append(CsgFact(src=owner, dst=ctx.name, relation="contains"))

    return sorted(facts, key=lambda f: (f.src, f.dst))


# Below this many square world units, a surviving-area difference is not a claim. Well above the
# boundary displacements the bounded-neighborhood truncation can introduce (eight of the spike's
# nine measured area differences moved a boundary by <= 0.024 uu; the worst symmetric difference was
# 224 uu^2, and that one was a known native `first_add_seed` defect on a 1-uu sliver, not truncation
# noise -- spike.md §4).
CARVE_AREA_EPS = 1.0

# A Subtract can only have removed matter from a kind that HAS matter to remove and is applied
# BEFORE it. Measured (spike.md §1, regression `test_csg_kind_facts.py`):
#   add       carved, with real area loss                                  -> valid target
#   nonsolid  contributes no solid, but its FACES are real world surfaces and a later Subtract
#             removes them with exactly the same area loss as an Add's     -> valid target
#   semisolid NEVER: the editor applies every Add/Subtract in LOOP 2 and only then, after the
#             repartition, the semisolids in LOOP 3, so trunk order cannot make one carveable
#   subtract/intersect/deintersect/mover  contribute nothing a Subtract could take
_CARVE_TARGET_KINDS = frozenset({"add", "nonsolid"})


def poly_area(verts) -> float:
    """A planar polygon's area, `0.5 * |newell|` -- the same relation `query.py`'s own `poly list`
    area uses (`texframe.newell`'s docstring)."""
    n = newell([tuple(float(c) for c in v) for v in verts])
    return 0.5 * (n[0] ** 2 + n[1] ** 2 + n[2] ** 2) ** 0.5


def authored_face_area(actor) -> float:
    """The total world-space area of ACTOR's own authored brush faces, before any CSG."""
    from . import polyalign
    if actor.brush is None:
        return 0.0
    return sum(poly_area(polyalign._world_verts(actor, p)) for p in actor.brush.polys
               if len(p.vertices) >= 3)


def surviving_face_area(probe, owner: str) -> float:
    """The total area of `owner`'s faces that survive in `probe`'s resolved world.

    Area, never face COUNT and never poly identity: a different tree shape splits the same surface
    into different polygons, so counts and indices are not comparable across two solves (spike.md §4
    residual 1). Summing area is."""
    return sum(poly_area(s.world_verts) for s in probe.world_surfaces
               if s.actor is not None and s.actor.name == owner)


def removed_by(ctx: SurveyContext, subtract, victim) -> bool:
    """Did `subtract` genuinely remove part of `victim`'s originally-contributed matter?

    Answered by a COUNTERFACTUAL SOLVE: re-solve the same neighborhood with `subtract` dropped and
    compare `victim`'s surviving face area. More survives without it <=> it took some. This is the
    same uncut-vs-cut comparison `kind_semantics.py` makes (`_solve([room, pillar])` against
    `_solve([room, pillar, cutter])`, then the pillar's own area on each), and it is what
    distinguishes the spec's two hard cases: a second Subtract carving EXACTLY an already-carved
    region changes nothing and reports nothing, while one that only PARTIALLY overlaps really does
    remove new matter and reports it.

    Never drops the level's FIRST world-CSG brush: that would fire `bsp_brush_csg`'s leading-Add
    world-shell shortcut on a different brush and change the whole tree (spike.md §4 residual 4).
    When `subtract` IS that brush, this returns False rather than solving a world the bounded-cost
    argument does not cover.

    The guard compares against `ctx.seed`, NOT `ctx.neighbors[0].name`. `neighbors` is in trunk
    order, so index 0 can be a Mover or the builder brush -- neither contributes to world CSG, so
    neither is the brush the solver seeds from, and the real seed would then sit at a later index
    and be droppable. `ctx.seed` is `seed_brush_name`'s answer: the first brush that actually
    contributes."""
    from .preview_native import solve_world_probe
    if not ctx.neighbors or subtract.name == ctx.seed:
        return False
    without = [a for a in ctx.neighbors if a.name != subtract.name]
    counterfactual = solve_world_probe(without, ctx.class_index)
    gained = surviving_face_area(counterfactual, victim.name) - \
        surviving_face_area(ctx.probe, victim.name)
    return gained > CARVE_AREA_EPS


def carves_facts_for(ctx: SurveyContext) -> list[CsgFact]:
    """`carves`: a Subtract removed part of another actor's originally-contributed matter.

    The agent leads, whichever side is surveyed -- so both directions are computed. "Part" means at
    least part: an Add entirely consumed by a later Subtract still reports `carves`, and that is the
    most valuable case of this fact, not an excluded one. Whatever of the victim still survives
    elsewhere reports `touches` as normal; if nothing survives, no `touches` accompanies the
    `carves`, which is correct -- there is nothing left to be flush against."""
    facts: list = []

    if ctx.surveyed.brush is not None and query.csg_is_subtract(ctx.surveyed):
        for other in ctx.near:
            if kind_of(other, ctx.class_index) not in _CARVE_TARGET_KINDS:
                continue
            if removed_by(ctx, ctx.surveyed, other):
                facts.append(CsgFact(src=ctx.name, dst=other.name, relation="carves"))
    elif ctx.surveyed.brush is not None and \
            kind_of(ctx.surveyed, ctx.class_index) in _CARVE_TARGET_KINDS:
        for other in ctx.near:
            if not query.csg_is_subtract(other):
                continue
            if removed_by(ctx, other, ctx.surveyed):
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
               contains_facts_for, carves_facts_for):
        out.extend(fn(ctx))
    return out


def survey(level, class_index, name: str, defaults) -> SurveyResult:
    """Both tiers for one actor, over ONE shared decomposition cache and ONE native solve.

    Raises `ActorNotFoundError` (unknown name), `actorgraph.DegenerateBrushError` (the SURVEYED
    actor's own brush), `preview_native.NativePreviewError` (no native extension, or a failed
    solve), `uprops.SchemaError` (an unresolvable class in the collision gate),
    `ActorHasNoLocationError` (the surveyed actor is non-brush with no `Location`) and
    `CollisionPropertyError` (a malformed `CollisionRadius`/`CollisionHeight` on the surveyed actor
    or a neighbour). The CLI maps every one of them to exit 2 -- none may reach the user as a
    traceback."""
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
    """One `csg `-prefixed line. Every `*_facts_for` already assigned `src`/`dst` in the spec's
    final direction, so this is pure formatting. No `:idx` at this tier, ever -- `crosses` alone
    carries an annotation, the measured penetration depth."""
    rel = fact.relation
    if fact.relation == "crosses" and fact.depth_uu is not None:
        rel = f"crosses({fact.depth_uu:.3g}uu)"
    return (f"csg {fact.src} {actorgraph._node_bracket(nodes[fact.src])} --{rel}--> "
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
    """Every stdout line of a survey, in order: the raw block, a blank separator when both tiers
    have something, then the csg block. A blank line is the ONLY line that does not start with a
    tier token."""
    lines = [format_raw_line(f, result.nodes) for f in result.raw]
    csg_lines = [format_csg_line(f, result.nodes) for f in result.csg]
    if lines and csg_lines:
        lines.append("")
    return lines + csg_lines
