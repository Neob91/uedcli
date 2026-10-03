"""`actor survey` — the bounded neighborhood, both tiers, and the CLI seam.

Fixtures live in `uedcli/tests/survey_scenarios.py`, one named builder per geometry, each returning
a `Scenario` so no test ever unpacks a tuple by arity.
"""
from __future__ import annotations

import dataclasses
from decimal import Decimal
from types import SimpleNamespace

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

def test_neighborhood_is_empty_for_a_level_with_no_brushes():
    from uedcli.model import Level
    lvl = Level(actors={"Light": scen.point("Light", (0, 0, 0))}, order=["Light"])
    out = actor_survey.neighborhood(lvl, scen.StubClassIndex(), lvl.actors["Light"], scen.stub_defaults())
    assert out == []


# ------------------------------------------------------------- Task 9: raw tier's pairwise relation

def test_raw_relation_reports_coincides_for_identical_brushes():
    s = scen.two_equal_volume_subtracts()
    cache: dict = {}
    rel = actor_survey.raw_relation_for("EarlierRoom", s.level.actors["EarlierRoom"],
                                        "LaterRoom", s.level.actors["LaterRoom"], cache)
    assert rel == ("EarlierRoom", "LaterRoom", "coincides")


def test_raw_relation_reports_encloses_with_the_container_leading():
    s = scen.room_with_pillar_and_light()
    cache: dict = {}
    rel = actor_survey.raw_relation_for("Pillar", s.level.actors["Pillar"],
                                        "Room", s.level.actors["Room"], cache)
    assert rel == ("Room", "Pillar", "encloses")


def test_raw_relation_reports_crosses_for_a_subtract_carving_its_add():
    """`raw:overlaps` renamed `raw:crosses` (spec) -- same mechanism, same fixture."""
    s = scen.niche_carved_into_wall()
    cache: dict = {}
    rel = actor_survey.raw_relation_for("Wall", s.level.actors["Wall"],
                                        "Niche", s.level.actors["Niche"], cache)
    assert rel == ("Wall", "Niche", "crosses")


def test_raw_relation_reports_touches_for_a_flush_contact():
    """`raw:meets` renamed `raw:touches` (spec) -- same mechanism, same fixture."""
    s = scen.two_adds_butted_face_to_face(offset=0.0)
    cache: dict = {}
    rel = actor_survey.raw_relation_for("BlockA", s.level.actors["BlockA"],
                                        "BlockB", s.level.actors["BlockB"], cache)
    assert rel == ("BlockA", "BlockB", "touches")


def test_raw_relation_is_none_for_disjoint_brushes():
    s = scen.far_apart_rooms()
    cache: dict = {}
    rel = actor_survey.raw_relation_for("FarRoom", s.level.actors["FarRoom"],
                                        "Distant", s.level.actors["Distant"], cache)
    assert rel is None


# ------------------------------------------------------------- Task 10: raw tier's `raw_facts_for`

def test_raw_tier_reports_encloses_for_a_subtract_around_an_add():
    s = scen.room_with_pillar_and_light()
    raw = actor_survey.raw_facts_for(s.level, s.index, "Room", s.defaults)
    assert any(f.src == "Room" and f.dst == "Light" and f.relation == "encloses"
               for f in raw.facts)


def test_raw_tier_never_reports_carves():
    s = scen.niche_carved_into_wall()
    raw = actor_survey.raw_facts_for(s.level, s.index, "Wall", s.defaults)
    assert not any(f.relation == "carves" for f in raw.facts)
    assert any(f.relation == "crosses" for f in raw.facts)


def test_raw_tier_leads_symmetric_relations_with_the_surveyed_actor():
    s = scen.two_adds_butted_face_to_face(offset=0.0)
    raw = actor_survey.raw_facts_for(s.level, s.index, "BlockB", s.defaults)
    fact = next(f for f in raw.facts if f.relation == "touches")
    assert fact.src == "BlockB"


def test_raw_tier_encloses_for_a_point_actor_names_the_container():
    s = scen.room_with_pillar_and_light()
    raw = actor_survey.raw_facts_for(s.level, s.index, "Light", s.defaults)
    assert raw.facts == [actor_survey.RawFact(src="Room", dst="Light", relation="encloses")]


def test_raw_facts_for_does_not_call_classify_pair(monkeypatch):
    from uedcli import actorgraph
    called = []
    monkeypatch.setattr(actorgraph, "classify_pair",
                        lambda *a, **k: called.append(1) or [])
    s = scen.niche_carved_into_wall()
    actor_survey.raw_facts_for(s.level, s.index, "Wall", s.defaults)
    assert not called


# ------------------------------------------------------------- Task 11: raw tier verification-only

def test_raw_line_shows_the_brush_kind_label():
    s = scen.niche_carved_into_wall()
    raw = actor_survey.raw_facts_for(s.level, s.index, "Wall", s.defaults)
    lines = [actor_survey.format_raw_line(f, raw.nodes) for f in raw.facts]
    assert any("[Engine.Brush Subtract]" in line for line in lines)


def test_raw_tier_never_reports_overlaps_meets_or_coincides_for_a_point_actor():
    s = scen.room_with_a_flush_mounted_prop()
    raw = actor_survey.raw_facts_for(s.level, s.index, "Room", s.defaults)
    point_relations = {f.relation for f in raw.facts if f.dst in ("Keypad", "Ghost", "Bracket")}
    assert point_relations <= {"encloses"}


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


def test_csg_faces_snaps_noisy_native_solve_output_before_deriving_the_face_plane():
    """Bug 1's REAL site: the live UNATCO false-positive (`Brush186`'s Y-extent computed as
    `576.000162` instead of `576.0`) came from `csg_faces` reading `surf.world_verts` straight off
    the native solve's own point pool, unsnapped -- not from `decompose_convex`, its sibling (already
    pinned by `test_actorgraph.test_decompose_convex_snaps_pre_existing_authored_float_noise`). Built
    directly against a synthetic `WorldProbe`/`SolvedSurface` carrying noisy verts (bypassing the
    native solve entirely, same shape of input a real solve hands `csg_faces`) so this pins the
    actual bug site rather than only the sibling function."""
    from uedcli.model import Actor
    from uedcli.preview_native import SolvedSurface, WorldProbe

    actor = Actor(name="Brush186", cls="Engine.Brush")
    noisy_z = 576.000162   # the real UNATCO repro's own noisy value, not a fresh magic number
    ring = [(0.0, 0.0, noisy_z), (512.0, 0.0, noisy_z),
            (512.0, 512.0, noisy_z), (0.0, 512.0, noisy_z)]
    probe = WorldProbe(world_surfaces=[SolvedSurface(actor=actor, poly_index=0, world_verts=ring,
                                                     poly_flags=0)],
                       solidity=None)
    region = ((-100.0, -100.0, 500.0), (600.0, 600.0, 600.0))

    faces = actor_survey.csg_faces(probe, region)

    assert len(faces) == 1
    face = faces[0]
    assert face.owner == "Brush186"
    assert face.offset == 576.0                        # not 576.000162
    assert all(v[2] == 576.0 for v in face.verts)       # the stored ring is snapped too


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


def test_touches_fires_for_a_carved_shelf_and_names_only_the_immediate_niche():
    """The spec's locality rule, now for `touches`: `Additive4`'s two surviving stubs sit flush
    against `Subtract3`'s own cut planes -- the immediate boundary that carved it -- and never
    against `Additive2`, however deep the nesting.

    `crosses` is NOT silent for this pair anymore, and that's correct under the redesigned spec
    (`dev/specs/commands/actor-survey.md`, csg:crosses): `Additive4` is authored BEFORE `Subtract3`,
    so at the moment `Additive4` is inserted, `Additive2`'s "resolved up until right before B" state
    is its own full, uncarved wall -- `Subtract3`'s niche doesn't exist yet. `Additive4` genuinely
    pierces that still-intact wall at that instant, so `crosses(Additive4, Additive2)` fires. That
    `Subtract3` immediately afterward erases both sides of the crossing (carving `Additive4`'s own
    matter there too) doesn't retroactively erase the fact -- `crosses` is deliberately an
    at-the-moment relation, not a final-resolved-world one (same tradeoff the spec accepts for
    `csg:carves`, and distinct from `csg:connects`, which the spec leaves pre-B-snapshot too).

    This test is the locality half, for `touches`: the relation that fires against the immediate
    carving boundary, never against the deeper nesting.

    Surveying `Additive4` alone would pass the touches-locality half even by accident:
    region-clipping keeps `Additive2`'s own faces out of `Additive4`'s survey region entirely.
    Surveying `Additive2` closes that gap: `Additive2`'s own faces ARE in-region there, and
    `Additive4`'s stubs sit entirely inside the hole `Subtract3` cut through `Additive2`, nowhere
    near `Additive2`'s own remaining ring -- so this is the case the immediate-owner attribution
    exists for, not a region-clipping accident."""
    pytest.importorskip("uedcli_native")
    sc = scen.shelf_pokes_through_a_niche_wall()

    ctx = actor_survey.build_context(sc.level, sc.index, "Additive4", sc.defaults)
    crosses = actor_survey.crosses_facts_for(ctx)
    assert any(f.src == "Additive4" and f.dst == "Additive2" for f in crosses)
    assert not any(f.dst == "Subtract3" for f in crosses), \
        "Subtract3 is never an eligible crosses source (csg:crosses's B kind list excludes Subtractive)"
    facts = actor_survey.touches_facts_for(ctx)
    assert any(f.src == "Additive4" and f.dst == "Subtract3" for f in facts)
    assert not any(f.dst == "Additive2" for f in facts)
    assert not any(f.src == "Additive2" and f.dst == "Additive4" for f in facts)

    ctx2 = actor_survey.build_context(sc.level, sc.index, "Additive2", sc.defaults)
    assert any(f.owner == "Additive2" for f in ctx2.faces), \
        "the real case: Additive2's own faces must be in-region for this to test anything"
    facts2 = actor_survey.touches_facts_for(ctx2)
    assert not any(f.src == "Additive4" and f.dst == "Additive2" for f in facts2)


def test_crosses_never_fires_from_a_subtract():
    """The design bug the source restriction exists to fix: without it, a Subtract room's raw shape
    trivially 'crosses' every Add placed inside it -- firing for every piece of furniture in every
    room."""
    pytest.importorskip("uedcli_native")
    sc = scen.pillar_in_room()
    ctx = actor_survey.build_context(sc.level, sc.index, "Room", sc.defaults)
    assert actor_survey.crosses_facts_for(ctx) == []


def test_crosses_uses_resolved_matter_not_authored_cells():
    s = scen.later_subtract_carves_an_add_that_encloses_a_semisolid()
    ctx = actor_survey.build_context(s.level, s.index, "Middle", s.defaults)
    facts = actor_survey.crosses_facts_for(ctx)
    assert not any(f.dst == "Enclosed" for f in facts), (
        "Middle's matter at Enclosed's location was carved away by Later; it must not report "
        "crosses against a carved-out void")


def test_crosses_fires_for_a_semisolid_partially_overlapping_an_add():
    """The suite's first genuine brush-sourced `crosses` -- a Semisolid's later, separate CSG pass
    never splits the underlying Add's face it overlaps (fixture's own docstring), so its matter
    genuinely pokes past it. Pinned so a future change to the semisolid CSG pass cannot silently
    break it; unaffected by Task 3's own fix (no Subtract in this fixture)."""
    pytest.importorskip("uedcli_native")
    sc = scen.semisolid_partially_overlapping_an_add()
    for surveyed in ("Spike", "B"):
        ctx = actor_survey.build_context(sc.level, sc.index, surveyed, sc.defaults)
        facts = actor_survey.crosses_facts_for(ctx)
        fact = next((f for f in facts if f.src == "Spike" and f.dst == "B"), None)
        assert fact is not None, f"surveying {surveyed}"


def test_crosses_direction_follows_loop_order_not_file_order():
    """A Semisolid authored BEFORE the Add it overlaps must still cross it, never the reverse --
    CSG ordering is LOOP membership (every world-pass brush, then every semisolid), not raw trunk
    position. Regression for exactly this: an earlier `_csg_order_position` compared raw file
    position, which this fixture's trunk order (`Spike` first, `B` second) inverts relative to
    real LOOP order, and wrongly produced `B --crosses--> Spike`."""
    pytest.importorskip("uedcli_native")
    sc = scen.semisolid_authored_before_the_add_it_overlaps()
    for surveyed in ("Spike", "B"):
        ctx = actor_survey.build_context(sc.level, sc.index, surveyed, sc.defaults)
        facts = actor_survey.crosses_facts_for(ctx)
        assert any(f.src == "Spike" and f.dst == "B" for f in facts), f"surveying {surveyed}"
        assert not any(f.src == "B" and f.dst == "Spike" for f in facts), f"surveying {surveyed}"


def test_crosses_does_not_fire_for_a_non_blocking_trigger_volume():
    pytest.importorskip("uedcli_native")
    sc = scen.room_with_a_flush_mounted_prop()
    ctx = actor_survey.build_context(sc.level, sc.index, "Trigger", sc.defaults)
    assert actor_survey.crosses_facts_for(ctx) == []


# --------------------------------------------------------------------- Task 13: touches

def test_touches_fires_between_the_surveyed_actor_and_a_face_it_is_flush_against():
    pytest.importorskip("uedcli_native")
    sc = scen.niche_carved_into_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Bystander", sc.defaults)
    facts = actor_survey.touches_facts_for(ctx)
    assert any(f.src == "Bystander" and f.dst == "Wall" and f.relation == "touches"
               for f in facts)


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


def test_touches_fires_for_a_mover_resting_on_a_wall():
    """A Mover's private model is a real brush, just outside world CSG, so it's not in `csg_order`
    and no last-writer rule over that list can ever name one. `resolved_matter_of` asks the
    per-actor question instead, which is what lets a non-world-CSG brush lead a `touches` line at
    all -- the spec's "a Mover is treated exactly like an Add".

    `Keypad`, the point-actor half of this fixture's original pair, is out of scope under the
    redesigned spec (brush-vs-brush only) and is no longer tested here -- point actors carry no
    polygon for `touches`'s area-contact test now that `CollisionRadius`/`CollisionHeight` handling
    is gone."""
    pytest.importorskip("uedcli_native")
    sc = scen.props_flush_against_a_room_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Door", sc.defaults)
    facts = actor_survey.touches_facts_for(ctx)
    assert any(f.src == "Door" and f.dst == "Room" for f in facts), facts
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




def test_a_far_seed_brush_does_not_disturb_a_touch():
    """`neighborhood`'s own first-brush clause forces the level's seed brush into the solve set even
    when it is nowhere near the surveyed actor, and `near_brushes` then has to keep it out of the
    fact set. Pinned on the fixture whose seed is 4000uu away and in the set only because of that
    clause."""
    pytest.importorskip("uedcli_native")
    sc = scen.far_apart_rooms()
    ctx = actor_survey.build_context(sc.level, sc.index, "FarRoom", sc.defaults)
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




def test_crosses_does_not_fire_for_a_room_carved_into_solid_rock():
    """Board item `crosses-fires-on-a-subtract-s-carve-victim`: `Rock` wrongly reported `crosses`
    against `RoomA`/`RoomB` (462uu/512uu) pre-fix -- the ordinary "solid rock, rooms carved into
    it" case, not a genuine penetration."""
    sc = scen.two_rooms_side_by_side()
    ctx = actor_survey.build_context(sc.level, sc.index, "Rock", sc.defaults)
    facts = actor_survey.crosses_facts_for(ctx)
    assert not any(f.dst in ("RoomA", "RoomB") for f in facts)


def test_touches_fires_both_directions_for_a_doorway_cut_through_a_wall_seam():
    """Board item `crosses-fires-on-a-subtract-s-carve-victim`: `WallA` wrongly reported `crosses`
    against `Doorway` (192uu) pre-fix, with `touches` suppressed both directions
    (`pair_touches(WallA, Doorway)` was already `True`; only the `crosses`-claims-the-pair exclusion
    blocked it). Post-fix, `crosses` is silent and `touches` fires both ways -- the doorway's carve
    boundary is real on the wall it cuts through, seen from either side."""
    sc = scen.a_doorway_through_a_wall_seam()
    ctx_a = actor_survey.build_context(sc.level, sc.index, "WallA", sc.defaults)
    assert not any(f.dst == "Doorway" for f in actor_survey.crosses_facts_for(ctx_a))
    assert any(f.src == "WallA" and f.dst == "Doorway" for f in actor_survey.touches_facts_for(ctx_a))

    ctx_doorway = actor_survey.build_context(sc.level, sc.index, "Doorway", sc.defaults)
    assert any(f.src == "Doorway" and f.dst == "WallA"
              for f in actor_survey.touches_facts_for(ctx_doorway))


def test_crosses_does_not_fire_for_an_add_to_add_pair_whose_source_was_later_recarved():
    """Board item `crosses-fires-on-a-subtract-s-carve-victim`'s own closing paragraph, the fourth
    case (no fixture pinned it before this): `Rock --crosses(1.47e+03uu)--> Crate` pre-fix, an
    Add-to-Add pair where `Room`/`Corridor` (Subtracts later than `Rock` in trunk order) carve away
    the matter that would otherwise reach `Crate` -- the same `_source_cells`-sources-authored-cells
    root cause as the other three rows, not a separate bug. Reuses the already-committed
    `an_oversized_corridor_past_its_room` fixture (verified live, pre-fix: `crosses_facts_for(Rock)`
    reports exactly `Rock --crosses(1472.0uu)--> Crate`, matching the board item's own cited figure);
    no new fixture needed."""
    sc = scen.an_oversized_corridor_past_its_room()
    ctx = actor_survey.build_context(sc.level, sc.index, "Rock", sc.defaults)
    assert not any(f.dst == "Crate" for f in actor_survey.crosses_facts_for(ctx))


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
    """Within CSG_TOLERANCE of coincident is `touches`; clearly past it is `crosses`. No (src, dst)
    pair is ever reported as both. `Additive4` is the live example: it crosses `Additive2` and
    touches `Subtract3`, never the other relation for the other pair."""
    pytest.importorskip("uedcli_native")
    sc = scen.shelf_pokes_through_a_niche_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Additive4", sc.defaults)
    crossed = {(f.src, f.dst) for f in actor_survey.crosses_facts_for(ctx)}
    touched = {(f.src, f.dst) for f in actor_survey.touches_facts_for(ctx)}
    assert crossed and touched and crossed & touched == set()


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


def test_touches_leads_with_the_surveyed_actor():
    # subtract_stops_flush_against_a_wall: Room (subtract) stops exactly at Wall's -X face --
    # a real touches fact, Room leading.
    pytest.importorskip("uedcli_native")
    sc = scen.subtract_stops_flush_against_a_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Room", sc.defaults)
    facts = actor_survey.touches_facts_for(ctx)
    assert facts and all(f.src == "Room" for f in facts)
    assert any(f.dst == "Wall" for f in facts)


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




def test_connects_leads_with_the_surveyed_actor():
    # redundant_nested_subtract: Shell(add), OuterRoom(subtract), InnerCarve(subtract) entirely
    # inside OuterRoom's already-void space -- surveying OuterRoom reports connects to InnerCarve.
    pytest.importorskip("uedcli_native")
    sc = scen.redundant_nested_subtract()
    ctx = actor_survey.build_context(sc.level, sc.index, "OuterRoom", sc.defaults)
    facts = actor_survey.connects_facts_for(ctx)
    assert facts and all(f.src == "OuterRoom" for f in facts)


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








# --------------------------------------------------------------------- Task 14 round 3

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


@pytest.mark.skip(reason="Known, accepted gap: connects has no reachability/sealed-void check -- "
                          "a Subtract's void sharing a coincident plane with another Subtract's "
                          "wall reports connects even when a solid block seals them apart. Owner "
                          "explicitly declined to fix this (\"connects is fine\") when the "
                          "touches/connects/occupies mechanism was rebuilt to match the spec.")
def test_connects_does_not_fire_for_a_subtract_sealed_inside_a_solid_block():
    s = scen.subtract_sealed_inside_a_block_sharing_the_outer_walls_plane()
    ctx = actor_survey.build_context(s.level, s.index, "InnerCut", s.defaults)
    facts = actor_survey.connects_facts_for(ctx)
    assert not any(f.dst == "OuterRoom" for f in facts), (
        "InnerCut's void is sealed inside Block's solid -- it must not report connects to "
        "OuterRoom just because they share a coincident wall plane")


@pytest.mark.skip(reason="Same known, accepted gap as "
                          "test_connects_does_not_fire_for_a_subtract_sealed_inside_a_solid_block "
                          "-- connects has no reachability check, so it can't tell a sealed void "
                          "apart from a continuous one.")
def test_connects_does_not_fire_the_other_direction_either():
    """`connects` is spec'd symmetric -- surveying the OTHER side of the same sealed bubble must
    also report nothing. A one-directional reachability check (walking only toward the NEIGHBOUR's
    interior) passes the `InnerCut`-survey direction above by accident: `InnerCut`'s own sealed
    interior is trivially reachable from the shared plane, even though the walk from `OuterRoom`'s
    side is blocked by `Block`'s solid."""
    s = scen.subtract_sealed_inside_a_block_sharing_the_outer_walls_plane()
    ctx = actor_survey.build_context(s.level, s.index, "OuterRoom", s.defaults)
    facts = actor_survey.connects_facts_for(ctx)
    assert not any(f.dst == "InnerCut" for f in facts), (
        "OuterRoom must not report connects to InnerCut's sealed bubble either -- connects is "
        "symmetric")


# --------------------------------------------------------------------- Task 15: contains primitives

def test_cell_volume_of_a_cube_is_exact():
    from uedcli import actorgraph
    sc = scen.kind_table_scenario()
    cells = actorgraph.decompose_convex(sc.level.actors["Adder"])
    assert len(cells) == 1
    assert actor_survey.cell_volume(cells[0]) == pytest.approx(64.0 ** 3, rel=1e-6)


def _box_cell(lo, hi):
    """A `ConvexCell` for the axis-aligned box `[lo, hi]`, for testing the splitting primitives
    directly without a whole Actor/Level."""
    from uedcli import actorgraph
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    half_spaces = [((1.0, 0.0, 0.0), x1), ((-1.0, 0.0, 0.0), -x0),
                   ((0.0, 1.0, 0.0), y1), ((0.0, -1.0, 0.0), -y0),
                   ((0.0, 0.0, 1.0), z1), ((0.0, 0.0, -1.0), -z0)]
    verts = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    return actorgraph.ConvexCell(vertices=verts, half_spaces=half_spaces)


def test_cell_intersection_returns_the_polytope_not_just_its_volume():
    a = _box_cell((0, 0, 0), (10, 10, 10))
    b = _box_cell((5, 5, 5), (15, 15, 15))
    cell = actor_survey._cell_intersection(a, b)
    assert cell is not None
    assert actor_survey.cell_volume(cell) == pytest.approx(125.0)  # the shared 5^3 corner


def test_cell_intersection_volume_still_matches_the_refactored_polytope():
    a = _box_cell((0, 0, 0), (10, 10, 10))
    b = _box_cell((5, 5, 5), (15, 15, 15))
    assert actor_survey._cell_intersection_volume(a, b) == pytest.approx(125.0)


def test_cell_intersection_of_two_coincident_cells_does_not_double_count_shared_faces():
    """Bug found live: two independent cells sharing every plane (two coincident boxes) fed
    `_polytope_from_planes` each plane TWICE (bare concatenation, `_cell_intersection`'s own
    docstring), and `cell_volume` fans/sums a face contribution per `half_spaces` entry -- so the
    shared faces were double-counted (`_cell_intersection_volume` came back ~2x `cell_volume`,
    not equal to it). `_polytope_from_planes` now dedupes by `_same_plane` first."""
    a = _box_cell((0, 0, 0), (10, 10, 10))
    b = _box_cell((0, 0, 0), (10, 10, 10))
    own_volume = actor_survey.cell_volume(a)
    assert actor_survey._cell_intersection_volume(a, b) == pytest.approx(own_volume)


def test_cell_intersection_is_none_for_disjoint_cells():
    a = _box_cell((0, 0, 0), (10, 10, 10))
    b = _box_cell((100, 100, 100), (110, 110, 110))
    assert actor_survey._cell_intersection(a, b) is None


def test_clip_cell_halves_a_cube():
    cube = _box_cell((0, 0, 0), (10, 10, 10))
    clipped = actor_survey._clip_cell(cube, (0.0, 0.0, 1.0), 5.0)   # z <= 5
    assert clipped is not None
    assert actor_survey.cell_volume(clipped) == pytest.approx(500.0)


def test_clip_cell_is_none_when_the_half_space_misses_entirely():
    cube = _box_cell((0, 0, 0), (10, 10, 10))
    assert actor_survey._clip_cell(cube, (0.0, 0.0, 1.0), -5.0) is None   # z <= -5: misses [0,10]


def test_subtract_cell_removes_a_smaller_cube_fully_inside():
    outer = _box_cell((0, 0, 0), (10, 10, 10))
    inner = _box_cell((3, 3, 3), (7, 7, 7))
    pieces = actor_survey._subtract_cell(outer, inner)
    assert sum(actor_survey.cell_volume(p) for p in pieces) == pytest.approx(1000.0 - 64.0)


def test_subtract_cell_is_unchanged_when_the_cutter_misses_entirely():
    outer = _box_cell((0, 0, 0), (10, 10, 10))
    far = _box_cell((100, 100, 100), (110, 110, 110))
    pieces = actor_survey._subtract_cell(outer, far)
    assert sum(actor_survey.cell_volume(p) for p in pieces) == pytest.approx(1000.0)


def test_partition_by_brushes_splits_a_cell_around_a_carving_subtract():
    from uedcli import actorgraph
    s = scen.pillar_in_room()   # Room(subtract), Pillar(add), Cutter(subtract, right half)
    ctx = actor_survey.build_context(s.level, s.index, "Pillar", s.defaults)
    pillar_cell = actorgraph.decompose_convex(s.level.actors["Pillar"], cache=ctx.cells)[0]
    cutter = s.level.actors["Cutter"]
    pieces = actor_survey._partition_by_brushes(pillar_cell, [cutter], ctx)
    # Pillar is 128x128x512 = 8388608 total; Cutter takes its right half over part of its height.
    assert sum(actor_survey.cell_volume(p) for p in pieces) == pytest.approx(
        actor_survey.cell_volume(pillar_cell))


def _wedge_cell():
    """A convex cell straddling x=0 everywhere (x in [-2, 10]) whose SOLID-side reach past x=0
    varies with y -- flush with the plane at y=0 (x <= 0 there, no reach at all) and deep at y=10
    (x <= 10) -- via one extra diagonal half-space on top of a box. A plain axis-aligned BOX cannot
    exhibit this (`penetration_depth`'s own docstring: a box's depth is uniform across its whole
    footprint), so this is the shape Bug 2's fix (bounding depth to the LOCAL overlap) is actually
    for -- real UNATCO content is not all axis-aligned."""
    from uedcli import actorgraph
    s = 0.7071067811865476   # 1/sqrt(2) -- the diagonal cutting plane's UNIT normal
    half_spaces = [
        ((1.0, 0.0, 0.0), 12.0), ((-1.0, 0.0, 0.0), 2.0),
        ((0.0, 1.0, 0.0), 10.0), ((0.0, -1.0, 0.0), 0.0),
        ((0.0, 0.0, 1.0), 10.0), ((0.0, 0.0, -1.0), 0.0),
        ((s, -s, 0.0), 0.0),                  # (x - y)/sqrt2 <= 0  =>  x <= y
    ]
    cell = actor_survey._polytope_from_planes(half_spaces, None)
    return actorgraph.ConvexCell(vertices=cell.vertices, half_spaces=cell.half_spaces)


def _narrow_face_on_x0(y_lo: float, y_hi: float) -> actor_survey.CsgFace:
    """A small `CsgFace` on the x=0 plane spanning `y in [y_lo, y_hi]` -- narrow enough that only
    the wedge's own LOCAL cross-section there is a candidate "depth", never a distant corner's."""
    return actor_survey.CsgFace(owner="Target", normal=(1.0, 0.0, 0.0), offset=0.0, verts=[
        (0.0, y_lo, 4.9), (0.0, y_hi, 4.9), (0.0, y_hi, 5.1), (0.0, y_lo, 5.1)])


def test_penetration_depth_does_not_fire_where_the_local_slice_never_reaches_solid(monkeypatch):
    """Bug 2, live UNATCO repro: the OLD code gated existence on a footprint OVERLAP check (does
    the cell's silhouette touch the face's footprint at all) but then read `min(past)`/`max(past)`
    from the cell's ENTIRE point set -- so a face touching the wedge's flush end (y~0, where the
    wedge's solid-side reach past x=0 is exactly zero) still 'crossed', because the SAME cell's far,
    unrelated deep end (y~10) supplied a `max(past)` of 10 and the cell's flat back face at x=-2
    supplied a `min(past)` of -2. Bounding `past` to the region that actually overlaps this face
    (the 3-D clip to the lateral prism over the overlap) fixes this: the local slice near y=0 has
    no real solid-side reach, and `penetration_depth` correctly reports no crossing there."""
    monkeypatch.setattr(actor_survey, "face_outward_sign", lambda ctx, face: 1.0)
    group = _wedge_cell()
    assert actor_survey.penetration_depth(None, [group], _narrow_face_on_x0(0.0, 0.01)) is None


def test_penetration_depth_tracks_the_local_depth_not_a_distant_corner(monkeypatch):
    """Same wedge, the genuine deep end (y~9.5): this one really does cross, and by roughly its own
    local amount (~9.6, not the cell's unrelated flat-back `-2` or some other face's own reach)."""
    monkeypatch.setattr(actor_survey, "face_outward_sign", lambda ctx, face: 1.0)
    group = _wedge_cell()
    depth = actor_survey.penetration_depth(None, [group], _narrow_face_on_x0(9.4, 9.6))
    assert depth is not None
    assert 9.0 < depth <= 9.6








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
















def test_occupies_facts_for_reports_the_matter_branch():
    s = scen.nested_niche_with_a_decoration()
    ctx = actor_survey.build_context(s.level, s.index, "Additive4", s.defaults)
    facts = actor_survey.occupies_facts_for(ctx)
    assert any(f.src == "Additive4" and f.dst == "Subtract3" and f.relation == "occupies"
               for f in facts)


def test_occupies_facts_for_composes_across_two_subtracts():
    # spec's "composes where containment cannot": an Add seated across two Subtracts' voids reports
    # occupies against BOTH, and crosses neither. `two_rooms_side_by_side`'s RoomA (x in [-200,-100])
    # and RoomB (x in [-100,0]) share the x=-100 plane with nothing solid between their voids
    # (`Rock` is carved straight through by both, both spanning the same y in [-100,100], z in
    # [-50,50]) -- `Bridge` (40 x 200 x 100 at (-100,0,0), so x in [-120,-80]) straddles that shared
    # plane, 20uu into each room's void, matching both rooms' y/z extents exactly (flush, never past
    # them) and nowhere near either room's own outer wall (x=-200 / x=0).
    s = scen.two_rooms_side_by_side()
    outer_shared_add = scen.brush("Bridge", (40, 200, 100), (-100, 0, 0))
    level = dataclasses.replace(s.level, actors={**s.level.actors, "Bridge": outer_shared_add},
                                order=s.level.order + ["Bridge"])
    ctx = actor_survey.build_context(level, s.index, "Bridge", s.defaults)
    facts = actor_survey.occupies_facts_for(ctx)
    dsts = {f.dst for f in facts if f.src == "Bridge" and f.relation == "occupies"}
    # Equality, not a subset check: also pins that "Outer" (first in trunk order, so the old
    # tautological condition (ii) falsely credited it too) does NOT appear alongside the two
    # correct facts.
    assert dsts == {"RoomA", "RoomB"}
    assert not any(f.relation == "crosses" for f in actor_survey.crosses_facts_for(ctx))


def test_containment_winner_and_contains_facts_for_are_gone():
    """No back-compat cruft: the winner-take-all contains machinery must not exist any more."""
    assert not hasattr(actor_survey, "containment_winner")
    assert not hasattr(actor_survey, "contains_facts_for")
    assert not hasattr(actor_survey, "_containment_candidates")


def test_occupies_and_touches_both_fire_for_an_add_flush_against_its_own_carved_walls():
    # an_add_inside_an_enclosing_subtract(clearance=0): Shelf pushed flush against Room's own
    # -X wall -- a real touches fact AND, once Shelf is excluded, Room is still the void's last
    # writer there, so occupies fires too. Both facts are genuinely true of the same pair at once.
    pytest.importorskip("uedcli_native")
    s = scen.an_add_inside_an_enclosing_subtract(clearance=0)
    ctx = actor_survey.build_context(s.level, s.index, "Shelf", s.defaults)
    facts = actor_survey.csg_facts_for(ctx)
    relations = {(f.src, f.dst, f.relation) for f in facts if f.src == "Shelf"}
    assert ("Shelf", "Room", "occupies") in relations
    assert ("Shelf", "Room", "touches") in relations


def test_carves_fires_when_a_subtract_removes_real_add_matter():
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.niche_carved_into_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Niche", sc.defaults)
    assert any(f.src == "Niche" and f.dst == "Wall" and f.relation == "carves"
               for f in actor_survey.carves_facts_for(ctx))


def test_carves_is_absent_where_the_subtract_only_stopped_flush():
    """The raw-vs-csg contrast the whole two-tier design exists for: raw has no `carves` relation at
    all (Task 10 -- the raw tier reasons over pure authored geometry, never trunk order), and reports
    `Room`/`Wall`'s authored boundaries as flush contact (`meets`); the csg tier correctly reports
    nothing against `Wall`, and reports `touches` instead. `Room` separately carves `Rock` (total
    removal, per spec) -- that fact is legitimate and out of scope for this test."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.subtract_stops_flush_against_a_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Room", sc.defaults)
    assert not any(f.dst == "Wall" for f in actor_survey.carves_facts_for(ctx))
    assert any(f.dst == "Wall" for f in actor_survey.touches_facts_for(ctx))
    raw = actor_survey.raw_facts_for(sc.level, sc.index, "Room", sc.defaults).facts
    assert not any(f.relation == "carves" for f in raw)
    assert any(f.src == "Room" and f.dst == "Wall" and f.relation == "touches" for f in raw)


def test_carves_never_fires_for_a_subtract_that_precedes_its_victim_in_trunk_order():
    """spec's own duals rule: "S-before-A -> only occupies possible; S-after-A -> only carves
    possible" -- mutual exclusivity, previously untested in either direction. `pillar_in_room`'s
    `Room` (Subtract, trunk-first) fully encloses `Pillar` (Add, trunk-second): `Room` precedes
    `Pillar`, so only `occupies` applies, never `carves`. Regression for a real bug:
    `_victim_matter_just_before`'s `csg_order[v_i + 1:s_i]` slice was empty whenever `s_i <= v_i`
    (Python does not raise or reverse on `start > stop`), so `not any([])` read vacuously True --
    `carves(Room, Pillar)` fired even though `Room` ran before `Pillar` existed at all."""
    import pytest
    pytest.importorskip("uedcli_native")
    s = scen.pillar_in_room()
    ctx = actor_survey.build_context(s.level, s.index, "Pillar", s.defaults)
    assert not any(f.src == "Room" and f.dst == "Pillar"
                   for f in actor_survey.carves_facts_for(ctx))
    assert any(f.src == "Pillar" and f.dst == "Room"
               for f in actor_survey.occupies_facts_for(ctx))


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






def test_carves_ordering_for_a_nonsolid_victim_uses_full_trunk_order():
    """Regression for `ctx.csg_index.get(victim.name, -1)` always returning -1 for a Nonsolid
    (`_WORLD_PASS_KINDS` excludes it), which made the `s_i <= v_i` ordering guard a no-op for any
    Nonsolid victim: a preceding Subtract wrongly got `carves` credit, and -- when both an earlier
    and a later Subtract overlapped the same Nonsolid -- the earlier (wrong) one got the credit
    while the later (right) one was silently dropped."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.nonsolid_straddled_by_an_earlier_and_a_later_subtract()
    ctx = actor_survey.build_context(sc.level, sc.index, "Decal", sc.defaults)
    facts = actor_survey.carves_facts_for(ctx)
    assert not any(f.src == "EarlySubtract" and f.dst == "Decal" for f in facts)
    assert any(f.src == "LateSubtract" and f.dst == "Decal" for f in facts)




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


def test_csg_fact_carries_no_depth_field():
    fact = actor_survey.CsgFact(src="A", dst="B", relation="crosses")
    assert not hasattr(fact, "depth_uu")


def test_csg_line_never_carries_a_depth_annotation():
    pytest.importorskip("uedcli_native")
    sc = scen.room_with_a_flush_mounted_prop()
    ctx = actor_survey.build_context(sc.level, sc.index, "Keypad", sc.defaults)
    facts = actor_survey.crosses_facts_for(ctx)
    nodes = actor_survey.raw_facts_for(sc.level, sc.index, "Keypad", sc.defaults).nodes
    lines = [actor_survey.format_csg_line(f, nodes) for f in facts]
    assert not any("(" in line for line in lines)


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
