"""`actor survey` — the bounded neighborhood, both tiers, and the CLI seam.

Fixtures live in `uedcli/tests/survey_scenarios.py`, one named builder per geometry, each returning
a `Scenario` so no test ever unpacks a tuple by arity.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from uedcli import actor_survey, relation
from uedcli.tests import survey_scenarios as scen


def _probe(sc, name):
    """The bounded-neighborhood solve for one surveyed actor in a scenario."""
    from uedcli.preview_native import solve_world_probe
    surveyed = sc.level.actors[name]
    return solve_world_probe(actor_survey.neighborhood(sc.level, sc.index, surveyed, sc.defaults),
                             sc.index)


def test_neighborhood_takes_only_brushes_whose_aabb_meets_the_region():
    sc = scen.far_apart_rooms()
    names = [a.name for a in actor_survey.neighborhood(sc.level, sc.index,
                                                       sc.level.actors["FarRoom"], sc.defaults)]
    assert "FarRoom" in names
    assert "Touching" in names      # shares FarRoom's +X wall
    assert "Distant" not in names   # 4000uu away, and not the level's first world-CSG brush


def test_neighborhood_always_includes_the_levels_first_world_csg_brush():
    """Not for its geometry — `bsp_brush_csg` special-cases a LEADING CSG_Add against a node-less
    world, seeding it as the world shell instead of classifying it (`bspcsg.rs`'s `first_add_seed`).
    Truncation changes which brush is first, so the shortcut fires on the wrong one. The spike
    measured this: without the clause, `nsfhq04 DeusExMover31`'s truncated solve lost all four
    `Brush799` faces and gained a `Brush798` one.
    (`dev/docs/spikes/2026-09-23-actor-survey-csg-kind-and-cost/harness/bounded_cost.py::neighborhood`.)"""
    sc = scen.far_apart_rooms()
    first = sc.level.order[0]
    names = [a.name for a in actor_survey.neighborhood(sc.level, sc.index,
                                                       sc.level.actors["FarRoom"], sc.defaults)]
    assert first == "Shell"
    assert "Shell" in names


def test_seed_brush_name_skips_a_leading_mover_and_names_the_first_contributing_brush():
    """`bsp_brush_csg` seeds the world shell from the first brush that actually CONTRIBUTES to the
    world solve. A Mover is a brush and contributes nothing, so trunk index 0 is not the answer —
    and any guard that says "the first brush" by INDEX would protect the wrong actor while the real
    seed sat further down, droppable. Built inline rather than as a scenario: this is about trunk
    order alone, no geometry."""
    from uedcli.builders import cube, make_brush_actor
    from uedcli.model import Level
    from uedcli.tests.conftest import StubClassIndex
    door = make_brush_actor("Door", cube(64, 8, 128), mover_class="Engine.Mover")
    wall = make_brush_actor("Wall", cube(256, 64, 256), csg="add")
    lvl = Level(actors={a.name: a for a in (door, wall)}, order=["Door", "Wall"])
    index = StubClassIndex()
    assert lvl.order[0] == "Door"
    assert actor_survey.in_world_csg(door, index) is False
    assert actor_survey.seed_brush_name(lvl, index) == "Wall"


def test_neighborhood_preserves_trunk_order():
    """The CSG evaluation order IS the actor-set order, so the selection must not re-sort."""
    sc = scen.far_apart_rooms()
    names = [a.name for a in actor_survey.neighborhood(sc.level, sc.index,
                                                       sc.level.actors["FarRoom"], sc.defaults)]
    positions = [sc.level.order.index(n) for n in names]
    assert positions == sorted(positions)


def test_near_brushes_excludes_the_far_first_brush_that_neighborhood_forces_in():
    """The first-brush clause is for the SOLVE's correctness, not for pair-testing: a brush 4000uu
    away shares no face with anything here and must not be fed to `classify_pair`."""
    sc = scen.far_apart_rooms()
    near = [a.name for a in actor_survey.near_brushes(sc.level, sc.index,
                                                      sc.level.actors["FarRoom"], sc.defaults)]
    assert "Shell" not in near
    assert "Touching" in near


def test_region_pad_is_one_uu_and_stays_decimal():
    """`actor_bounds` returns Decimals and `aabb_intersects` adds its own Decimal slack, so a bare
    float pad raises TypeError against them. The value is 1.0 uu — the spike's own `PAD`
    (`harness/bounded_cost.py:35`), which every one of its 140 verified surveys ran at."""
    from decimal import Decimal
    sc = scen.far_apart_rooms()
    lo, hi = actor_survey.region_of(sc.level.actors["FarRoom"], sc.defaults)
    assert all(isinstance(c, Decimal) for c in lo + hi)
    assert actor_survey.NEIGHBORHOOD_PAD == Decimal("1")


def test_nearby_point_actors_finds_a_light_inside_the_surveyed_room():
    sc = scen.room_with_pillar_and_light()
    names = [a.name for a in actor_survey.nearby_point_actors(sc.level,
                                                              sc.level.actors["Room"],
                                                              sc.defaults)]
    assert "Light" in names


# ------------------------------------------------------------- review round: malformed collision values

def test_collision_radius_nan_raises_named_error_not_a_bare_arithmetic_exception():
    """`Decimal("NaN")` parses without error, so a naive numeric-format check lets it through --
    and `aabb_intersects`'s comparisons then raise a bare `decimal.InvalidOperation`. The malformed
    value must be caught and named before it ever reaches that comparison."""
    actor = scen.point("Bad", (0, 0, 0),
                        props=[("bCollideActors", "True"), ("bBlockActors", "True"),
                               ("CollisionRadius", "NaN")])
    with pytest.raises(actor_survey.CollisionPropertyError):
        actor_survey.region_of(actor, scen.stub_defaults())


def test_collision_radius_infinity_raises_instead_of_producing_an_unbounded_region():
    """`Infinity` parses and compares fine, so left unguarded it would silently defeat the whole
    bounded-cost guarantee this feature exists for."""
    actor = scen.point("Bad", (0, 0, 0),
                        props=[("bCollideActors", "True"), ("bBlockActors", "True"),
                               ("CollisionRadius", "Infinity")])
    with pytest.raises(actor_survey.CollisionPropertyError):
        actor_survey.region_of(actor, scen.stub_defaults())


def test_collision_radius_negative_raises_instead_of_inverting_the_aabb():
    """A negative radius would silently build an inverted (lo > hi) box that `aabb_intersects`
    still returns True for -- a corrupt fact reported as a normal one."""
    actor = scen.point("Bad", (0, 0, 0),
                        props=[("bCollideActors", "True"), ("bBlockActors", "True"),
                               ("CollisionRadius", "-30")])
    with pytest.raises(actor_survey.CollisionPropertyError):
        actor_survey.region_of(actor, scen.stub_defaults())


def test_collision_height_out_of_domain_is_also_guarded():
    """Both extent() call sites in `_collision_half_extent` are guarded, not just the radius one."""
    actor = scen.point("Bad", (0, 0, 0),
                        props=[("bCollideActors", "True"), ("bBlockActors", "True"),
                               ("CollisionRadius", "10"), ("CollisionHeight", "-5")])
    with pytest.raises(actor_survey.CollisionPropertyError):
        actor_survey.region_of(actor, scen.stub_defaults())


# ------------------------------------------------------------- review round: surveyed actor with no Location

def test_region_of_raises_for_a_non_brush_actor_with_no_location():
    """A missing `Location` on a point actor is UNKNOWN, not `(0,0,0)` -- silently defaulting it
    would fabricate a neighborhood around the world origin. Mirrors `nearby_point_actors`' own
    already-adopted rule for a location-less CANDIDATE, applied here to the SURVEYED actor."""
    from uedcli.model import Actor
    ghost = Actor(name="Ghost", cls="Engine.Light", location=None)
    with pytest.raises(actor_survey.ActorHasNoLocationError):
        actor_survey.region_of(ghost, scen.stub_defaults())


def test_neighborhood_raises_for_a_location_less_surveyed_actor():
    from uedcli.model import Actor, Level
    ghost = Actor(name="Ghost", cls="Engine.Light", location=None)
    room = scen.brush("Room", (256, 256, 256), (0, 0, 0))
    lvl = Level(actors={"Room": room, "Ghost": ghost}, order=["Room", "Ghost"])
    with pytest.raises(actor_survey.ActorHasNoLocationError):
        actor_survey.neighborhood(lvl, scen.StubClassIndex(), ghost, scen.stub_defaults())


def test_nearby_point_actors_skips_a_candidate_with_no_location():
    """A location-less CANDIDATE (as opposed to the surveyed actor above) is skipped, not raised on
    -- `nearby_point_actors` filters it out before ever calling `region_of` on it."""
    from uedcli.model import Actor, Level
    room = scen.brush("Room", (1024, 1024, 1024), (0, 0, 0), csg="subtract")
    ghost = Actor(name="Ghost", cls="Engine.Light", location=None)
    lvl = Level(actors={"Room": room, "Ghost": ghost}, order=["Room", "Ghost"])
    names = [a.name for a in actor_survey.nearby_point_actors(lvl, room, scen.stub_defaults())]
    assert "Ghost" not in names


# ------------------------------------------------------------- review round: the collision gate itself

def test_region_of_ignores_collision_radius_without_bblockactors():
    """`_blocks_movement` requires BOTH `bCollideActors` AND `bBlockActors` -- a collide-only actor
    (a typical shipped trigger) must not grow the region by its `CollisionRadius`."""
    trigger = scen.point("Trigger", (0, 0, 0),
                          props=[("bCollideActors", "True"), ("bBlockActors", "False"),
                                 ("CollisionRadius", "500"), ("CollisionHeight", "500")])
    lo, hi = actor_survey.region_of(trigger, scen.stub_defaults())
    assert hi[0] - lo[0] == Decimal("2")   # just the 1uu pad on each side, no collision growth
    assert hi[2] - lo[2] == Decimal("2")


def test_region_of_grows_by_collision_extent_when_actor_blocks_movement():
    """The same actor, with `bBlockActors` also `True`, DOES grow by its collision cylinder's
    bounding box: 2 * CollisionRadius in X/Y, 2 * CollisionHeight in Z, plus the pad."""
    blocker = scen.point("Blocker", (0, 0, 0),
                          props=[("bCollideActors", "True"), ("bBlockActors", "True"),
                                 ("CollisionRadius", "64"), ("CollisionHeight", "128")])
    lo, hi = actor_survey.region_of(blocker, scen.stub_defaults())
    assert hi[0] - lo[0] == Decimal("130")   # 2*64 + 2*1 pad
    assert hi[2] - lo[2] == Decimal("258")   # 2*128 + 2*1 pad


# ------------------------------------------------------------- review round: absent vs present-but-empty

def test_blocks_movement_present_empty_value_is_not_replaced_by_the_class_default():
    """An explicit, empty `bCollideActors` ("" -- present, not absent) must NOT be coalesced with a
    truthy class default. `field_or`'s `is not None` test (mirroring
    `serve/scene.py::_actor_radii`) is what keeps a present-but-empty value from silently reading
    as absent."""
    defaults = scen.defaults_with({"bCollideActors": "True", "bBlockActors": "True"})
    actor = scen.point("Weird", (0, 0, 0), props=[("bCollideActors", "")])
    assert actor_survey._blocks_movement(actor, defaults) is False


def test_blocks_movement_falls_back_to_the_class_default_when_truly_absent():
    """The mirror case: an actor that states NEITHER field at all takes both from the class
    default -- proving the stub actually exercises the class-default branch, not just instance
    props."""
    defaults = scen.defaults_with({"bCollideActors": "True", "bBlockActors": "True"})
    actor = scen.point("Default", (0, 0, 0))
    assert actor_survey._blocks_movement(actor, defaults) is True


# ------------------------------------------------------------- review round: SchemaError propagation

def test_region_of_propagates_schema_error_for_an_unresolvable_class():
    """`failing_defaults()` models a missing game package -- `region_of` must let `SchemaError`
    propagate uncaught rather than guessing "does not collide"."""
    from uedcli import uprops
    actor = scen.point("Ghost", (0, 0, 0), cls="Unknown.Class")
    with pytest.raises(uprops.SchemaError):
        actor_survey.region_of(actor, scen.failing_defaults())


# ------------------------------------------------------------- review round: NEIGHBORHOOD_PAD, behaviorally

def test_pad_is_the_exact_selection_threshold():
    """A candidate exactly `NEIGHBORHOOD_PAD` (1uu) away from the surveyed actor's own edge is
    selected; one 2uu away is not. Proves the constant's VALUE matters, not just its type."""
    sc = scen.pad_boundary_neighbors()
    names = [a.name for a in actor_survey.neighborhood(sc.level, sc.index,
                                                       sc.level.actors["Anchor"], sc.defaults)]
    assert "JustWithinPad" in names
    assert "JustOutsidePad" not in names


# ------------------------------------------------------------- review round: empty-case coverage

def test_seed_brush_name_returns_none_for_a_brush_less_level():
    from uedcli.model import Level
    lvl = Level(actors={"Light": scen.point("Light", (0, 0, 0))}, order=["Light"])
    assert actor_survey.seed_brush_name(lvl, scen.StubClassIndex()) is None


def test_neighborhood_is_empty_for_a_level_with_no_brushes():
    from uedcli.model import Level
    lvl = Level(actors={"Light": scen.point("Light", (0, 0, 0))}, order=["Light"])
    out = actor_survey.neighborhood(lvl, scen.StubClassIndex(), lvl.actors["Light"], scen.stub_defaults())
    assert out == []


# ------------------------------------------------------------- Task 8: the raw tier

def test_raw_tier_reports_touches_and_carves_for_the_surveyed_brush():
    sc = scen.niche_carved_into_wall()
    got = actor_survey.raw_facts_for(sc.level, sc.index, "Wall", sc.defaults)
    rels = {(f.src, f.relation, f.dst) for f in got.facts}
    assert ("Niche", "carves", "Wall") in rels
    assert ("Wall", "touches", "Bystander") in rels


def test_raw_tier_spells_it_carves_with_the_subtract_leading_not_carved_by():
    """`level graph` prints `carved_by` with the ADD leading (`actorgraph.classify_pair`'s last
    line). `actor survey` prints `carves` with the SUBTRACT leading, whichever side is surveyed --
    the owner's 'one name per interaction, flip the sides to match' ruling (spec, Round 6). This is
    a presentation choice in THIS verb only; `level graph` is untouched."""
    sc = scen.niche_carved_into_wall()
    for surveyed in ("Wall", "Niche"):
        facts = actor_survey.raw_facts_for(sc.level, sc.index, surveyed, sc.defaults).facts
        carve = next(f for f in facts if f.relation == "carves")
        assert (carve.src, carve.dst) == ("Niche", "Wall")
        assert not any(f.relation == "carved_by" for f in facts)


def test_raw_touches_puts_the_surveyed_actor_first_and_swaps_its_matched_pair_with_it():
    """A symmetric relation leads with whoever you asked about. `Edge.matched_pair` is glued to
    `(src, dst)` positionally, so flipping the names MUST flip the pair too -- a rename-only flip
    renders a real face selector against the wrong brush (spec, Output shape)."""
    sc = scen.niche_carved_into_wall()
    a = next(f for f in actor_survey.raw_facts_for(sc.level, sc.index, "Wall", sc.defaults).facts
             if f.relation == "touches" and f.dst == "Bystander")
    b = next(f for f in actor_survey.raw_facts_for(sc.level, sc.index, "Bystander",
                                                   sc.defaults).facts
             if f.relation == "touches" and f.dst == "Wall")
    assert (a.src, a.dst) == ("Wall", "Bystander")
    assert (b.src, b.dst) == ("Bystander", "Wall")
    assert a.matched_pair is not None
    assert b.matched_pair == (a.matched_pair[1], a.matched_pair[0])


def test_from_edge_flips_a_symmetric_fact_when_the_surveyed_actor_is_the_edges_dst():
    """`_from_edge`'s flip branch, exercised directly.

    `raw_facts_for` always passes the surveyed actor as `classify_pair`'s `name_a`, so every edge it
    hands `_from_edge` already leads with the surveyed name and the flip branch never fires through
    that path. The branch is still the thing that GUARANTEES the orientation: without this test it
    is unexercised code, and a later change to the call order would silently start emitting
    `touches` facts led by the wrong actor with nothing going red. Constructed here as a bare
    `actorgraph.Edge` rather than through a scenario, because no scenario can reach it.
    """
    from uedcli import actorgraph
    edge = actorgraph.Edge(src="Other", dst="Wall", relation="touches", directed=False,
                           matched_pair=(2, 5), area_estimate=64.0)
    fact = actor_survey._from_edge(edge, "Wall")
    assert (fact.src, fact.dst) == ("Wall", "Other")
    assert fact.matched_pair == (5, 2)          # glued to (src, dst) positionally
    assert fact.area_estimate == 64.0


def test_raw_tier_reports_contains_for_a_mover_inside_a_subtract():
    sc = scen.room_contains_a_mover()
    facts = actor_survey.raw_facts_for(sc.level, sc.index, "Room", sc.defaults).facts
    assert ("Room", "contains", "Door") in {(f.src, f.relation, f.dst) for f in facts}


def test_raw_tier_reports_contains_for_a_point_actor_inside_the_surveyed_brush():
    sc = scen.room_with_pillar_and_light()
    facts = actor_survey.raw_facts_for(sc.level, sc.index, "Room", sc.defaults).facts
    assert ("Room", "contains", "Light") in {(f.src, f.relation, f.dst) for f in facts}


def test_raw_tier_surveying_the_point_actor_shows_the_same_containment():
    """`contains` is fixed-direction: the container leads whichever side you survey."""
    sc = scen.room_with_pillar_and_light()
    facts = actor_survey.raw_facts_for(sc.level, sc.index, "Light", sc.defaults).facts
    assert ("Room", "contains", "Light") in {(f.src, f.relation, f.dst) for f in facts}


def test_raw_tier_does_not_use_build_graph():
    """`build_graph` is whole-level and O(brushes^2) -- the measured expensive half (spike.md §4).
    The raw tier must run `classify_pair` over the bounded neighborhood instead."""
    import inspect
    src = inspect.getsource(actor_survey.raw_facts_for)
    assert "build_graph" not in src
    assert "classify_pair" in src


def test_raw_line_format_matches_level_graphs_grammar_with_a_tier_prefix():
    sc = scen.niche_carved_into_wall()
    got = actor_survey.raw_facts_for(sc.level, sc.index, "Wall", sc.defaults)
    touch = next(f for f in got.facts if f.relation == "touches")
    line = actor_survey.format_raw_line(touch, got.nodes)
    assert line.startswith("raw Wall:")
    assert "[Engine.Brush Add] --touches(" in line
    assert "uu^2)--> Bystander:" in line


def test_raw_line_carries_no_idx_or_area_on_a_contains_line():
    """`room_with_pillar_and_light` also yields a `Room contains Pillar` brush-pair fact (Pillar is a
    later-order Add fully inside Room's Subtract void -- `classify_pair`'s own contains/carved_by
    order heuristic, not this verb's concern) -- filtered out here since this test is about the
    POINT-actor contains line's format, not which contains fact comes first."""
    sc = scen.room_with_pillar_and_light()
    got = actor_survey.raw_facts_for(sc.level, sc.index, "Room", sc.defaults)
    fact = next(f for f in got.facts if f.relation == "contains" and f.dst == "Light")
    line = actor_survey.format_raw_line(fact, got.nodes)
    assert line == ("raw Room [Engine.Brush Subtract] --contains--> Light [Engine.Light]")


def test_csg_faces_collapses_every_coplanar_fragment_of_one_owner_to_one_candidate():
    """A `SolvedSurface` is a BSP FRAGMENT: one authored face routinely splits into many. Dedup by
    (owner, plane) is what stops one relationship being reported N times — and it is also how the
    spec's 'decide by plane coincidence, never by face existence' rule is implemented."""
    pytest.importorskip("uedcli_native")
    sc = scen.niche_carved_into_wall()
    surveyed = sc.level.actors["Wall"]
    probe = _probe(sc, "Wall")
    faces = actor_survey.csg_faces(probe, actor_survey.region_of(surveyed, sc.defaults))
    keys = [(f.owner, tuple(round(c, 3) for c in f.normal), round(f.offset, 3)) for f in faces]
    assert len(keys) == len(set(keys))
    wall_fragments = sum(1 for s in probe.world_surfaces
                        if s.actor is not None and s.actor.name == "Wall")
    wall_faces = sum(1 for f in faces if f.owner == "Wall")
    # The wall is a box: at most 6 distinct planes, however many fragments the carve produced.
    assert wall_faces <= 6
    assert wall_fragments > wall_faces      # the carve really did split at least one face


def test_csg_faces_normal_sign_is_canonical_so_one_plane_has_one_key():
    """Two fragments of the same plane can come back wound oppositely. The key must not depend on
    which one was seen first."""
    pytest.importorskip("uedcli_native")
    sc = scen.niche_carved_into_wall()
    faces = actor_survey.csg_faces(_probe(sc, "Wall"),
                                   actor_survey.region_of(sc.level.actors["Wall"], sc.defaults))
    for f in faces:
        first = next(c for c in f.normal if abs(c) > 1e-9)
        assert first > 0


def test_csg_faces_drops_a_face_that_only_shares_one_coordinate_band_with_the_region():
    """The region filter is an AABB INTERSECTION, not a per-axis OR. `Wall`'s +Y face survives at
    y=32 wherever x,z sit outside BOTH the `Niche` hole (x,z in [-64, 64]) and `Bystander`'s own
    flush footprint (x in [-32, 32], z in [118, 182] -- flush add-on-add contact consumes the wall's
    face there entirely, ordinary CSG behavior, not a bug in this filter). x=150, z=0 is clear
    of both, and its +X face sits at x=256: a 2uu region there shares the +X face's y band (that
    ring spans y=-32..32) while sitting 106 uu away from it in x -- an OR-across-axes test keeps
    that face, an intersection test drops it.

    Planes are keyed by `(owner, normal, offset)`, not just `(normal, offset)`: `Bystander` sits on
    this same plane elsewhere in the neighborhood, so an owner-blind key can't tell which actor's
    face was actually found -- an EARLIER version of this test picked a region that, before the
    fixture fix above, sat inside the `Niche` hole where `Wall` itself had no face at all, and
    passed only because `Bystander` happened to supply a coincident plane there instead."""
    pytest.importorskip("uedcli_native")
    sc = scen.niche_carved_into_wall()
    probe = _probe(sc, "Wall")
    region = ((149.0, 31.0, -1.0), (151.0, 33.0, 1.0))   # 2uu box on the wall's +Y face at x=150
    planes = {(f.owner, tuple(round(c, 3) for c in f.normal), round(f.offset, 3))
              for f in actor_survey.csg_faces(probe, region)}
    assert ("Wall", (0.0, 1.0, 0.0), 32.0) in planes     # the face the region is on
    assert ("Wall", (1.0, 0.0, 0.0), 256.0) not in planes  # 106uu away — never a candidate


def test_collision_extent_needs_both_collide_and_block():
    """`bCollideActors` alone is not a claim about matter: a DataLinkTrigger (R=520), a FlagTrigger
    (R=630), a Teleporter all set it so they can be touched, block nothing, and are routinely sized
    to span rooms, walls included. Measured across 1522 collidable shipped actors, the non-blocking
    ones are 471 of them and carry the entire deep tail — gating them out drops the worst by-design
    overlap from 436 uu to 64 uu (spike.md §3)."""
    sc = scen.room_with_a_flush_mounted_prop()
    assert actor_survey.collision_extent(sc.level.actors["Keypad"], sc.defaults) == (16.0, 16.0)
    assert actor_survey.collision_extent(sc.level.actors["Trigger"], sc.defaults) is None
    assert actor_survey.collision_extent(sc.level.actors["Ghost"], sc.defaults) is None


def test_region_of_a_point_actor_covers_its_real_collision_extent():
    """A non-brush actor's shape is its collision cylinder, exactly as a brush's is its own
    vertices. A cylinder of radius R and half-height H bounds to `Location +/- (R, R, H)` -- the
    same box a box-shaped volume of those half-extents would -- and then the SAME `NEIGHBORHOOD_PAD`
    goes on top. Without it `Keypad`'s region would be 2 uu across and the `+X` wall it is mounted
    flush against (x=512) would fall outside it, so no face of that wall would ever reach
    `ctx.faces`. `Ghost` has no collision volume, so the same formula gives it the bare padded point
    box -- the degenerate case, not a special one.

    `Trigger` shows the gate: it sets `bCollideActors` and `CollisionRadius=520` but blocks nothing,
    so its cylinder is not matter and sizing a 1042-uu region (and solving the neighborhood that
    selects) off it would buy nothing. Same gate `collision_extent` applies, so the two agree."""
    from decimal import Decimal
    sc = scen.room_with_a_flush_mounted_prop()
    lo, hi = actor_survey.region_of(sc.level.actors["Keypad"], sc.defaults)
    assert (lo[0], hi[0]) == (Decimal(487), Decimal(521))      # 504 -/+ 16, then -/+ 1 of pad
    assert actor_survey.region_of(sc.level.actors["Ghost"], sc.defaults) == \
        ((Decimal(503), Decimal(-1), Decimal(-1)), (Decimal(505), Decimal(1), Decimal(1)))
    assert actor_survey.region_of(sc.level.actors["Trigger"], sc.defaults) == \
        ((Decimal(503), Decimal(-1), Decimal(-1)), (Decimal(505), Decimal(1), Decimal(1)))


def test_collision_extent_present_empty_value_is_not_replaced_by_the_class_default():
    """`field(name) or default` would treat an explicitly-present empty `CollisionRadius` ("" --
    present, not absent) as absent and substitute the class default -- a bug `serve/scene.py
    ::_actor_radii` already found and fixed with an `is not None` test. Class default `64` would
    read as a real 64uu radius if coalesced; the correct, uncoalesced read leaves `""` to
    `_to_decimal` (which can't parse it, so it falls to `0`), so `collision_extent` sees a
    zero-size radius and returns `None` -- the observable proof the empty value won as-is."""
    defaults = scen.defaults_with({"bCollideActors": "True", "bBlockActors": "True",
                                    "CollisionRadius": "64", "CollisionHeight": "64"})
    actor = scen.point("Weird", (0, 0, 0), props=[("CollisionRadius", "")])
    assert actor_survey.collision_extent(actor, defaults) is None


def test_collision_extent_falls_back_to_the_class_default_when_truly_absent():
    """The mirror case: an actor that states NEITHER collision field at all takes both from the
    class default -- proving the stub actually exercises the class-default branch, not just
    instance props (matching `_blocks_movement`'s own analogous pair, Task 7's review round)."""
    defaults = scen.defaults_with({"bCollideActors": "True", "bBlockActors": "True",
                                    "CollisionRadius": "64", "CollisionHeight": "64"})
    actor = scen.point("Default", (0, 0, 0))
    assert actor_survey.collision_extent(actor, defaults) == (64.0, 64.0)


# --------------------------------------- review round: collision_extent's own malformed-value guard

def test_collision_extent_nan_raises_rather_than_returning_a_nan_extent():
    """`collision_extent` must reject a malformed `CollisionRadius` exactly as `region_of`'s
    `_collision_half_extent` already does (the block above) -- both now go through the shared
    `_validated_extent`. Before the fix, `collision_extent` used a bare float parse with no range
    check and returned `(nan, 16.0)` here instead of raising, which would have fed NaN sample points
    into `cylinder_sample_points` -> `any_point_solid`."""
    actor = scen.point("Bad", (0, 0, 0),
                        props=[("bCollideActors", "True"), ("bBlockActors", "True"),
                               ("CollisionRadius", "NaN"), ("CollisionHeight", "16")])
    with pytest.raises(actor_survey.CollisionPropertyError):
        actor_survey.collision_extent(actor, scen.stub_defaults())


def test_collision_extent_infinity_raises_rather_than_returning_an_infinite_extent():
    actor = scen.point("Bad", (0, 0, 0),
                        props=[("bCollideActors", "True"), ("bBlockActors", "True"),
                               ("CollisionRadius", "Infinity"), ("CollisionHeight", "16")])
    with pytest.raises(actor_survey.CollisionPropertyError):
        actor_survey.collision_extent(actor, scen.stub_defaults())


def test_collision_extent_negative_radius_raises_rather_than_reading_as_no_collision():
    """Before the fix, a negative radius failed the `radius <= 0.0` check and returned `None` --
    silently misclassifying a malformed actor as one with no collision volume at all, instead of
    naming the bad value."""
    actor = scen.point("Bad", (0, 0, 0),
                        props=[("bCollideActors", "True"), ("bBlockActors", "True"),
                               ("CollisionRadius", "-16"), ("CollisionHeight", "16")])
    with pytest.raises(actor_survey.CollisionPropertyError):
        actor_survey.collision_extent(actor, scen.stub_defaults())


def test_collision_extent_propagates_a_schema_error_rather_than_guessing():
    """An unresolvable class means the collision gate cannot be answered. Exit 2 is the caller's job
    (Task 18); silently treating it as 'does not collide' would be a substituted default."""
    import pytest
    from uedcli import uprops
    sc = scen.room_with_a_flush_mounted_prop()
    with pytest.raises(uprops.SchemaError):
        actor_survey.collision_extent(sc.level.actors["Keypad"], scen.failing_defaults())


def test_crosses_source_eligibility_follows_the_specs_kind_table():
    sc = scen.kind_table_scenario()
    ci, d = sc.index, sc.defaults
    eligible = {n for n in sc.level.order
                if actor_survey.crosses_source_eligible(sc.level.actors[n], ci, d)}
    assert {"Adder", "Semi", "Door"} <= eligible          # Add, Semisolid, Mover
    assert eligible.isdisjoint({"Cutter", "Nonsolid", "Inter", "Deinter"})


def test_crosses_target_eligibility_follows_the_specs_kind_table():
    sc = scen.kind_table_scenario()
    ci = sc.index
    ok = {n for n in sc.level.order
          if actor_survey.crosses_target_eligible(sc.level.actors[n], ci)}
    assert {"Adder", "Semi", "Cutter"} <= ok              # Add, Semisolid, Subtract author faces
    assert ok.isdisjoint({"Nonsolid", "Inter", "Deinter", "Door", "Lamp"})


def test_cylinder_sample_points_never_leaves_the_cylinder():
    """The regression against reintroducing box sampling. The engine's collision volume is a
    cylinder, so no sample may stand further than `radius` from the axis -- a box corner would stand
    at `radius * sqrt(2)` = 22.6 uu for R=16 and invent penetration into a diagonal wall.

    Hand-checked: 3 Z levels x (1 axis point + 8 ring points) = 27, the same count the box version
    used. The first ring point is at +X exactly, so an axis-aligned face sees the cylinder's true
    extreme; that is what keeps the flush-mount depths below exact."""
    from math import hypot
    pts = actor_survey.cylinder_sample_points((504.0, 0.0, 0.0), 16.0, 16.0)
    assert len(pts) == 27
    assert {round(p[2], 6) for p in pts} == {-16.0, 0.0, 16.0}
    assert max(round(hypot(p[0] - 504.0, p[1]), 6) for p in pts) == 16.0
    assert max(round(p[0], 6) for p in pts) == 520.0


def test_extent_reaches_solid_is_true_for_a_flush_mounted_prop():
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.room_with_a_flush_mounted_prop()
    ctx = actor_survey.build_context(sc.level, sc.index, "Keypad", sc.defaults)
    assert actor_survey.extent_reaches_solid(ctx, (504.0, 0.0, 0.0), 16.0, 16.0) is True
    assert actor_survey.extent_reaches_solid(ctx, (0.0, 0.0, 0.0), 16.0, 16.0) is False


def test_build_context_solves_once_and_shares_the_decomposition_cache():
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.niche_carved_into_wall()
    cells = {}
    ctx = actor_survey.build_context(sc.level, sc.index, "Wall", sc.defaults, cells=cells)
    assert ctx.cells is cells
    assert ctx.probe.solidity is not None
    assert ctx.faces and all(isinstance(f, actor_survey.CsgFace) for f in ctx.faces)
    assert [a.name for a in ctx.near] == ["Niche", "Bystander"]


# --------------------------------------------------------------------- Task 12: crosses

def test_a_resolved_faces_solid_side_is_determined_by_the_solidity_probe_not_by_winding():
    """A `CsgFace`'s normal is sign-canonicalized and carries no facing. Rather than trust the
    ring's winding -- which `bspcsg.rs`'s leading-Add seed deliberately reverses for the world
    shell -- the solid side is MEASURED: step a short distance off the face's centroid both ways and
    ask the native solidity query. Exactly one side must be solid for a face that bounds solid.

    Scenario: `test_csg_kind_facts`' own Room/Pillar/Cutter, whose solid/void answers at LEFT and
    RIGHT are already pinned by that committed regression."""
    pytest.importorskip("uedcli_native")
    sc = scen.pillar_in_room()
    ctx = actor_survey.build_context(sc.level, sc.index, "Pillar", sc.defaults)
    pillar_faces = [f for f in ctx.faces if f.owner == "Pillar"]
    assert pillar_faces, "the Add pillar contributes surviving faces"
    for f in pillar_faces:
        sign = actor_survey.face_outward_sign(ctx, f)
        assert sign in (1.0, -1.0), "exactly one side of a solid-bounding face is solid"


def test_crosses_fires_for_an_add_poking_through_a_niche_wall_and_names_only_the_immediate_owner():
    """The spec's locality rule: `Additive4` crosses `Subtract3`, the boundary it actually pushes
    through, and never `Additive2`, however deep the nesting.

    Surveying `Additive4` alone would pass this even by accident: region-clipping keeps `Additive2`'s
    own faces out of `Additive4`'s survey region entirely, so `not any(f.dst == "Additive2")` proves
    nothing about the both-sides straddle check on its own (verified: `ctx.faces` for this survey
    carries no `Additive2`-owned entry at all). Surveying `Additive2` closes that gap: `Additive2`'s
    own faces ARE in `ctx.near`/`ctx.faces` there (`Additive4`'s footprint sits well inside
    `Additive2`'s own AABB), and `Additive4`'s matter genuinely lies entirely on the solid side of
    every one of them (it never reaches below `Additive2`'s `y=96` or above its `y=160`, and its
    `x,z` stay inside `Additive2`'s own `x,z` bounds too) -- so this is the case the both-sides check
    (`penetration_depth`: some point past the plane AND some point on the void side) exists for, not
    the region-clipping accident. Regression for the spec's own forbidden fact
    (`actor-survey-and-actor-relation-csg-resolved/spec.md:315-319`): a prior version of this
    algorithm reported `Additive4 --crosses--> Additive2` here."""
    pytest.importorskip("uedcli_native")
    sc = scen.shelf_pokes_through_a_niche_wall()

    ctx = actor_survey.build_context(sc.level, sc.index, "Additive4", sc.defaults)
    facts = actor_survey.crosses_facts_for(ctx)
    assert any(f.src == "Additive4" and f.dst == "Subtract3" for f in facts)
    assert not any(f.dst == "Additive2" for f in facts)
    assert not any(f.src == "Additive2" and f.dst == "Additive4" for f in facts)
    assert all(f.relation == "crosses" and f.depth_uu is not None and f.depth_uu > 0
               for f in facts)

    ctx2 = actor_survey.build_context(sc.level, sc.index, "Additive2", sc.defaults)
    assert any(f.owner == "Additive2" for f in ctx2.faces), \
        "the real case: Additive2's own faces must be in-region for this to test anything"
    facts2 = actor_survey.crosses_facts_for(ctx2)
    assert not any(f.src == "Additive4" and f.dst == "Additive2" for f in facts2)


def test_crosses_never_fires_from_a_subtract():
    """The design bug the source restriction exists to fix: without it, a Subtract room's raw shape
    trivially 'crosses' every Add placed inside it -- firing for every piece of furniture in every
    room."""
    pytest.importorskip("uedcli_native")
    sc = scen.pillar_in_room()
    ctx = actor_survey.build_context(sc.level, sc.index, "Room", sc.defaults)
    assert actor_survey.crosses_facts_for(ctx) == []


def test_crosses_fires_for_a_flush_mounted_collision_extent_with_a_measured_depth():
    """Under the bBlockActors gate, ~12% of physically-blocking shipped actors really are inside
    solid, by ~8 uu at the median. The fact is true and is reported, made readable by the depth
    (spike.md §3).

    `Keypad` sits at x=504 with R=16, and the `+X` wall's face is at x=512. The wall's normal is
    axis-aligned, so `cylinder_sample_points`' first ring point lands on the cylinder's extreme at
    x = 504 + 16 = 520 exactly, and the measured depth is 8 uu -- the same number the old box sample
    gave, because a box face centre and a cylinder ring point coincide on an axis-aligned normal.
    That face only reaches `ctx.faces` because `region_of` covers the actor's real collision extent
    (Task 7) -- a zero-size point box would leave it 7 uu outside the region."""
    pytest.importorskip("uedcli_native")
    sc = scen.room_with_a_flush_mounted_prop()
    ctx = actor_survey.build_context(sc.level, sc.index, "Keypad", sc.defaults)
    facts = actor_survey.crosses_facts_for(ctx)
    assert any(f.src == "Keypad" and f.dst == "Room" for f in facts)
    assert 4.0 < next(f for f in facts if f.dst == "Room").depth_uu < 12.0


def test_crosses_fires_for_a_point_actor_whose_location_is_outside_the_surveyed_brush():
    """Direction 2, and the regression for `nearby_point_actors`' extent-aware candidate test
    (Task 7). `Bracket` sits at x=520, OUTSIDE `Room`'s own padded AABB (x = 513), so a candidate
    filter reading the bare `Location` drops it from `ctx.points` and this fact disappears when you
    survey `Room` while still appearing when you survey `Bracket` -- the one-sided pair
    `crosses_facts_for` is written to rule out. Its collision cylinder spans x in [504, 536], which
    does meet the region, so the extent-aware test keeps it, and its deepest sample point -- the
    ring point at +X, at x = 520 + 16 = 536 -- is 24 uu past the `+X` wall's face at x=512.

    `Keypad` is not the case under test here: its `Location` is inside `Room`'s AABB, so the
    narrower filter would keep it and this direction would look fine."""
    pytest.importorskip("uedcli_native")
    sc = scen.room_with_a_flush_mounted_prop()
    assert Decimal(520) > actor_survey.region_of(sc.level.actors["Room"], sc.defaults)[1][0]
    ctx = actor_survey.build_context(sc.level, sc.index, "Room", sc.defaults)
    assert "Bracket" in [a.name for a in ctx.points]
    facts = actor_survey.crosses_facts_for(ctx)
    fact = next((f for f in facts if f.src == "Bracket" and f.dst == "Room"), None)
    assert fact is not None and fact.relation == "crosses"
    assert 20.0 < fact.depth_uu < 28.0


def test_crosses_does_not_fire_for_a_non_blocking_trigger_volume():
    pytest.importorskip("uedcli_native")
    sc = scen.room_with_a_flush_mounted_prop()
    ctx = actor_survey.build_context(sc.level, sc.index, "Trigger", sc.defaults)
    assert actor_survey.crosses_facts_for(ctx) == []


def test_crosses_reports_the_reverse_direction_when_the_surveyed_actor_is_the_target():
    """`crosses` is fixed-direction: the intruder always leads. Surveying the actor that was crossed
    INTO must still show the fact, with the intruder as src -- the spec's own worked example has
    `Additive4 --crosses--> Subtract3`, and surveying `Subtract3` has to show it too."""
    pytest.importorskip("uedcli_native")
    sc = scen.shelf_pokes_through_a_niche_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Subtract3", sc.defaults)
    facts = actor_survey.crosses_facts_for(ctx)
    assert any(f.src == "Additive4" and f.dst == "Subtract3" for f in facts)


def test_crosses_dedupes_to_one_fact_per_src_dst_pair():
    """A wall is many BSP fragments and several planes. One relationship, one line."""
    pytest.importorskip("uedcli_native")
    sc = scen.shelf_pokes_through_a_niche_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Additive4", sc.defaults)
    facts = actor_survey.crosses_facts_for(ctx)
    keys = [(f.src, f.dst, f.relation) for f in facts]
    assert len(keys) == len(set(keys))


# --------------------------------------------------------------------- Task 13: touches

def test_touches_fires_between_the_surveyed_actor_and_a_face_it_is_flush_against():
    pytest.importorskip("uedcli_native")
    sc = scen.niche_carved_into_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Bystander", sc.defaults)
    facts = actor_survey.touches_facts_for(ctx)
    assert any(f.src == "Bystander" and f.dst == "Wall" and f.relation == "touches"
               for f in facts)
    assert all(f.depth_uu is None for f in facts)


def test_touches_is_reported_from_either_side_of_the_pair():
    """Symmetric, so the surveyed actor leads -- and the fact has to be visible from BOTH surveys.
    `Bystander`'s own flush contact consumes `Wall`'s face directly underneath it, so the two sides
    do not find the pair through the same face."""
    pytest.importorskip("uedcli_native")
    sc = scen.niche_carved_into_wall()
    for name, other in (("Bystander", "Wall"), ("Wall", "Bystander")):
        ctx = actor_survey.build_context(sc.level, sc.index, name, sc.defaults)
        facts = actor_survey.touches_facts_for(ctx)
        assert any(f.src == name and f.dst == other for f in facts), name


def test_touches_is_not_source_restricted_so_a_subtract_can_lead_one():
    """Unlike `crosses`. A room's Subtract stopping exactly at its bounding wall is how 'this room
    is bounded by that wall, and the wall is intact' gets stated."""
    pytest.importorskip("uedcli_native")
    sc = scen.subtract_stops_flush_against_a_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Room", sc.defaults)
    facts = actor_survey.touches_facts_for(ctx)
    assert any(f.src == "Room" and f.dst == "Wall" for f in facts)


def test_touches_finds_a_pair_whose_only_surviving_face_belongs_to_the_other_side():
    """The x=224 contact plane carries exactly one surviving resolved face and it belongs to
    `Room`; `Wall`'s own face there was consumed by the carve that stops on it. The fact still has
    to be visible from `Wall`'s survey, which is what a predicate reading candidate planes off the
    resolved snapshot could only do by computing a second direction."""
    pytest.importorskip("uedcli_native")
    sc = scen.subtract_stops_flush_against_a_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Wall", sc.defaults)
    assert [f.owner for f in ctx.faces
            if f.normal == (1.0, 0.0, 0.0) and f.offset == 224.0] == ["Room"]
    assert any(f.src == "Wall" and f.dst == "Room"
               for f in actor_survey.touches_facts_for(ctx))


def test_touches_does_not_fire_for_an_actor_buried_in_the_others_solid():
    """`Peg` enters through `Wall`'s x=192 face and stops 100uu inside its solid, so four of its
    vertices sit exactly ON that plane. Plane coincidence alone calls that a flush touch, and
    `crosses` cannot catch it either -- `Peg` never reaches the void on the far side. What excludes
    it is that `Peg`'s matter and `Wall`'s matter are on the SAME side of that face: the two are
    interpenetrating, not resting against each other."""
    pytest.importorskip("uedcli_native")
    sc = scen.peg_buried_in_a_wall()
    for name, other in (("Peg", "Wall"), ("Wall", "Peg")):
        ctx = actor_survey.build_context(sc.level, sc.index, name, sc.defaults)
        facts = actor_survey.touches_facts_for(ctx)
        assert not any(f.dst == other for f in facts), (name, facts)


@pytest.mark.parametrize("depth", [1, 2, 7, 25, 50, 75, 93, 98, 99])
def test_touches_does_not_fire_at_any_partial_burial_depth(depth):
    """The whole 1..99 uu range, not one sample of it. A partly-sunk `Peg` still has flank faces out
    in the void, so `Wall`'s matter is genuinely flush against them -- the burial is on a different
    plane entirely, 100uu away, and a predicate that only names the two sides of the nearest contact
    accepts every one of these (measured: the round-4 predicate fired at all 99 depths, in both
    trunk orders). `crosses` does not catch them either: `Wall`'s x=192 face survives only as the
    flanking fragment `Peg`'s own contact split it into, which never overlaps `Peg`'s footprint."""
    pytest.importorskip("uedcli_native")
    sc = scen.peg_partly_buried_in_a_wall(depth)
    for name, other in (("Peg", "Wall"), ("Wall", "Peg")):
        ctx = actor_survey.build_context(sc.level, sc.index, name, sc.defaults)
        facts = actor_survey.touches_facts_for(ctx)
        assert not any(f.dst == other for f in facts), (depth, name, facts)


@pytest.mark.parametrize("prop", ["Keypad", "Door"])
def test_touches_fires_for_a_point_actor_or_a_mover_resting_on_a_wall(prop):
    """Neither a point actor's collision cylinder nor a Mover's private model is in world CSG, so
    neither is in `csg_order` and no last-writer rule over that list can ever name one.
    `resolved_matter_of` asks the per-actor question instead, which is what lets a non-brush actor
    lead a `touches` line at all -- the spec's "not source-restricted", and its "a Mover is treated
    exactly like an Add"."""
    pytest.importorskip("uedcli_native")
    sc = scen.props_flush_against_a_room_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, prop, sc.defaults)
    facts = actor_survey.touches_facts_for(ctx)
    assert any(f.src == prop and f.dst == "Room" for f in facts), facts
    assert not actor_survey.crosses_facts_for(ctx)      # flush, not 1uu into the wall


def test_a_non_brush_actor_is_never_the_other_side_of_a_touches_line():
    """The stated cost of `crosses_target_eligible` gating both directions, pinned rather than left
    to be rediscovered: a point actor or a Mover can LEAD a `touches` line but can never be NAMED as
    the far side of one, so surveying the room reports neither prop. That is what the spec's own
    rule gives -- a collision cylinder is not world geometry and a Mover authors no world face --
    but `touches` is symmetric and the surveyed actor is supposed to lead, so a fact visible from
    one side of a pair and not the other is a real asymmetry. Flagged for the owner, not decided
    here."""
    pytest.importorskip("uedcli_native")
    sc = scen.props_flush_against_a_room_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Room", sc.defaults)
    assert actor_survey.touches_facts_for(ctx) == []


def test_touches_does_not_fire_for_a_prop_that_reaches_into_the_wall():
    """The contrast fixture: `room_with_a_flush_mounted_prop`'s `Keypad` is 8uu INTO the solid, so
    its cylinder claims both sides of the wall face. That is `crosses`, and never `touches`."""
    pytest.importorskip("uedcli_native")
    sc = scen.room_with_a_flush_mounted_prop()
    ctx = actor_survey.build_context(sc.level, sc.index, "Keypad", sc.defaults)
    assert actor_survey.touches_facts_for(ctx) == []
    assert any(f.src == "Keypad" and f.dst == "Room"
               for f in actor_survey.crosses_facts_for(ctx))


def test_touches_does_not_fire_for_a_mover_floating_in_the_void():
    """A Mover with no contact at all. Its own faces coincide with nothing, and `Room`'s faces are
    512uu away, so neither side of any candidate contact is the Mover's matter."""
    pytest.importorskip("uedcli_native")
    sc = scen.room_contains_a_mover()
    ctx = actor_survey.build_context(sc.level, sc.index, "Door", sc.defaults)
    assert actor_survey.touches_facts_for(ctx) == []


def test_touches_does_not_fire_between_two_rooms_sharing_only_wall_planes():
    """Two Subtract rooms carved side by side. Their four other walls are coplanar continuations of
    each other, and `RoomA`'s carve stops exactly on the solid side of each of `RoomB`'s -- so an
    unbounded "reaches the plane without passing it" test fires on a contact 100uu from anything the
    pair shares. The spec rules this shape `connects`, never `touches`."""
    pytest.importorskip("uedcli_native")
    sc = scen.two_rooms_side_by_side()
    for name, other in (("RoomA", "RoomB"), ("RoomB", "RoomA")):
        ctx = actor_survey.build_context(sc.level, sc.index, name, sc.defaults)
        facts = actor_survey.touches_facts_for(ctx)
        assert not any(f.dst == other for f in facts), (name, facts)


def test_a_contact_plane_outlives_the_resolved_face_it_would_have_been_read_from():
    """Candidate planes come from the actors' own authored geometry, never from `ctx.faces`, and
    this is what that buys. On `peg_buried_in_a_wall` the full solve keeps `Wall`'s x=192 face only
    as the flanking fragment `Peg`'s own contact split it into, which by construction does not
    overlap `Peg` at all; on `niche_carved_into_wall` `Bystander`'s flush contact consumes the
    `y=32` fragment directly underneath it. `contact_planes` offers both planes regardless."""
    pytest.importorskip("uedcli_native")
    sc = scen.peg_buried_in_a_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Peg", sc.defaults)
    final = next(f for f in ctx.faces if f.owner == "Wall" and f.offset == 192.0)
    assert min(v[1] for v in final.verts) == 32.0        # flanking: starts past Peg's own footprint
    planes = actor_survey.contact_planes(ctx, ctx.level.actors["Peg"], ctx.level.actors["Wall"])
    assert any(n == (1.0, 0.0, 0.0) and off == 192.0 for n, off in planes)

    sc = scen.niche_carved_into_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Bystander", sc.defaults)
    final = next(f for f in ctx.faces if f.owner == "Wall")
    assert min(v[0] for v in final.verts) == 32.0        # flanking, alongside Bystander
    planes = actor_survey.contact_planes(ctx, ctx.level.actors["Bystander"],
                                          ctx.level.actors["Wall"])
    assert any(n == (0.0, 1.0, 0.0) and off == 32.0 for n, off in planes)


def test_a_far_seed_brush_does_not_disturb_a_touch():
    """`neighborhood`'s own first-brush clause forces the level's seed brush into the solve set even
    when it is nowhere near the surveyed actor, and `near_brushes` then has to keep it out of the
    fact set. Pinned on the fixture whose seed is 4000uu away and in the set only because of that
    clause."""
    pytest.importorskip("uedcli_native")
    sc = scen.far_apart_rooms()
    ctx = actor_survey.build_context(sc.level, sc.index, "FarRoom", sc.defaults)
    assert ctx.seed == "Shell"
    assert ctx.neighbors[0].name == "Shell"
    assert any(f.src == "FarRoom" and f.dst == "Touching"
               for f in actor_survey.touches_facts_for(ctx))


def test_touches_does_not_fire_where_two_voids_meet_on_a_subtracts_plane():
    """`Cutter` takes the pillar's right half, so its own faces survive where they cut real matter
    -- which makes its whole PLANE a live boundary. Out beyond the pillar the same plane has
    `Room`'s void on one side and `Cutter`'s on the other and nothing solid anywhere near, and the
    spec's "a surviving solid face on at least one side" is what rules that out. Two Subtracts are
    `connects`, never `touches`."""
    pytest.importorskip("uedcli_native")
    sc = scen.pillar_in_room()
    for name, other in (("Room", "Cutter"), ("Cutter", "Room")):
        ctx = actor_survey.build_context(sc.level, sc.index, name, sc.defaults)
        facts = actor_survey.touches_facts_for(ctx)
        assert not any(f.dst == other for f in facts), (name, facts)


def test_resolved_matter_of_drops_matter_a_later_subtract_removed():
    """The per-actor question a last-writer rule cannot answer. `Wall`'s authored body covers the
    whole niche, but `Niche` removed that matter, so `Wall` has none there. Where two Adds overlap
    the difference runs the other way: `Peg` is inside `Wall`, and BOTH have matter at the same
    point even though only the later one wrote it last."""
    pytest.importorskip("uedcli_native")
    sc = scen.niche_carved_into_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Niche", sc.defaults)
    wall, niche = ctx.level.actors["Wall"], ctx.level.actors["Niche"]
    assert actor_survey.resolved_matter_of(ctx, wall, (0, 0, 0)) is False    # carved away
    assert actor_survey.resolved_matter_of(ctx, wall, (100, 0, 0)) is True   # outside the niche
    assert actor_survey.resolved_matter_of(ctx, niche, (0, 0, 0)) is False   # a Subtract has none

    sc = scen.peg_buried_in_a_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Peg", sc.defaults)
    for name in ("Peg", "Wall"):
        assert actor_survey.resolved_matter_of(ctx, ctx.level.actors[name], (200, 0, 0)) is True


def test_touches_fires_for_a_subtracts_carve_victim():
    """`Niche` cuts a hole through `Wall`; what remains of `Wall` is flush against the hole's own
    side walls. The source's matter extends 192uu past those planes -- it IS the wall the niche cut
    -- so no "how far past the plane" measure can accept this, and whose matter lies on each side
    of the contact can."""
    pytest.importorskip("uedcli_native")
    sc = scen.niche_carved_into_wall()
    for name, other in (("Niche", "Wall"), ("Wall", "Niche")):
        ctx = actor_survey.build_context(sc.level, sc.index, name, sc.defaults)
        facts = actor_survey.touches_facts_for(ctx)
        assert any(f.src == name and f.dst == other for f in facts), (name, facts)


@pytest.mark.xfail(reason="blocked by a `crosses` false positive, not by `touches`: shipped "
                          "`penetration_depth` reports `Wall --crosses--> Pocket` (224uu) for the "
                          "wall a Subtract carved, and `touches_facts_for` reports nothing for a "
                          "pair `crosses` claims. `pair_touches` itself accepts the pair (its own "
                          "assertion below). The same `crosses` mechanism produces the "
                          "spec-mandated `Additive4 --crosses--> Subtract3`, so it cannot be "
                          "corrected for one without breaking the other. See board item "
                          "`crosses-fires-on-a-subtract-s-carve-victim`.", strict=True)
def test_touches_fires_for_a_blind_pockets_carve_victim():
    """The same carve-victim fact as above, on a fixture with none of `niche_carved_into_wall`'s
    quirks -- an ordinary solve and a carve that stops inside the wall."""
    pytest.importorskip("uedcli_native")
    sc = scen.blind_pocket_in_a_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Pocket", sc.defaults)
    assert actor_survey.pair_touches(ctx, ctx.level.actors["Pocket"], ctx.level.actors["Wall"])
    facts = actor_survey.touches_facts_for(ctx)
    assert any(f.src == "Pocket" and f.dst == "Wall" for f in facts), facts


def test_resolved_matter_ignores_the_pooled_solidity_oracle():
    """`face_outward_sign` asks the resolved solidity oracle, which pools every actor's contribution
    with the world's own default solidity and the leading-Add seed shell -- so on the two fixtures
    `touches` has to separate it gives the SAME answer, `+1`, solid on the intruder's own side. On
    `niche_carved_into_wall` that oracle is outright inverted: `Wall` is the leading Add, so its own
    interior reads VOID. `resolved_matter_of` reads the authored volumes instead and names who is
    actually there, which is why it, and not the oracle, decides a contact's sides."""
    pytest.importorskip("uedcli_native")
    buried = scen.peg_buried_in_a_wall()
    ctx = actor_survey.build_context(buried.level, buried.index, "Peg", buried.defaults)
    face = next(f for f in ctx.faces if f.owner == "Wall")
    assert actor_survey.face_outward_sign(ctx, face) == 1.0
    peg, wall = ctx.level.actors["Peg"], ctx.level.actors["Wall"]
    assert actor_survey.resolved_matter_of(ctx, peg, (192.05, 0, 0)) is True
    assert actor_survey.resolved_matter_of(ctx, wall, (192.05, 0, 0)) is True    # both, same side
    assert actor_survey.resolved_matter_of(ctx, wall, (191.95, 0, 0)) is False

    flush = scen.niche_carved_into_wall()
    ctx = actor_survey.build_context(flush.level, flush.index, "Bystander", flush.defaults)
    face = next(f for f in ctx.faces if f.owner == "Wall")
    assert actor_survey.face_outward_sign(ctx, face) == 1.0             # inverted by the seed shell
    assert ctx.probe.solidity.point_is_solid((0, 31.95, 150)) is False  # inside Wall, reads void
    wall, bystander = ctx.level.actors["Wall"], ctx.level.actors["Bystander"]
    assert actor_survey.resolved_matter_of(ctx, wall, (0, 31.95, 150)) is True
    assert actor_survey.resolved_matter_of(ctx, bystander, (0, 32.05, 150)) is True


def test_touches_and_crosses_are_mutually_exclusive_for_one_pair():
    """Within CSG_TOLERANCE of coincident is `touches`; clearly past it is `crosses`. A pair is
    never both."""
    pytest.importorskip("uedcli_native")
    sc = scen.shelf_pokes_through_a_niche_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Additive4", sc.defaults)
    crossed = {(f.src, f.dst) for f in actor_survey.crosses_facts_for(ctx)}
    touched = {(f.src, f.dst) for f in actor_survey.touches_facts_for(ctx)}
    assert crossed and crossed & touched == set()


def test_touches_never_names_a_nonsolid_or_an_intersect_as_the_other_side():
    pytest.importorskip("uedcli_native")
    sc = scen.kind_table_scenario()
    ctx = actor_survey.build_context(sc.level, sc.index, "Adder", sc.defaults)
    named = {f.dst for f in actor_survey.touches_facts_for(ctx)}
    assert named.isdisjoint({"Nonsolid", "Inter", "Deinter", "Lamp"})


def test_touches_dedupes_to_one_fact_per_pair():
    """A wall is many fragments and several planes; one relationship is one line. `Wall` meets
    `Bystander` on one plane and `Niche` on four, and reports two lines."""
    pytest.importorskip("uedcli_native")
    sc = scen.niche_carved_into_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Wall", sc.defaults)
    keys = [(f.src, f.dst) for f in actor_survey.touches_facts_for(ctx)]
    assert keys and len(keys) == len(set(keys))


def test_touches_fires_between_two_adds_butted_face_to_face():
    """The shape five rounds never tested: a wall built from two blocks with IDENTICAL footprints.
    Their mutual contact consumes the shared plane's face on BOTH owners, so the resolved model
    holds no face there for either of them, and a predicate reading candidates off that model has
    nothing to test. Required in both directions."""
    pytest.importorskip("uedcli_native")
    sc = scen.two_adds_butted_face_to_face()
    ctx = actor_survey.build_context(sc.level, sc.index, "BlockA", sc.defaults)
    assert [f for f in ctx.faces
            if abs(abs(f.normal[0]) - 1.0) < 1e-6 and abs(f.offset) < 1e-6] == []
    for name, other in (("BlockA", "BlockB"), ("BlockB", "BlockA")):
        ctx = actor_survey.build_context(sc.level, sc.index, name, sc.defaults)
        facts = actor_survey.touches_facts_for(ctx)
        assert any(f.src == name and f.dst == other for f in facts), (name, facts)


@pytest.mark.parametrize("clearance", [1, 8, 64, 240, 480, 960])
def test_touches_does_not_fire_for_an_add_standing_free_in_a_subtracts_void(clearance):
    """An Add inside an enclosing Subtract, touching no wall, at six clearances spanning three
    orders of magnitude. Its faces have that Subtract's void on one side at every one of them, so
    naming the two sides of the contact accepts it -- measured firing at 960uu on the round-5
    predicate. What rules it out is that the plane is nowhere near the Subtract's own carve
    boundary."""
    pytest.importorskip("uedcli_native")
    sc = scen.an_add_inside_an_enclosing_subtract(clearance)
    for name, other in (("Shelf", "Room"), ("Room", "Shelf")):
        ctx = actor_survey.build_context(sc.level, sc.index, name, sc.defaults)
        facts = actor_survey.touches_facts_for(ctx)
        assert not any(f.dst == other for f in facts), (clearance, name, facts)


def test_touches_fires_for_an_add_pushed_back_against_that_same_wall():
    """The contrast that keeps the test above from passing vacuously: the same shelf, moved flush
    against the room's -X wall, IS a contact -- and on the Subtract's own carve boundary."""
    pytest.importorskip("uedcli_native")
    sc = scen.an_add_inside_an_enclosing_subtract(0)
    ctx = actor_survey.build_context(sc.level, sc.index, "Shelf", sc.defaults)
    facts = actor_survey.touches_facts_for(ctx)
    assert any(f.src == "Shelf" and f.dst == "Room" for f in facts), facts


@pytest.mark.parametrize("offset, flush", [(0.0, True), (0.002, True), (0.010, True),
                                           (0.014, True), (0.016, False), (0.020, False),
                                           (0.050, False), (-0.002, True), (-0.010, True),
                                           (-0.016, False), (-0.050, False)])
def test_the_contact_tolerance_is_csg_tolerance(offset, flush):
    """The spec's 0.015uu, measured rather than asserted. `offset` is the gap (positive) or the
    overlap (negative) between two butted Adds.

    A gap is decided exactly at `CSG_TOLERANCE` by `_cell_slice`'s span test. An overlap is decided
    by the probe points, which sit `CSG_TOLERANCE` off the plane, so its boundary is
    `CSG_TOLERANCE` less `actorgraph._VERTEX_EPS` (1e-3) -- the authored-geometry noise floor
    `point_in_brush` itself carries, not a second tolerance of this relation's own."""
    pytest.importorskip("uedcli_native")
    sc = scen.two_adds_butted_face_to_face(offset)
    ctx = actor_survey.build_context(sc.level, sc.index, "BlockA", sc.defaults)
    got = actor_survey.pair_touches(ctx, ctx.level.actors["BlockA"], ctx.level.actors["BlockB"])
    assert got is flush


@pytest.mark.parametrize("constant, tracks", [("CSG_TOLERANCE", True), ("_SIDE_PROBE_STEP", False)])
def test_only_csg_tolerance_moves_the_contact_boundary(monkeypatch, constant, tracks):
    """Round 4 and round 5 each asserted the tolerance was `CSG_TOLERANCE` and each shipped a
    predicate whose real boundary was `_SIDE_PROBE_STEP` (0.05uu). Checking that the constant is
    referenced somewhere does not catch that; moving it and watching the answer does. A 0.03uu gap
    is rejected at the shipped tolerance and must become a touch when only `CSG_TOLERANCE` is
    widened past it."""
    pytest.importorskip("uedcli_native")
    monkeypatch.setattr(actor_survey, constant, 0.05)
    sc = scen.two_adds_butted_face_to_face(0.03)
    ctx = actor_survey.build_context(sc.level, sc.index, "BlockA", sc.defaults)
    got = actor_survey.pair_touches(ctx, ctx.level.actors["BlockA"], ctx.level.actors["BlockB"])
    assert got is tracks


def test_a_contact_region_with_no_area_is_not_a_touch():
    """Two rooms carved side by side have four pairs of coplanar walls that meet along a shared
    EDGE and nowhere else. The region test is what rejects those -- the intersection of the two
    cross-sections is a zero-area sliver -- and it is the reason a plane-coincidence test alone
    fires on a contact 100uu from anything the pair shares."""
    pytest.importorskip("uedcli_native")
    sc = scen.two_rooms_side_by_side()
    ctx = actor_survey.build_context(sc.level, sc.index, "RoomA", sc.defaults)
    a, b = ctx.level.actors["RoomA"], ctx.level.actors["RoomB"]
    plane = ((0.0, 1.0, 0.0), 100.0)                     # RoomA's +Y wall == RoomB's +Y wall
    assert plane in actor_survey.contact_planes(ctx, a, b)
    region = relation._clip_2d(
        relation._ensure_ccw(actor_survey.plane_slices(ctx, a, *plane)[0]),
        relation._ensure_ccw(actor_survey.plane_slices(ctx, b, *plane)[0]))
    assert relation._shoelace_area(region) == 0.0


def test_touches_does_not_fire_against_a_subtract_that_carved_nothing():
    """A Subtract's authored plane is not a surface unless its carve actually made one. `Ghost`
    sits entirely in space `Outer` had already emptied, so it removes nothing anywhere, and the
    crate butted flush against its boundary is resting against nothing at all."""
    pytest.importorskip("uedcli_native")
    sc = scen.a_subtract_that_carves_nothing()
    ctx = actor_survey.build_context(sc.level, sc.index, "Ghost", sc.defaults)
    assert [f for f in ctx.probe.world_surfaces
            if f.actor is not None and f.actor.name == "Ghost"] == []
    ghost = ctx.level.actors["Ghost"]
    assert actor_survey._was_solid_before(ctx, ghost, (0.015, 0, 0)) is False
    for name, other in (("Crate", "Ghost"), ("Ghost", "Crate")):
        ctx = actor_survey.build_context(sc.level, sc.index, name, sc.defaults)
        facts = actor_survey.touches_facts_for(ctx)
        assert not any(f.dst == other for f in facts), (name, facts)


def test_touches_does_not_fire_against_an_oversized_corridors_phantom_end():
    """The spec calls the idiom routine: a corridor is run PAST the room it opens into so its end
    plane does not land on the room's wall. That end plane is inside space the room already
    emptied, so the corridor made no surface there -- the crate resting against it, hundreds of uu
    from anything the corridor removed, is not a contact.

    The corridor's REAL carve boundary, out in the rock, is a contact and must stay one: without
    that half this test passes for the wrong reason."""
    pytest.importorskip("uedcli_native")
    sc = scen.an_oversized_corridor_past_its_room()
    for name, other in (("Crate", "Corridor"), ("Corridor", "Crate")):
        ctx = actor_survey.build_context(sc.level, sc.index, name, sc.defaults)
        facts = actor_survey.touches_facts_for(ctx)
        assert not any(f.dst == other for f in facts), (name, facts)
    ctx = actor_survey.build_context(sc.level, sc.index, "Corridor", sc.defaults)
    corridor, rock = ctx.level.actors["Corridor"], ctx.level.actors["Rock"]
    assert actor_survey._was_solid_before(ctx, corridor, (-448.015, 0, 0)) is False  # in the room
    assert actor_survey._was_solid_before(ctx, corridor, (-1000, 0, 0)) is True      # in the rock
    assert actor_survey.pair_touches(ctx, corridor, rock)


def test_touches_fires_across_a_wall_seam_a_doorway_is_cut_through():
    """Two butted Adds with a door cut through the join -- about as ordinary as level geometry
    gets. They still meet over the whole seam above the doorway, but the centre of that contact
    region is inside the doorway, so probing the region once, at its centroid, reports nothing."""
    pytest.importorskip("uedcli_native")
    sc = scen.a_doorway_through_a_wall_seam()
    for name, other in (("WallA", "WallB"), ("WallB", "WallA")):
        ctx = actor_survey.build_context(sc.level, sc.index, name, sc.defaults)
        facts = actor_survey.touches_facts_for(ctx)
        assert any(f.src == name and f.dst == other for f in facts), (name, facts)
    ctx = actor_survey.build_context(sc.level, sc.index, "WallA", sc.defaults)
    a, b = ctx.level.actors["WallA"], ctx.level.actors["WallB"]
    assert actor_survey._contact_at(ctx, a, b, (-0.015, 0, 0), (0.015, 0, 0)) is False  # the centre
    assert actor_survey.pair_touches(ctx, a, b)                                         # the seam


@pytest.mark.parametrize("degrees", [0, 17, 30, 45])
def test_two_cubes_meeting_at_one_edge_never_touch(degrees):
    """An edge is not a contact. Unrotated the two footprints cancel to exactly 0.0 area; rotated
    they cancel to float dust (1.9e-13 uu^2 at 30 degrees), which an exact `== 0` test reads as a
    real region and reports a touch. Rotated content is ordinary, which is why the area threshold
    has to be a tolerance -- `CSG_TOLERANCE` squared, the finest area the resolved model can tell
    from a line."""
    pytest.importorskip("uedcli_native")
    sc = scen.two_cubes_meeting_at_one_edge(degrees)
    ctx = actor_survey.build_context(sc.level, sc.index, "PrismA", sc.defaults)
    a, b = ctx.level.actors["PrismA"], ctx.level.actors["PrismB"]
    assert actor_survey.pair_touches(ctx, a, b) is False
    assert actor_survey.touches_facts_for(ctx) == []


@pytest.mark.parametrize("degrees", [0, 17, 30, 45])
def test_two_rotated_cubes_face_to_face_do_touch(degrees):
    """The contrast, so the test above cannot pass by rejecting every rotated pair: the same two
    cubes butted over a full 100x100 face are a contact at every angle.

    Asserted on `pair_touches`, not on `touches_facts_for`, and that is a finding rather than a
    convenience: at 17 and 30 degrees `crosses` reports a 100uu penetration between two cubes that
    only touch, and the mutual-exclusivity rule then drops the real fact. That is
    `penetration_depth`'s own documented rotated-source limit, which its docstring asks to have
    REPORTED if a rotated case ever turned up -- board item
    `crosses-over-reports-depth-for-a-rotated-source`."""
    pytest.importorskip("uedcli_native")
    sc = scen.two_cubes_face_to_face(degrees)
    ctx = actor_survey.build_context(sc.level, sc.index, "PrismA", sc.defaults)
    a, b = ctx.level.actors["PrismA"], ctx.level.actors["PrismB"]
    assert actor_survey.pair_touches(ctx, a, b) is True


# --------------------------------------------------------------------- Task 14: connects

def test_connects_fires_for_two_subtracts_sharing_a_plane_and_touches_does_not():
    """The spec's key disambiguation. Two Subtracts sharing a coincident plane leave no surviving
    solid face between them, so there is nothing to be flush against — it can only be `connects`."""
    pytest.importorskip("uedcli_native")
    sc = scen.two_rooms_sharing_a_plane()
    ctx = actor_survey.build_context(sc.level, sc.index, "RoomA", sc.defaults)
    assert any(f.src == "RoomA" and f.dst == "RoomB" and f.relation == "connects"
               for f in actor_survey.connects_facts_for(ctx))
    assert not any(f.dst == "RoomB" for f in actor_survey.touches_facts_for(ctx))


def test_connects_does_not_fire_across_an_intact_wall():
    pytest.importorskip("uedcli_native")
    sc = scen.two_rooms_split_by_an_intact_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "RoomA", sc.defaults)
    assert not any(f.dst == "RoomB" for f in actor_survey.connects_facts_for(ctx))


def test_connects_fires_for_a_fully_nested_redundant_subtract():
    pytest.importorskip("uedcli_native")
    sc = scen.redundant_nested_subtract()
    ctx = actor_survey.build_context(sc.level, sc.index, "OuterRoom", sc.defaults)
    assert any(f.dst == "InnerCarve" and f.relation == "connects"
               for f in actor_survey.connects_facts_for(ctx))


def test_connects_is_subtract_only():
    pytest.importorskip("uedcli_native")
    sc = scen.two_rooms_sharing_a_plane()
    ctx = actor_survey.build_context(sc.level, sc.index, "Shell", sc.defaults)
    assert actor_survey.connects_facts_for(ctx) == []


def test_connects_reads_no_zone_number():
    """The zone flood is a whole-model pass, so zone numbers are not reproducible under a truncated
    solve (spike.md §4 residual 3). No survey relation may read one."""
    import inspect
    src = inspect.getsource(actor_survey.connects_facts_for) + \
        inspect.getsource(actor_survey.voids_meet)
    assert "zone" not in src.lower()


def test_connects_fires_for_two_previously_tested_side_by_side_rooms():
    """`two_rooms_side_by_side` (Task 13) already pins that this shape is `connects, never touches`
    on the `touches` side; this pins the positive half on the same fixture."""
    pytest.importorskip("uedcli_native")
    sc = scen.two_rooms_side_by_side()
    for name, other in (("RoomA", "RoomB"), ("RoomB", "RoomA")):
        ctx = actor_survey.build_context(sc.level, sc.index, name, sc.defaults)
        assert any(f.dst == other and f.relation == "connects"
                   for f in actor_survey.connects_facts_for(ctx)), (name, ctx)


def test_connects_fires_for_two_voids_meeting_on_a_subtracts_plane():
    """`pillar_in_room`'s `Room`/`Cutter` pair: `touches` already refuses this (both are Subtracts
    meeting past the pillar, no solid nearby); `connects` must be the relation that DOES fire."""
    pytest.importorskip("uedcli_native")
    sc = scen.pillar_in_room()
    for name, other in (("Room", "Cutter"), ("Cutter", "Room")):
        ctx = actor_survey.build_context(sc.level, sc.index, name, sc.defaults)
        assert any(f.dst == other and f.relation == "connects"
                   for f in actor_survey.connects_facts_for(ctx)), (name, ctx)


@pytest.mark.parametrize("degrees", [0, 17, 30, 45])
def test_connects_fires_for_two_rotated_subtracts_sharing_a_plane(degrees):
    """Two Subtract prisms sharing a face, symmetric about the rotation origin, must still connect
    at every angle. Kept as a baseline, but NOT the rotated regression on its own -- a grid-based
    predicate can pass this exact fixture by construction (the grid always lands on the box centre,
    which happens to be the seam here) while missing a real, off-centre rotated seam entirely; see
    `test_connects_fires_for_an_asymmetric_off_centre_rotated_seam` below for that case."""
    pytest.importorskip("uedcli_native")
    sc = scen._scenario([
        scen.brush("Shell", (4096, 4096, 4096), (0, 0, 0)),
        scen._as_subtract(scen._rotated_brush("PrismA", (100, 100, 100), (-50, 0), degrees)),
        scen._as_subtract(scen._rotated_brush("PrismB", (100, 100, 100), (50, 0), degrees)),
    ])
    ctx = actor_survey.build_context(sc.level, sc.index, "PrismA", sc.defaults)
    assert any(f.dst == "PrismB" and f.relation == "connects"
               for f in actor_survey.connects_facts_for(ctx))


@pytest.mark.parametrize("degrees", [0, 17, 30, 45])
def test_connects_fires_for_an_asymmetric_off_centre_rotated_seam(degrees):
    """Critical review finding: a grid-sampling predicate found 0/125 samples on a real seam here
    (15/15 real seam points genuinely lie in both brushes) at every non-zero angle, because the
    fixture is deliberately NOT symmetric about the rotation origin -- unequal room sizes, the seam
    itself offset from both rooms' centres. `_planar_void_contact`'s real geometric intersection
    (mirroring `pair_touches`) must find this regardless of rotation, since it never samples a fixed
    grid at all."""
    pytest.importorskip("uedcli_native")
    sc = scen.two_rotated_subtracts_meeting_off_centre(degrees)
    ctx = actor_survey.build_context(sc.level, sc.index, "RoomA", sc.defaults)
    assert any(f.dst == "RoomB" and f.relation == "connects"
               for f in actor_survey.connects_facts_for(ctx))


@pytest.mark.parametrize("degrees", [0, 17, 30, 45])
def test_connects_never_fires_for_an_edge_or_corner_only_meeting(degrees):
    """Critical review finding: the prior grid-sampling `voids_meet` fired `connects` for two
    Subtracts meeting only at a shared edge -- `two_cubes_meeting_at_one_edge`'s own docstring says
    "an edge is not a contact", and `touches` already rejects the identical shape for Add/Add via
    `_MIN_CONTACT_AREA`. `connects` must reject it the same way, at every rotation."""
    pytest.importorskip("uedcli_native")
    sc = scen.two_subtracts_meeting_at_one_edge(degrees)
    ctx = actor_survey.build_context(sc.level, sc.index, "PrismA", sc.defaults)
    assert actor_survey.connects_facts_for(ctx) == []


def test_connects_does_not_treat_a_mover_as_a_subtract():
    """Critical review finding: `query.csg_is_subtract` reads only the raw `CsgOper` prop, so a
    Mover carrying a stray `CsgOper=CSG_Subtract` (never emitted by any builder, but not forbidden
    on an imported actor block) was wrongly accepted on both sides of `connects`'s gate. `_kind`
    must reject it via the actor's real kind (`mover`, from `movers.is_mover`'s class-ancestry
    check), matching every other csg-tier eligibility gate in this module."""
    pytest.importorskip("uedcli_native")
    sc = scen.mover_wrongly_tagged_as_subtract()
    ctx = actor_survey.build_context(sc.level, sc.index, "Room", sc.defaults)
    assert actor_survey.connects_facts_for(ctx) == []
    ctx = actor_survey.build_context(sc.level, sc.index, "Door", sc.defaults)
    assert actor_survey.connects_facts_for(ctx) == []


def test_connects_propagates_on_a_degenerate_surveyed_subtract(monkeypatch):
    """`raw_facts_for`'s own rule, reused here: a degenerate SURVEYED brush propagates (a
    single-actor report has nothing left to say); only a degenerate NEIGHBOUR is skipped (next
    test). Forced via monkeypatch rather than a genuinely malformed brush, so the native CSG solve
    inside `build_context` (a separate, Rust-side concern) cannot confound what this pins."""
    pytest.importorskip("uedcli_native")
    from uedcli import actorgraph as actorgraph_mod
    sc = scen.two_rooms_sharing_a_plane()
    ctx = actor_survey.build_context(sc.level, sc.index, "RoomA", sc.defaults)
    real_decompose = actorgraph_mod.decompose_convex

    def boom(actor, *, cache=None):
        if actor.name == "RoomA":
            raise actorgraph_mod.DegenerateBrushError("RoomA: forced for the test")
        return real_decompose(actor, cache=cache)

    monkeypatch.setattr(actor_survey.actorgraph, "decompose_convex", boom)
    with pytest.raises(actorgraph_mod.DegenerateBrushError):
        actor_survey.connects_facts_for(ctx)


def test_connects_skips_a_degenerate_neighbour_subtract(monkeypatch):
    """The contrast: a degenerate NEIGHBOUR (not the surveyed actor) is silently skipped, matching
    the raw tier and every other csg-tier neighbour-skip in this module."""
    pytest.importorskip("uedcli_native")
    from uedcli import actorgraph as actorgraph_mod
    sc = scen.two_rooms_sharing_a_plane()
    ctx = actor_survey.build_context(sc.level, sc.index, "RoomA", sc.defaults)
    real_decompose = actorgraph_mod.decompose_convex

    def boom(actor, *, cache=None):
        if actor.name == "RoomB":
            raise actorgraph_mod.DegenerateBrushError("RoomB: forced for the test")
        return real_decompose(actor, cache=cache)

    monkeypatch.setattr(actor_survey.actorgraph, "decompose_convex", boom)
    assert actor_survey.connects_facts_for(ctx) == []


def test_shared_region_is_none_when_the_actors_do_not_meet():
    pytest.importorskip("uedcli_native")
    sc = scen.far_apart_rooms()
    ctx = actor_survey.build_context(sc.level, sc.index, "FarRoom", sc.defaults)
    a, b = ctx.level.actors["FarRoom"], ctx.level.actors["Distant"]
    assert actor_survey.shared_region(ctx, a, b) is None


def test_shared_region_is_a_zero_thickness_slab_for_a_shared_plane():
    pytest.importorskip("uedcli_native")
    sc = scen.two_rooms_sharing_a_plane()
    ctx = actor_survey.build_context(sc.level, sc.index, "RoomA", sc.defaults)
    a, b = ctx.level.actors["RoomA"], ctx.level.actors["RoomB"]
    lo, hi = actor_survey.shared_region(ctx, a, b)
    assert lo[0] == pytest.approx(-actor_survey.CSG_TOLERANCE)
    assert hi[0] == pytest.approx(actor_survey.CSG_TOLERANCE)


def test_shared_region_uses_the_cells_agreeing_bounds_helper_not_writes_actor_bounds():
    """Important review finding: `_brush_bounds` (the module's own memoized, cells-agreeing AABB),
    never `writes.actor_bounds` -- that function's own docstring already names this exact trap
    ("this has to compare against float probe points and must agree with the cells `point_in_brush`
    itself tests"). Pinned by recomputing the expected box the same way and comparing directly,
    rather than trusting an unobservable implementation detail."""
    pytest.importorskip("uedcli_native")
    sc = scen.two_rooms_sharing_a_plane()
    ctx = actor_survey.build_context(sc.level, sc.index, "RoomA", sc.defaults)
    a, b = ctx.level.actors["RoomA"], ctx.level.actors["RoomB"]
    a_lo, a_hi = actor_survey._brush_bounds(ctx, a)
    b_lo, b_hi = actor_survey._brush_bounds(ctx, b)
    expected_lo = tuple(max(a_lo[i], b_lo[i]) - actor_survey.CSG_TOLERANCE for i in range(3))
    expected_hi = tuple(min(a_hi[i], b_hi[i]) + actor_survey.CSG_TOLERANCE for i in range(3))
    lo, hi = actor_survey.shared_region(ctx, a, b)
    assert lo == expected_lo
    assert hi == expected_hi


# --------------------------------------------------------------------- Task 14 round 3

@pytest.mark.parametrize("degrees", [0, 17, 30, 45])
def test_pair_touches_fires_for_differently_sized_rotated_adds_sharing_a_plane(degrees):
    """Critical review finding: the shared `_cell_slice`/`contact_planes` tolerance mismatch this
    task's own `connects` work uncovered was ALREADY LIVE in shipped `touches` -- a real, ordinary
    28000 uu^2 flush contact between two DIFFERENTLY-SIZED rotated Adds was silently missed at 17
    and 30 degrees (not 0/45, where the trig happens to cancel exactly), because `pair_touches` fed
    ONE actor's own plane to the OTHER's `plane_slices`, and `_cell_slice`'s near-parallel-face skip
    is tuned tighter than the rotation noise between two independently-computed planes. Fixed by
    `_self_consistent_plane`/`_reproject_uv`, shared verbatim with `connects`'s own identical fix.

    Asserted on `pair_touches`, not `touches_facts_for` -- the same reason
    `test_two_rotated_cubes_face_to_face_do_touch` already gives: at these angles `crosses`
    over-reports depth for this rotated, differently-sized pair (the ALREADY-FILED, out-of-scope
    `crosses-over-reports-depth-for-a-rotated-source`), and the mutual-exclusivity rule then drops
    the real touches fact -- a separate, pre-existing bug this task does not touch."""
    pytest.importorskip("uedcli_native")
    sc = scen.two_adds_meeting_off_centre(degrees)
    ctx = actor_survey.build_context(sc.level, sc.index, "RoomA", sc.defaults)
    a, b = ctx.level.actors["RoomA"], ctx.level.actors["RoomB"]
    assert actor_survey.pair_touches(ctx, a, b) is True


def test_connects_fires_for_a_partial_merge_well_under_half_extent():
    """Critical review finding: the round-2 fix's own `_volume_void_overlap` (a per-cell CENTROID
    containment test) only fired when the shared volume covered roughly half of one room's own
    extent -- a real 100 x 280 x 200 uu^3 overlap well under that fraction (independently verified
    void on both sides) produced no fact at any depth below half. Fixed by unifying the volume and
    planar cases into one real-geometric-intersection mechanism (`_planar_void_contact`, now driven
    by `contact_planes`' full either-side candidate set rather than a mutual-coincidence-only
    subset) -- sound because a positive-volume intersection of two convex bodies always has at
    least one real boundary facet on one of the two bodies' own defining planes."""
    pytest.importorskip("uedcli_native")
    sc = scen.partial_merge_below_half_extent()
    ctx = actor_survey.build_context(sc.level, sc.index, "RoomA", sc.defaults)
    assert any(f.dst == "RoomB" and f.relation == "connects"
               for f in actor_survey.connects_facts_for(ctx))
    ctx = actor_survey.build_context(sc.level, sc.index, "RoomB", sc.defaults)
    assert any(f.dst == "RoomA" and f.relation == "connects"
               for f in actor_survey.connects_facts_for(ctx))


def test_connects_finds_a_real_opening_off_the_old_probe_cross():
    """Critical review finding: `_region_probes`' fixed 5-point fan (centroid + one point per edge --
    tuned for `touches`' different question) can walk right past a real, ordinary-sized doorway that
    doesn't happen to sit under one of those 5 specific points -- POSITION-dependent, not just
    size-dependent. Fixed with `_region_grid_probes`, a denser grid scoped to the real clipped
    region (not `touches`' own `_region_probes`, left untouched). Confirmed by direct comparison
    against the old 5-point fan on this exact fixture (see the task report for the before/after)."""
    pytest.importorskip("uedcli_native")
    sc = scen.doorway_off_the_probe_cross()
    ctx = actor_survey.build_context(sc.level, sc.index, "RoomA", sc.defaults)
    assert any(f.dst == "RoomB" and f.relation == "connects"
               for f in actor_survey.connects_facts_for(ctx))


def test_region_grid_probes_never_samples_the_exact_boundary():
    """Regression for the bug the fix itself introduced first: a grid that DOES include the exact
    box edge lands a sample on a neighbouring actor's own boundary, where the solidity oracle's
    tie-break can misread solid as void (measured live: `two_rooms_split_by_an_intact_wall`'s
    region corner exactly matched the Wall's own corner and read void, firing `connects` across an
    intact wall). Every returned point must be strictly inside `(lo, hi)` on each axis, matching
    `_region_probes`' own "strictly interior" discipline."""
    region = [(-256.0, 256.0), (-256.0, -256.0), (256.0, -256.0), (256.0, 256.0)]
    for u, v in actor_survey._region_grid_probes(region):
        assert -256.0 < u < 256.0
        assert -256.0 < v < 256.0


def test_connects_still_rejects_an_edge_only_meeting_with_the_broader_candidate_set():
    """Guards against a regression the round-3 refactor could plausibly introduce: broadening the
    candidate planes from a mutual-coincidence-only subset to `contact_planes`' full either-side set
    (the round-2 -> round-3 change) must not reopen the edge/corner false positive round 2 fixed --
    `two_subtracts_meeting_at_one_edge` is the same fixture as before, now exercised against the
    unified mechanism."""
    pytest.importorskip("uedcli_native")
    sc = scen.two_subtracts_meeting_at_one_edge(17.0)
    ctx = actor_survey.build_context(sc.level, sc.index, "PrismA", sc.defaults)
    assert actor_survey.connects_facts_for(ctx) == []


# --------------------------------------------------------------------- Task 15: contains primitives

def test_cell_volume_of_a_cube_is_exact():
    from uedcli import actorgraph
    sc = scen.kind_table_scenario()
    cells = actorgraph.decompose_convex(sc.level.actors["Adder"])
    assert len(cells) == 1
    assert actor_survey.cell_volume(cells[0]) == pytest.approx(64.0 ** 3, rel=1e-6)


def test_authored_volume_sums_every_cell_of_a_non_convex_brush():
    """An L-shaped brush decomposes to 2+ cells; the authored volume is their sum, not one cell's.
    Geometry: the same L `test_actorgraph.py::_l_shaped_brush` builds -- a 128x128x64 footprint with
    the upper-right 64x64 quadrant missing, so 3/4 of 128*128*64."""
    from uedcli.tests.test_actorgraph import _l_shaped_brush
    a = _l_shaped_brush()
    assert actor_survey.authored_volume(a, {}) == pytest.approx(128 * 128 * 64 * 0.75, rel=1e-4)


def test_authored_volume_of_a_non_brush_actor_is_zero():
    """A point actor authors no volume, and so never competes to be a container (Task 16)."""
    a = scen.point("Lamp", (0, 0, 0))
    assert actor_survey.authored_volume(a, {}) == 0.0


def test_authored_shape_contains_a_point_actor_by_its_location():
    sc = scen.room_with_pillar_and_light()
    assert actor_survey.authored_shape_contains(sc.level.actors["Room"],
                                                sc.level.actors["Light"], {}) is True
    assert actor_survey.authored_shape_contains(sc.level.actors["Pillar"],
                                                sc.level.actors["Light"], {}) is False


def test_authored_shape_contains_a_brush_only_on_FULL_containment():
    """Strict full containment, deliberately (spec): a large Add that only PARTIALLY pokes out of a
    Subtract gets no csg `contains`, even though raw `contains` (touch-or-overlap) reports one.
    That is the stated cost of a strict predicate, not an oversight."""
    sc = scen.shelf_pokes_through_a_niche_wall()
    inside = sc.level.actors["Subtract3"]
    poking = sc.level.actors["Additive4"]
    assert actor_survey.authored_shape_contains(inside, poking, {}) is False
    small = scen.pillar_in_room()
    assert actor_survey.authored_shape_contains(small.level.actors["Room"],
                                                small.level.actors["Pillar"], {}) is True


def test_authored_shape_contains_uses_the_actors_own_authored_shape_not_its_aabb():
    """An L-shaped container must not claim something sitting in its notch."""
    from uedcli.model import Actor, Level
    from uedcli.tests.test_actorgraph import _l_shaped_brush
    from decimal import Decimal
    container = _l_shaped_brush()
    in_notch = Actor(name="Notch", cls="Engine.Light",
                     location=tuple(Decimal(str(c)) for c in (96, 96, 0)))
    in_arm = Actor(name="Arm", cls="Engine.Light",
                   location=tuple(Decimal(str(c)) for c in (32, 32, 0)))
    del Level
    assert actor_survey.authored_shape_contains(container, in_notch, {}) is False
    assert actor_survey.authored_shape_contains(container, in_arm, {}) is True


def test_authored_shape_contains_target_with_no_brush_and_no_location_is_false():
    """No Location and no brush means no known extent at all -- never fabricate one."""
    from uedcli.model import Actor
    sc = scen.room_with_pillar_and_light()
    ghost = Actor(name="Ghost", cls="Engine.Light", location=None)
    assert actor_survey.authored_shape_contains(sc.level.actors["Room"], ghost, {}) is False


# ------------------------------------------------- adversarial: rotation, exact shape vs AABB

def test_cell_volume_is_orientation_independent():
    """A cube's volume must not change when it's rotated -- pins `_order_around`'s face
    triangulation against a normal that isn't axis-aligned, not just the axis-aligned box every
    other cell_volume test exercises."""
    from uedcli import actorgraph
    rotated = scen._rotated_brush("Spun", (64, 64, 64), (0, 0), 23.0)
    cells = actorgraph.decompose_convex(rotated)
    assert len(cells) == 1
    assert actor_survey.cell_volume(cells[0]) == pytest.approx(64.0 ** 3, rel=1e-6)


def test_authored_shape_contains_tests_the_true_rotated_shape_not_its_aabb():
    """A rotated box's AABB is bigger than the box itself (the corners stick out past every face).
    Two points chosen to be inside/outside the TRUE rotated box while both sitting well inside its
    AABB -- a container test that quietly fell back to an AABB would wrongly accept both."""
    import math
    theta = math.radians(25.0)
    container = scen._rotated_brush("Spun", (200, 200, 200), (0, 0), 25.0)
    # local (99, 0, 0) -- just inside the box's local +X face (half-extent 100) -- rotated to world.
    just_inside = (99.0 * math.cos(theta), 99.0 * math.sin(theta), 0.0)
    # local (101, 0, 0) -- just past that same face -- still well inside the box's AABB (whose
    # half-extent along any world axis is ~132.9 for a 200-cube at 25 degrees).
    just_outside = (101.0 * math.cos(theta), 101.0 * math.sin(theta), 0.0)
    inside_actor = scen.point("Inside", just_inside)
    outside_actor = scen.point("Outside", just_outside)
    assert actor_survey.authored_shape_contains(container, inside_actor, {}) is True
    assert actor_survey.authored_shape_contains(container, outside_actor, {}) is False


def test_authored_shape_contains_rejects_a_target_poking_out_by_a_single_vertex():
    """Strict full containment must reject on ANY one vertex outside, not merely most of them --
    the case a majority/centroid-based test would wrongly accept. A 64-cube target sits fully
    inside a 512-cube container except its +X face, pushed 4uu past the container's own +X wall."""
    container = scen.brush("Room", (512, 512, 512), (0, 0, 0))
    poking = scen.brush("Poker", (64, 64, 64), (252, 0, 0))  # +X extent = 284, wall at x=256
    assert actor_survey.authored_shape_contains(container, poking, {}) is False
    flush_inside = scen.brush("Flush", (64, 64, 64), (220, 0, 0))  # +X extent = 252 < 256
    assert actor_survey.authored_shape_contains(container, flush_inside, {}) is True


def test_authored_shape_contains_rejects_a_beam_whose_corners_sit_in_an_l_shaped_containers_two_arms():
    """Critical review finding, round 2: vertex-only containment is NECESSARY but not SUFFICIENT for
    a non-convex container. `_l_shaped_brush` is two rectangular arms (x in [0,128] y in [0,64], and
    x in [0,64] y in [64,128]) sharing a reentrant corner at (64,64); the missing upper-right
    quadrant (x,z in [64,128]) is the notch. This target is a thin diagonal beam whose 8 corners
    (4 in-plane corners x 2 Z levels) each sit safely inside one arm or the other -- EVERY corner
    individually passes `point_in_brush` -- while the beam's own middle cuts straight through the
    notch. A vertex-only test (the pre-round-2 implementation) reports this contained; the real
    volume-coverage test must not."""
    from uedcli import actorgraph, builders
    from uedcli.builders import cube, make_brush_actor
    from uedcli.tests.test_actorgraph import _l_shaped_brush
    import math
    container = _l_shaped_brush()
    p1, p2 = (110.0, 50.0), (50.0, 110.0)          # both safely inside the L's two arms
    mid = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2, 0.0)
    length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    angle_deg = math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0]))
    beam = builders._rotate_z(cube(length, 8.0, 16.0), angle_deg)
    target = make_brush_actor("Beam", beam, location=tuple(Decimal(str(c)) for c in mid))

    cells = actorgraph.decompose_convex(target)
    assert len(cells) == 1
    # Every one of the beam's own 8 corners individually passes -- the vertex-only test's own
    # necessary condition holds, so a vertex-only implementation would (wrongly) call this contained.
    for v in cells[0].vertices:
        assert actorgraph.point_in_brush(container, v) is True

    # But a real fraction of the beam's own volume -- ~53% of its length runs through the notch --
    # is NOT covered by either of the container's two arms.
    covered = sum(actor_survey._cell_intersection_volume(cells[0], cc)
                  for cc in actorgraph.decompose_convex(container))
    tc_volume = actor_survey.cell_volume(cells[0])
    assert covered / tc_volume == pytest.approx(0.4667, abs=0.01)

    assert actor_survey.authored_shape_contains(container, target, {}) is False


# ------------------------------------------------------------------ Task 16: contains

def test_contains_is_uncontested_when_the_only_other_candidate_is_an_add():
    """The pillar case: a later Add pillar inside a room never enters the competition -- it is not a
    Subtract -- so the room wins uncontested and the light is contained regardless of the pillar."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.room_with_pillar_and_light()
    ctx = actor_survey.build_context(sc.level, sc.index, "Room", sc.defaults)
    assert any(f.src == "Room" and f.dst == "Light" and f.relation == "contains"
               for f in actor_survey.contains_facts_for(ctx))


def test_contains_picks_the_smallest_authored_volume_when_nested():
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.nested_niche_with_a_decoration()
    inner = actor_survey.build_context(sc.level, sc.index, "Subtract3", sc.defaults)
    outer = actor_survey.build_context(sc.level, sc.index, "Subtract1", sc.defaults)
    assert any(f.src == "Subtract3" and f.dst == "Additive4"
               for f in actor_survey.contains_facts_for(inner))
    assert not any(f.dst == "Additive4" for f in actor_survey.contains_facts_for(outer))


def test_contains_breaks_an_exact_volume_tie_toward_the_later_brush():
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.two_equal_volume_subtracts()
    later = actor_survey.build_context(sc.level, sc.index, "LaterRoom", sc.defaults)
    earlier = actor_survey.build_context(sc.level, sc.index, "EarlierRoom", sc.defaults)
    assert any(f.src == "LaterRoom" and f.dst == "Item"
               for f in actor_survey.contains_facts_for(later))
    assert not any(f.dst == "Item" for f in actor_survey.contains_facts_for(earlier))


def test_contains_shows_the_same_fact_when_the_contained_actor_is_surveyed():
    """Fixed-direction: the container leads whichever side you ask about."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.room_with_pillar_and_light()
    ctx = actor_survey.build_context(sc.level, sc.index, "Light", sc.defaults)
    assert any(f.src == "Room" and f.dst == "Light"
               for f in actor_survey.contains_facts_for(ctx))


def test_contains_never_has_an_intersect_or_deintersect_as_the_container():
    """They contribute nothing to the world at all, so they can never be the container side."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.kind_table_scenario()
    ctx = actor_survey.build_context(sc.level, sc.index, "Lamp", sc.defaults)
    assert not any(f.src in ("Inter", "Deinter")
                   for f in actor_survey.contains_facts_for(ctx))


def test_contains_does_not_treat_a_mover_as_a_subtract():
    """The same trap `test_connects_does_not_treat_a_mover_as_a_subtract` already pins for `connects`
    (critical review finding there): `query.csg_is_subtract` reads only the raw `CsgOper` prop, so a
    Mover carrying a stray `CsgOper=CSG_Subtract` would wrongly enter the container competition.
    `Door`'s authored volume here is far smaller than `Room`'s, so an ungated competition would have
    `Door` (wrongly) steal `Item` from `Room` -- `containment_winner`'s gate must go through the
    actor's real kind, not the raw prop, exactly like every other csg-tier eligibility gate in this
    module."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.mover_wrongly_tagged_as_subtract_competes_for_an_item()
    room_ctx = actor_survey.build_context(sc.level, sc.index, "Room", sc.defaults)
    assert any(f.src == "Room" and f.dst == "Item" for f in actor_survey.contains_facts_for(room_ctx))
    door_ctx = actor_survey.build_context(sc.level, sc.index, "Door", sc.defaults)
    assert not any(f.src == "Door" for f in actor_survey.contains_facts_for(door_ctx))


def test_volume_tolerance_is_a_named_constant_not_an_inline_literal():
    import inspect
    assert actor_survey.VOLUME_TOLERANCE_REL == 1e-6
    assert "1e-6" not in inspect.getsource(actor_survey.containment_winner)


def test_carves_fires_when_a_subtract_removes_real_add_matter():
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.niche_carved_into_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Niche", sc.defaults)
    assert any(f.src == "Niche" and f.dst == "Wall" and f.relation == "carves"
               for f in actor_survey.carves_facts_for(ctx))


def test_carves_is_absent_where_the_subtract_only_stopped_flush():
    """The raw-vs-csg contrast the whole two-tier design exists for: the raw order heuristic calls
    this pair `carves` (the Subtract is later in trunk order); the csg tier correctly reports
    nothing against `Wall`, and reports `touches` instead. `Room` separately carves `Rock` (total
    removal, per spec) -- that fact is legitimate and out of scope for this test."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.subtract_stops_flush_against_a_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Room", sc.defaults)
    assert not any(f.dst == "Wall" for f in actor_survey.carves_facts_for(ctx))
    assert any(f.dst == "Wall" for f in actor_survey.touches_facts_for(ctx))
    raw = actor_survey.raw_facts_for(sc.level, sc.index, "Room", sc.defaults).facts
    assert any(f.relation == "carves" for f in raw), "raw's heuristic really does claim it"


def test_carves_never_targets_a_semisolid():
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.semisolid_pillar_straddled_by_a_subtract()
    ctx = actor_survey.build_context(sc.level, sc.index, "Cutter", sc.defaults)
    assert not any(f.dst == "Pillar" for f in actor_survey.carves_facts_for(ctx))


def test_carves_fires_for_total_removal_with_no_accompanying_touches():
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.partial_and_total_carves()
    ctx = actor_survey.build_context(sc.level, sc.index, "Eraser", sc.defaults)
    assert any(f.src == "Eraser" and f.dst == "Gone"
               for f in actor_survey.carves_facts_for(ctx))
    assert not any(f.dst == "Gone" for f in actor_survey.touches_facts_for(ctx))


def test_a_partially_overlapping_second_subtract_carves_and_connects():
    """The spec's coexistence case: `SecondCut` covers `FirstCut`'s already-carved region AND new
    matter, so it reports `carves Block` for the new part and `connects FirstCut` for the redundant
    part."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.partial_and_total_carves()
    ctx = actor_survey.build_context(sc.level, sc.index, "SecondCut", sc.defaults)
    assert any(f.dst == "Block" for f in actor_survey.carves_facts_for(ctx))
    assert any(f.dst == "FirstCut" for f in actor_survey.connects_facts_for(ctx))


def test_carves_shows_the_same_fact_when_the_carved_actor_is_surveyed():
    """Fixed-direction: the Subtract leads whichever side you ask about. The spec's own worked
    example surveys `Brush117`, the carved Add, and still prints the Subtract first."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.niche_carved_into_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Wall", sc.defaults)
    assert any(f.src == "Niche" and f.dst == "Wall"
               for f in actor_survey.carves_facts_for(ctx))


# --------------------------------------------------------------------- Task 18: survey() orchestration

def test_survey_returns_both_tiers_and_one_node_tag_per_named_actor():
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.niche_carved_into_wall()
    got = actor_survey.survey(sc.level, sc.index, "Wall", sc.defaults)
    assert got.raw and got.csg
    named = {f.src for f in got.raw} | {f.dst for f in got.raw} \
        | {f.src for f in got.csg} | {f.dst for f in got.csg}
    assert named <= set(got.nodes)


def test_csg_line_carries_a_depth_on_crosses_and_nothing_on_the_others():
    sc = scen.niche_carved_into_wall()
    nodes = actor_survey.raw_facts_for(sc.level, sc.index, "Wall", sc.defaults).nodes
    crossing = actor_survey.CsgFact(src="Wall", dst="Niche", relation="crosses", depth_uu=8.25)
    touching = actor_survey.CsgFact(src="Wall", dst="Niche", relation="touches")
    assert actor_survey.format_csg_line(crossing, nodes) == (
        "csg Wall [Engine.Brush Add] --crosses(8.25uu)--> Niche [Engine.Brush Subtract]")
    assert actor_survey.format_csg_line(touching, nodes) == (
        "csg Wall [Engine.Brush Add] --touches--> Niche [Engine.Brush Subtract]")


def test_no_csg_line_ever_carries_an_idx():
    """Cut from this tier entirely (spec): a `Name:idx` token is a promise of a pipeable selector,
    and the attribution mechanism for one was found factually wrong against the native code twice.
    Poly identity is also not reproducible under the bounded solve (spike.md §4 residual 1)."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.shelf_pokes_through_a_niche_wall()
    got = actor_survey.survey(sc.level, sc.index, "Additive4", sc.defaults)
    for fact in got.csg:
        line = actor_survey.format_csg_line(fact, got.nodes)
        assert ":" not in line.split("--")[0]


def test_survey_warns_only_when_the_surveyed_actor_is_an_intersect():
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.level_with_a_placed_intersect()
    assert "Inter" in actor_survey.survey(sc.level, sc.index, "Inter", sc.defaults).warning
    assert actor_survey.survey(sc.level, sc.index, "Room", sc.defaults).warning is None


def test_survey_propagates_a_degenerate_surveyed_brush():
    """`level graph` skips a bad brush and carries on over the rest of the level. A single-actor
    report has nothing left to say, so this propagates to the CLI's exit 2 instead."""
    import pytest
    from uedcli import actorgraph
    sc = scen.level_with_a_degenerate_brush()
    with pytest.raises(actorgraph.DegenerateBrushError):
        actor_survey.survey(sc.level, sc.index, "BadBrush", sc.defaults)
