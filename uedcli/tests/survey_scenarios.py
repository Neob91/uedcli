"""Geometric fixtures for `actor survey`'s tests.

One named builder per scenario, each returning a `Scenario` — never a bare tuple, so a test never
has to know how many things a fixture hands back. Geometry is stated in the builder's own docstring
in world units, because several tasks assert exact facts about it.

`index` is `conftest.StubClassIndex` (the offline mover/class-hierarchy stand-in the whole suite
already uses). `defaults` is the minimal class-defaults stand-in `test_serve_scene.py` already uses
for `_actor_radii` — a `for_class` returning an object with an empty `defaults` dict — so every
collision property a scenario needs is stated on the ACTOR, not resolved from a game package. A
scenario that wants an unresolvable class uses `failing_defaults()` instead.
"""
from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace

from uedcli import builders
from uedcli.builders import PF_SEMISOLID, cube, make_brush_actor
from uedcli.model import Actor, Level
from uedcli.tests.conftest import StubClassIndex


@dataclass(frozen=True)
class Scenario:
    level: Level
    index: object
    defaults: object


def stub_defaults():
    """Every class resolves, with no defaults of its own — so an actor's own props are the whole
    story. Mirrors `test_serve_scene.py`'s `_actor_radii` stub."""
    return SimpleNamespace(for_class=lambda cls: SimpleNamespace(defaults={}))


def failing_defaults():
    """Every class fails to resolve, the way a missing game package does."""
    from uedcli import uprops

    def _raise(cls):
        raise uprops.SchemaError(f"no schema for {cls}")

    return SimpleNamespace(for_class=_raise)


def defaults_with(values: dict):
    """Every class shares one dict of class-DEFAULT members, keyed like `classdefaults.ClassInfo
    .defaults`: `(field_name.casefold(), 0) -> value`. Lets a test give a class default that
    differs from an actor's own instance props, to exercise the present-but-empty-vs-truly-absent
    distinction `_blocks_movement`/`_collision_half_extent` share with `serve/scene.py
    ::_actor_radii` (`stub_defaults()`'s always-empty dict can't tell those apart)."""
    table = {(k.casefold(), 0): v for k, v in values.items()}
    return SimpleNamespace(for_class=lambda cls: SimpleNamespace(defaults=table))


def _dec(v):
    return tuple(Decimal(str(c)) for c in v)


def brush(name, size, location, *, csg="add", poly_flags=0):
    """An axis-aligned box brush actor of world `size` centred at `location`."""
    return make_brush_actor(name, cube(*size), location=_dec(location), csg=csg,
                            poly_flags=poly_flags)


def oper_brush(name, size, location, oper):
    """A box brush carrying a raw `CsgOper` value `make_brush_actor` cannot author (`CSG_Intersect`,
    `CSG_Deintersect`). Strips the `CsgOper` `make_brush_actor` already added rather than appending a
    second one: `query._csg_oper` reads the FIRST match while `preview_native._csg_oper_or_skip`
    reads `dict(actor.props)` (last wins), so two entries would make the two disagree."""
    a = brush(name, size, location)
    props = [p for p in a.props if p[0].casefold() != "csgoper"] + [("CsgOper", oper)]
    return dataclasses.replace(a, props=props)


def point(name, location, *, cls="Engine.Light", props=()):
    return Actor(name=name, cls=cls, location=_dec(location), props=list(props))


def _level(actors) -> Level:
    return Level(actors={a.name: a for a in actors}, order=[a.name for a in actors])


def _scenario(actors, *, defaults=None) -> Scenario:
    return Scenario(level=_level(actors), index=StubClassIndex(),
                    defaults=defaults if defaults is not None else stub_defaults())


# --------------------------------------------------------------------- Task 7's scenarios

def far_apart_rooms() -> Scenario:
    """Trunk order: Shell, FarRoom, Touching, Distant.

    * `Shell`   1024^3 Add   at (0, 0, 0)          — the level's FIRST world-CSG brush
    * `FarRoom` 512^3 Subtract at (4000, 0, 0)     — the surveyed actor, far from Shell
    * `Touching` 256^3 Add   at (4384, 0, 0)       — flush against FarRoom's +X wall (x=4256)
    * `Distant` 256^3 Add    at (8000, 0, 0)       — meets nothing, and is not the first brush
    """
    return _scenario([
        brush("Shell", (1024, 1024, 1024), (0, 0, 0)),
        brush("FarRoom", (512, 512, 512), (4000, 0, 0), csg="subtract"),
        brush("Touching", (256, 256, 256), (4384, 0, 0)),
        brush("Distant", (256, 256, 256), (8000, 0, 0)),
    ])


def room_with_pillar_and_light() -> Scenario:
    """Trunk order: Room, Pillar, Light.

    * `Room`   1024^3 Subtract at (0, 0, 0)
    * `Pillar` 128 x 128 x 512 Add at (0, 0, 0)  — a later Add standing inside the room's void
    * `Light`  a point actor at (300, 0, 0)      — inside Room, outside Pillar

    The spec's pillar case: the Add never competes for `contains` (it is not a Subtract), so the
    Room owns the Light uncontested.
    """
    return _scenario([
        brush("Room", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        brush("Pillar", (128, 128, 512), (0, 0, 0)),
        point("Light", (300, 0, 0)),
    ])


def pad_boundary_neighbors() -> Scenario:
    """Trunk order: Anchor, JustWithinPad, JustOutsidePad -- proves `NEIGHBORHOOD_PAD` (1uu) is the
    exact threshold, not just a value that happens to be asserted.

    * `Anchor`          100^3 Add at (0,0,0)     -- +X edge at x=50; the surveyed actor (and,
      being trunk-first, also the seeded world-CSG brush -- irrelevant here since it's tested via
      direct self-overlap, not the seed clause)
    * `JustWithinPad`   20^3 Add at (61,0,0)     -- extent x:[51,71]: a 1uu gap from Anchor's edge,
      exactly `NEIGHBORHOOD_PAD` -- must be selected
    * `JustOutsidePad`  20^3 Add at (62,0,0)     -- extent x:[52,72]: a 2uu gap -- must NOT be
      selected
    """
    return _scenario([
        brush("Anchor", (100, 100, 100), (0, 0, 0)),
        brush("JustWithinPad", (20, 20, 20), (61, 0, 0)),
        brush("JustOutsidePad", (20, 20, 20), (62, 0, 0)),
    ])


# --------------------------------------------------------------------- Task 8's scenarios

def niche_carved_into_wall() -> Scenario:
    """Trunk order: Wall, Niche, Bystander.

    * `Wall`      512 x 64 x 512 Add      at (0, 0, 0)      — x,z in [-256, 256], y in [-32, 32]
    * `Niche`     128 x 128 x 128 Subtract at (0, 0, 0)     — cuts a through-hole in x,z in
      [-64, 64]: `Niche`'s y-extent ([-64, 64]) fully spans `Wall`'s thickness, so no wall matter
      survives inside that x,z square, at any y.
    * `Bystander` 64^3 Add                at (0, 64, 150)   — flush against the wall's +Y face
      (y=32), OUTSIDE the hole's z in [-64, 64] band (its own z-extent is [118, 182]) so it rests
      on real, surviving Wall matter.

    `Niche` is LATER in trunk order than `Wall`, so the raw tier's order heuristic calls it
    `carves`; the csg tier confirms it (Task 17). `Bystander` touches the wall and nothing else.

    (`Bystander`'s x,z placement is load-bearing, not cosmetic: at `Niche`'s footprint -- e.g. the
    task brief's original `(0, 64, 0)` -- `Bystander` sits entirely over the through-hole, so the
    resolved CSG model has NO wall matter under it at all; `region_of(Bystander)` then meets zero
    real Wall faces, silently breaking any test that assumes a genuine touch. At the corrected
    position, `Wall`'s +Y face survives everywhere outside the hole -- but flush add-on-add contact
    CONSUMES `Wall`'s own face directly under `Bystander`'s footprint too (`x in [-32, 32], z in
    [118, 182]`; verified against the resolved model), leaving only `Bystander`'s own coincident
    face there. `region_of(Bystander)`'s 1uu pad still reaches a real `Wall` plane, but only through
    the flanking fragments just outside that footprint (e.g. `z in [64, 118]`/`[182, 256]`), never
    through a face directly underneath.)

    (Y is corrected from the task brief's `(0, 96, 0)`, which leaves a 32uu gap to Wall's face --
    `Bystander` has half-extent 32, so its near face sits flush at y=32 only when its center is at
    y=64.)
    """
    return _scenario([
        brush("Wall", (512, 64, 512), (0, 0, 0)),
        brush("Niche", (128, 128, 128), (0, 0, 0), csg="subtract"),
        brush("Bystander", (64, 64, 64), (0, 64, 150)),
    ])


def room_contains_a_mover() -> Scenario:
    """Trunk order: Room, Door.

    * `Room` 1024^3 Subtract at (0, 0, 0)
    * `Door` 64 x 8 x 128 `DeusEx.DeusExMover` at (0, 0, 0) — fully inside Room's void

    A Mover carries no `CsgOper` at all, so trunk order is meaningless for it and `classify_pair`
    always reports `contains` from the Subtract (`actorgraph.py:599-602`). `StubClassIndex` puts
    `DeusEx.DeusExMover` under `Engine.Mover` via its `mover_classes` default.
    """
    door = make_brush_actor("Door", cube(64, 8, 128), location=_dec((0, 0, 0)),
                            mover_class="DeusEx.DeusExMover")
    return _scenario([brush("Room", (1024, 1024, 1024), (0, 0, 0), csg="subtract"), door])


# --------------------------------------------------------------------- Task 11's scenario

def room_with_a_flush_mounted_prop() -> Scenario:
    """Trunk order: Room, Keypad, Trigger, Ghost, Bracket.

    * `Room`    1024^3 Subtract at (0, 0, 0)       — walls at x = +/-512
    * `Keypad`  a point actor at (504, 0, 0), bCollideActors + bBlockActors, R=16 H=16 —
                its collision cylinder spans x in [488, 520], so 8uu of it is inside the +X wall's
                solid
    * `Trigger` a point actor at the same place, bCollideActors but NOT bBlockActors, R=520 —
                a room-spanning trigger volume, the exact shape the spike's source gate excludes
    * `Ghost`   a point actor at (504, 0, 0) with no collision props at all
    * `Bracket` a point actor at (520, 0, 0), same blocking collision as `Keypad`, R=16 H=16 —
                its LOCATION is buried in the +X wall and sits OUTSIDE `Room`'s own padded AABB
                (x = 513), but its cylinder spans x in [504, 536], which does meet that AABB. This
                is the case `nearby_point_actors`' extent-aware candidate test exists for: a bare-
                `Location` filter drops `Bracket` from `Room`'s point candidates, and its
                `crosses` fact then shows up when you survey `Bracket` and vanishes when you
                survey `Room`. Its deepest sample point is 24 uu past the wall face at x=512.
    """
    coll = [("bCollideActors", "True"), ("bBlockActors", "True"),
            ("CollisionRadius", "16"), ("CollisionHeight", "16")]
    trig = [("bCollideActors", "True"), ("bBlockActors", "False"),
            ("CollisionRadius", "520"), ("CollisionHeight", "520")]
    return _scenario([
        brush("Room", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        point("Keypad", (504, 0, 0), cls="DeusEx.Keypad1", props=coll),
        point("Trigger", (504, 0, 0), cls="Engine.Trigger", props=trig),
        point("Ghost", (504, 0, 0), cls="Engine.Light"),
        point("Bracket", (520, 0, 0), cls="DeusEx.Keypad1", props=coll),
    ])


# --------------------------------------------------------------------- Task 12's scenarios

def pillar_in_room() -> Scenario:
    """The scenario `uedcli/tests/test_csg_kind_facts.py` already pins, rebuilt here through this
    module's own helpers so both stay in step. Trunk order: Room, Pillar, Cutter.

    * `Room`   1024^3 Subtract at (0, 0, 0)
    * `Pillar` 128 x 128 x 512 Add at (0, 0, 0)
    * `Cutter` 256^3 Subtract at (128, 0, 0)  — takes the pillar's RIGHT half over the middle of
      its height, leaving the left half and both ends

    Pinned there: (-40, 0, 0) is solid, (40, 0, 0) is not, the pillar keeps 11 faces and
    229376 uu^2 of its original 294912.
    """
    return _scenario([
        brush("Room", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        brush("Pillar", (128, 128, 512), (0, 0, 0)),
        brush("Cutter", (256, 256, 256), (128, 0, 0), csg="subtract"),
    ])


def shelf_pokes_through_a_niche_wall() -> Scenario:
    """The spec's own nesting example -- `Subtract1 -> Additive2 -> Subtract3 -> Additive4` is a
    NESTING chain (each one geometrically inside/carved-from the previous), not a trunk-order
    mandate. Trunk order here is `Subtract1, Additive2, Additive4, Subtract3` -- `Additive4` is
    authored BEFORE `Subtract3`, load-bearing (see the correction note below).

    * `Subtract1` 1024^3 Subtract at (0, 0, 0)          — the outer room
    * `Additive2` 256 x 64 x 256 Add at (0, 128, 0)     — a wall inside it, y in [96, 160]
    * `Additive4` 32 x 256 x 32 Add at (0, 128, 0)      — a shelf, x,z in [-16, 16] (inside
      `Subtract3`'s future hole footprint, so it never touches `Additive2`'s own faces), y in
      [0, 256] (past `Additive2`'s wall on both ends).
    * `Subtract3` 128 x 128 x 128 Subtract at (0, 128, 0) — a niche, y in [64, 192]. Carved AFTER
      `Additive4`, it removes `Additive4`'s own matter within its box too (x,z in [-64, 64]),
      leaving `Additive4`'s y in [0, 64) and (192, 256] surviving on either side, past
      `Subtract3`'s own y=64/y=192 caps.

    `Additive4` crosses `Subtract3` -- the immediate boundary it pushes through -- and never
    `Additive2`, however the nesting reads (the spec's strict-locality rule): depth 64uu, both ends
    ((256-192) above and (64-0) below), verified against `crosses_facts_for` directly.

    (Trunk order is the fix, not a dimension: with the naive order `..., Subtract3, Additive4`
    (`Additive4` authored AFTER the niche), `Additive4`'s own matter, wherever it overlaps
    `Additive2`'s already-solid ring `x,z` in [64, 128]/[-128, -64], gets folded into that solid by
    plain CSG_Add union (no internal face between two Adds); AND wherever `Additive4` fills what
    `Subtract3` carved to void, `Subtract3`'s own face there gets removed as now-interior. Both
    effects erase exactly the face `Additive4` would need to overlap to register a crossing --
    verified directly: with that order, `Additive4`'s resolved footprint is clipped to `Subtract3`'s
    own +-64 hole (nothing survives past it), and `crosses_facts_for` reports no `Additive4`-owned
    fact at all. Authoring `Additive4` first means `Subtract3`'s later carve is what PRODUCES the
    y=64/y=192 faces, as a real carve into `Additive4`'s own pre-existing matter, so they survive
    intact and `Additive4`'s full authored y in [0, 256] genuinely overlaps them.)
    """
    return _scenario([
        brush("Subtract1", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        brush("Additive2", (256, 64, 256), (0, 128, 0)),
        brush("Additive4", (32, 256, 32), (0, 128, 0)),
        brush("Subtract3", (128, 128, 128), (0, 128, 0), csg="subtract"),
    ])


# --------------------------------------------------------------------- Task 13's scenarios

def subtract_stops_flush_against_a_wall() -> Scenario:
    """Trunk order: Outer, Rock, Wall, Room.

    * `Outer` 1024^3 Subtract at (0, 0, 0)          — the void the rest lives in
    * `Rock`  448 x 512 x 512 Add at (0, 0, 0)      — x in [-224, 224], the material the room is
      carved out of, butted against the wall's -X face
    * `Wall`  64 x 512 x 512 Add at (256, 0, 0)     — x in [224, 288]
    * `Room`  448 x 512 x 512 Subtract at (0, 0, 0) — x in [-224, 224], removing `Rock` entirely and
      stopping EXACTLY at the wall's -X face, removing none of the WALL's matter

    `Room` is later in trunk order than `Wall`, so the raw tier's order heuristic calls this
    `carves`; the csg tier must call it `touches` and NOT `carves` (Task 17's contrast test uses the
    same fixture).

    Two corrections are baked in here, both of the same class, and the second is why `Rock` exists.

    (1) `Outer` is corrected in from the task brief's two-brush version, for the same class of
    reason `niche_carved_into_wall` documents its own corrections. Without it `Wall` is the level's
    leading Add, which `bsp_brush_csg` turns into the world SHELL with its faces reversed — `Wall`'s
    interior then reads void, `Room`'s carve meets void on both sides of x=224, and the contact face
    is dropped as interior to void. Verified against the resolved model: the two-brush level has NO
    surviving face on the x=224 plane at all, from either owner, so the fact under test could only
    ever have fired off `Wall`'s unrelated +/-Y/+/-Z shell faces.

    (2) `Rock` is corrected in because `Outer` alone left `Room` carving space that was ALREADY
    void — measured: zero resolved surfaces owned by `Room` anywhere in the solve, and every point
    of its own volume already void at the moment it ran. A Subtract that removes nothing creates no
    surface, so nothing can rest against its authored boundary, and the fixture was asking for a
    contact with a wall that was never opened. That is the same shape as a Subtract dropped in empty
    space, and as the far end of an oversized corridor run past the room it opens into — both of
    which `touches` must reject, and both of which are their own regression tests. The spec's own
    worked example is the corrected shape, not the degenerate one: `Brush118` is a room carved into
    rock, and "no real removal ever occurred" there means it removed none of `Brush113`'s matter,
    not that it removed nothing at all.

    The contact plane still carries exactly ONE surviving face, and it belongs to `Room` — `Wall`
    authors none at x=224, its own face there having been consumed by the carve that stops on it.
    So a predicate reading its candidates off the resolved snapshot can only reach this pair from
    `Wall`'s survey by computing a second survey direction.
    """
    return _scenario([
        brush("Outer", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        brush("Rock", (448, 512, 512), (0, 0, 0)),
        brush("Wall", (64, 512, 512), (256, 0, 0)),
        brush("Room", (448, 512, 512), (0, 0, 0), csg="subtract"),
    ])


def peg_buried_in_a_wall() -> Scenario:
    """Trunk order: Room, Wall, Peg.

    * `Room` 1024^3 Subtract at (0, 0, 0)
    * `Wall` 128 x 1024 x 1024 Add at (256, 0, 0)  — a partition, x in [192, 320]
    * `Peg`  100 x 64 x 64 Add at (242, 0, 0)      — x in [192, 292], entering through `Wall`'s -X
      face and sinking 100uu into its solid, never reaching the void on the far side

    The case plane coincidence alone gets wrong: four of `Peg`'s vertices sit exactly ON `Wall`'s
    x=192 plane, so "is any point near the plane" reports a flush touch for an actor that is
    materially buried. `penetration_depth` does not catch it either — `crosses` needs the source to
    straddle the face, and `Peg` has no matter on the void side at all — so `touches` is the relation
    that has to exclude it. It does, by naming both sides of the contact: at `Peg`'s own footprint on
    x=192 the matter is `Peg`'s on one side and `Room`'s void on the other, never `Wall`'s, so the
    pair under test is not the pair the contact is between.

    `Room` is first so the level has an ordinary solve rather than the leading-Add seed shell, and
    `Wall`'s solid is real: (194, 0, 0) and (300, 0, 0) are solid, (325, 0, 0) and (190, 0, 0) are
    not.
    """
    return _scenario([
        brush("Room", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        brush("Wall", (128, 1024, 1024), (256, 0, 0)),
        brush("Peg", (100, 64, 64), (242, 0, 0)),
    ])


def peg_partly_buried_in_a_wall(depth: int) -> Scenario:
    """`peg_buried_in_a_wall`, but `Peg` is sunk only `depth` uu into `Wall` instead of all 100 --
    so it straddles the x=192 face with (100 - depth) uu still out in `Room`'s void.

    Trunk order: Room, Wall, Peg. `Peg` is 100 x 64 x 64 spanning x in [92 + depth, 192 + depth].

    Parameterised because the whole 1..99 range is the test, not one sample of it: every depth in
    that range is a real burial and none of them is `touches`. The shape is genuinely harder than
    total burial and it is what defeated the round-4 predicate at every depth. `Peg`'s own flank
    faces poke out of the wall, so `Wall`'s matter really is flush against them from outside, and a
    predicate that only names the two sides of that one contact sees a perfectly good touch -- the
    burial is 100 uu away, on the OTHER plane. It also escapes `crosses`, which would otherwise have
    caught it: `Wall`'s x=192 face survives only as the flanking fragment `y in [32, 512]` that
    `Peg`'s own contact split it into, and `penetration_depth` bounds its footprint test to that
    fragment, which by construction does not overlap `Peg`."""
    return _scenario([
        brush("Room", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        brush("Wall", (128, 1024, 1024), (256, 0, 0)),
        brush("Peg", (100, 64, 64), (142 + depth, 0, 0)),
    ])


def props_flush_against_a_room_wall() -> Scenario:
    """Trunk order: Room, Keypad, Door.

    * `Room`   1024^3 Subtract at (0, 0, 0)          — walls at x = +/-512
    * `Keypad` a point actor at (496, 0, 0), bCollideActors + bBlockActors, R=16 H=16 — its
      collision cylinder spans x in [480, 512], resting EXACTLY on the +X wall and not past it
    * `Door`   64 x 8 x 128 `DeusEx.DeusExMover` at (480, 0, 0) — x in [448, 512], the same flush
      contact from a Mover

    Neither actor is in world CSG at all: a point actor has no brush, and a Mover is excluded from
    the solve (`in_world_csg`). Both are nevertheless legitimate `touches` SOURCES -- the spec makes
    `touches` "not source-restricted", and rules a Mover's private model "treated exactly like an
    Add's". Neither can be the OTHER side of one (`crosses_target_eligible`): a collision cylinder
    is not world geometry and a Mover authors no world face.

    `room_with_a_flush_mounted_prop` is the contrasting fixture -- its `Keypad` is 8uu INTO the
    wall, which is `crosses`. This one is the boundary case that has to come out the other way."""
    door = make_brush_actor("Door", cube(64, 8, 128), location=_dec((480, 0, 0)),
                            mover_class="DeusEx.DeusExMover")
    return _scenario([
        brush("Room", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        point("Keypad", (496, 0, 0), cls="DeusEx.Keypad1",
              props=[("bCollideActors", "True"), ("bBlockActors", "True"),
                     ("CollisionRadius", "16"), ("CollisionHeight", "16")]),
        door,
    ])


def two_rooms_side_by_side() -> Scenario:
    """Trunk order: Outer, Rock, RoomA, RoomB.

    * `Outer` 1024^3 Subtract at (0, 0, 0)            — the void the rest lives in
    * `Rock`  1024^3 Add at (0, 0, 0)                 — fills it back in, so the rooms carve solid
    * `RoomA` 100 x 200 x 100 Subtract at (-150, 0, 0) — x in [-200, -100]
    * `RoomB` 100 x 200 x 100 Subtract at (-50, 0, 0)  — x in [-100, 0]

    Two rooms sharing the x=-100 wall plane, with the same y and z extents — so each room's OTHER
    four walls are coplanar continuations of the other's. The spec calls this shape extremely common
    and rules it `connects`, never `touches`: nothing solid survives between two Subtracts sharing a
    plane, so there is no face to be flush against.

    The trap it exists to pin is those coplanar continuations. `RoomA`'s carve volume reaches exactly
    the y=+/-100 and z=+/-50 planes of `RoomB`'s walls and stops there, on the solid side of each, so
    any test that asks "does the source reach this plane without passing it" fires on a contact 100uu
    away from anything the two rooms share.
    """
    return _scenario([
        brush("Outer", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        brush("Rock", (1024, 1024, 1024), (0, 0, 0)),
        brush("RoomA", (100, 200, 100), (-150, 0, 0), csg="subtract"),
        brush("RoomB", (100, 200, 100), (-50, 0, 0), csg="subtract"),
    ])


def blind_pocket_in_a_wall() -> Scenario:
    """Trunk order: Outer, Wall, Pocket.

    * `Outer`  1024^3 Subtract at (0, 0, 0)
    * `Wall`   512 x 128 x 512 Add at (0, 0, 0)    — x,z in [-256, 256], y in [-64, 64]
    * `Pocket` 64^3 Subtract at (0, 64, 0)         — x,z in [-32, 32], y in [32, 96], entering
      through the wall's +Y face and stopping at y=32, HALFWAY through its thickness

    The carve-victim shape with none of `niche_carved_into_wall`'s quirks: an ordinary solve (the
    leading world-CSG brush is a Subtract), and a carve that stops inside the wall rather than going
    through it. What survives of `Wall` sits flush against all five of `Pocket`'s faces, which the
    spec says is `touches` (`carves`: "the boundary retreats to wherever the carve stopped, and what
    remains of X sits flush against it — that is touches").
    """
    return _scenario([
        brush("Outer", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        brush("Wall", (512, 128, 512), (0, 0, 0)),
        brush("Pocket", (64, 64, 64), (0, 64, 0), csg="subtract"),
    ])


# --------------------------------------------------------------------- Task 13 round 6

def two_adds_butted_face_to_face(offset: float = 0.0) -> Scenario:
    """Trunk order: Outer, BlockA, BlockB.

    * `Outer`  2048^3 Subtract at (0, 0, 0)     — the void the blocks live in
    * `BlockA` 128^3 Add at (-64, 0, 0)         — x in [-128, 0]
    * `BlockB` 128^3 Add at (64 + offset, 0, 0) — x in [offset, 128 + offset]

    A wall built from two blocks: the most ordinary shape in any level, and the one no round of this
    relation had a fixture for. Their footprints on the shared x=0 plane are IDENTICAL, so the CSG
    contact consumes the face on BOTH owners and the resolved model has no surviving face there at
    all, from either side — which is why a predicate that enumerates candidate faces from the final
    snapshot cannot even test the pair.

    `offset` separates them (positive) or overlaps them (negative), which is how the relation's
    contact tolerance is measured: at `offset` 0 they are flush, and the accept/reject boundary must
    track `actor_survey.CSG_TOLERANCE` rather than any probe step.
    """
    return _scenario([
        brush("Outer", (2048, 2048, 2048), (0, 0, 0), csg="subtract"),
        brush("BlockA", (128, 128, 128), (-64, 0, 0)),
        brush("BlockB", (128, 128, 128), (Decimal("64") + Decimal(str(offset)), 0, 0)),
    ])


def an_add_inside_an_enclosing_subtract(clearance: int) -> Scenario:
    """Trunk order: Room, Shelf.

    * `Room`  2048^3 Subtract at (0, 0, 0)                  — x, y, z in [-1024, 1024]
    * `Shelf` 64^3 Add at (-1024 + clearance + 32, 0, 0)    — `clearance` uu from the -X wall, and
      at least that far from every other one

    An Add standing free in a room's void. Its faces are adjacent to that void at ANY distance, so
    every "whose space is on each side of this plane" test accepts it — measured at 960uu of
    clearance on the round-5 predicate. It is not a contact: the shelf touches no wall.

    `clearance` 0 is the contrasting case — the shelf pushed back against the wall, which IS a
    contact, and on the Subtract's own carve boundary.
    """
    return _scenario([
        brush("Room", (2048, 2048, 2048), (0, 0, 0), csg="subtract"),
        brush("Shelf", (64, 64, 64), (Decimal(-1024 + clearance + 32), 0, 0)),
    ])


def a_subtract_that_carves_nothing() -> Scenario:
    """Trunk order: Outer, Crate, Ghost.

    * `Outer` 4096^3 Subtract at (0, 0, 0)          — the void the rest lives in
    * `Crate` 128^3 Add at (-64, 0, 0)              — x in [-128, 0]
    * `Ghost` 1024^3 Subtract at (512, 0, 0)        — x in [0, 1024], butted flush against `Crate`'s
      +X face but entirely inside `Outer`'s void, so it removes NOTHING, anywhere

    A Subtract's authored boundary is not a surface unless the carve made one. `Ghost` made none, so
    `Crate` rests against nothing and the pair is not `touches`. Seen on real shipped content: a
    Subtract with zero resolved surfaces in the whole solve was still being named as a target.
    """
    return _scenario([
        brush("Outer", (4096, 4096, 4096), (0, 0, 0), csg="subtract"),
        brush("Crate", (128, 128, 128), (-64, 0, 0)),
        brush("Ghost", (1024, 1024, 1024), (512, 0, 0), csg="subtract"),
    ])


def an_oversized_corridor_past_its_room() -> Scenario:
    """Trunk order: Outer, Rock, Room, Corridor, Crate.

    * `Outer`    4096^3 Subtract at (0, 0, 0)
    * `Rock`     2048^3 Add at (0, 0, 0)                       — solid material
    * `Room`     1024^3 Subtract at (0, 0, 0)                  — x in [-512, 512], carved into it
    * `Corridor` 1152 x 128 x 128 Subtract at (-1024, 0, 0)    — x in [-1600, -448], deliberately
      run PAST the room it opens into so its end plane does not land on the room's wall
    * `Crate`    128^3 Add at (-384, 0, 0)                      — x in [-448, -320], standing in the
      room flush against the corridor's phantom x=-448 end plane

    The spec calls the oversized-corridor idiom routine — a corridor is run past the room to avoid a
    coplanar seam. Its far end is inside space the ROOM already emptied, so the corridor made no
    surface there, and the crate resting against that plane is resting against nothing. The nearest
    material the corridor actually removed is far outside the room.
    """
    return _scenario([
        brush("Outer", (4096, 4096, 4096), (0, 0, 0), csg="subtract"),
        brush("Rock", (2048, 2048, 2048), (0, 0, 0)),
        brush("Room", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        brush("Corridor", (1152, 128, 128), (-1024, 0, 0), csg="subtract"),
        brush("Crate", (128, 128, 128), (-384, 0, 0)),
    ])


def a_doorway_through_a_wall_seam() -> Scenario:
    """Trunk order: Outer, WallA, WallB, Doorway.

    * `Outer`   2048^3 Subtract at (0, 0, 0)
    * `WallA`   256 x 128 x 256 Add at (-128, 0, 0)               — x in [-256, 0]
    * `WallB`   256 x 128 x 256 Add at (128, 0, 0)                — x in [0, 256]
    * `Doorway` 128 x 256 x 128 Subtract at (0, 0, -64)           — x in [-64, 64], z in [-128, 0],
      cut through the seam the two walls share

    A wall built from two blocks with a door cut through the join — about as ordinary as level
    geometry gets. The two Adds still meet across the whole x=0 plane above the doorway, but the
    CENTRE of that contact region is inside the doorway, so a predicate that probes the region once,
    at its centroid, reports that the wall touches nothing.
    """
    return _scenario([
        brush("Outer", (2048, 2048, 2048), (0, 0, 0), csg="subtract"),
        brush("WallA", (256, 128, 256), (-128, 0, 0)),
        brush("WallB", (256, 128, 256), (128, 0, 0)),
        brush("Doorway", (128, 256, 128), (0, 0, -64), csg="subtract"),
    ])


def _rotated_brush(name, size, centre, degrees: float):
    """A box of `size` whose centre is at `centre` (given UNROTATED, in the XY plane), with the whole
    thing turned `degrees` about the world Z axis. `builders._rotate_z` is the module's own rotation
    of a brush's vertices about its local origin, which is what a real rotated brush in a trunk
    carries — a `Rotation` property would instead have to be applied by every reader in step."""
    angle = math.radians(degrees)
    location = (centre[0] * math.cos(angle) - centre[1] * math.sin(angle),
                centre[0] * math.sin(angle) + centre[1] * math.cos(angle), 0)
    return make_brush_actor(name, builders._rotate_z(cube(*size), degrees),
                            location=_dec(tuple(round(c, 6) for c in location)))


def two_cubes_meeting_at_one_edge(degrees: float) -> Scenario:
    """Two 100-cubes placed corner to corner so they share EXACTLY ONE vertical edge and no area at
    all, with the whole configuration turned `degrees` about that edge.

    Trunk order: Outer, PrismA (centre (-50, -50)), PrismB (centre (50, 50)).

    An edge is not a contact. Unrotated the two footprints cancel to an area of exactly 0.0; rotated
    they cancel to float dust (1.9e-13 uu^2 at 30 degrees), which an exact `== 0` test reads as a
    real region. Rotated content is ordinary, so this is the shape that makes the area threshold
    have to be a tolerance.
    """
    return _scenario([
        brush("Outer", (4096, 4096, 4096), (0, 0, 0), csg="subtract"),
        _rotated_brush("PrismA", (100, 100, 100), (-50, -50), degrees),
        _rotated_brush("PrismB", (100, 100, 100), (50, 50), degrees),
    ])


def two_cubes_face_to_face(degrees: float) -> Scenario:
    """`two_cubes_meeting_at_one_edge`'s contrast: the same two cubes butted FACE to face over a
    full 100x100 square, turned `degrees` about the shared face's centre. A real contact at every
    angle."""
    return _scenario([
        brush("Outer", (4096, 4096, 4096), (0, 0, 0), csg="subtract"),
        _rotated_brush("PrismA", (100, 100, 100), (-50, 0), degrees),
        _rotated_brush("PrismB", (100, 100, 100), (50, 0), degrees),
    ])


# --------------------------------------------------------------------- Task 14's scenarios

def two_rooms_sharing_a_plane() -> Scenario:
    """Trunk order: Shell, RoomA, RoomB.

    * `Shell` 2048^3 Add at (0, 0, 0)               — solid matter for the rooms to carve
    * `RoomA` 512^3 Subtract at (-256, 0, 0)        — x in [-512, 0]
    * `RoomB` 512^3 Subtract at (256, 0, 0)         — x in [0, 512], sharing the x = 0 plane exactly

    The spec's disambiguation case: `connects`, never `touches` — nothing solid survives between
    them to be flush against.
    """
    return _scenario([
        brush("Shell", (2048, 2048, 2048), (0, 0, 0)),
        brush("RoomA", (512, 512, 512), (-256, 0, 0), csg="subtract"),
        brush("RoomB", (512, 512, 512), (256, 0, 0), csg="subtract"),
    ])


def two_rooms_split_by_an_intact_wall() -> Scenario:
    """Trunk order: Shell, RoomA, RoomB, Wall.

    Same two rooms, plus `Wall` 64 x 512 x 512 Add at (0, 0, 0) filling x in [-32, 32] — so the
    shared region between them is solid and the voids do not meet.
    """
    return _scenario([
        brush("Shell", (2048, 2048, 2048), (0, 0, 0)),
        brush("RoomA", (576, 512, 512), (-288, 0, 0), csg="subtract"),
        brush("RoomB", (576, 512, 512), (288, 0, 0), csg="subtract"),
        brush("Wall", (64, 512, 512), (0, 0, 0)),
    ])


def redundant_nested_subtract() -> Scenario:
    """Trunk order: Shell, OuterRoom, InnerCarve.

    * `Shell`      2048^3 Add at (0, 0, 0)
    * `OuterRoom`  512^3 Subtract at (0, 0, 0)
    * `InnerCarve` 128^3 Subtract at (0, 0, 0)   — entirely inside OuterRoom's already-void space

    `connects`, never `contains`: a redundant carve is not content.
    """
    return _scenario([
        brush("Shell", (2048, 2048, 2048), (0, 0, 0)),
        brush("OuterRoom", (512, 512, 512), (0, 0, 0), csg="subtract"),
        brush("InnerCarve", (128, 128, 128), (0, 0, 0), csg="subtract"),
    ])


# --------------------------------------------------------------------- Task 14 round 2

def _as_subtract(actor):
    """`actor` with its `CsgOper` forced to `CSG_Subtract` -- used to recast an existing Add-shaped
    fixture (e.g. a rotated-brush builder) without a second geometry helper."""
    props = [p for p in actor.props if p[0].casefold() != "csgoper"] + [("CsgOper", "CSG_Subtract")]
    return dataclasses.replace(actor, props=props)


def two_rotated_subtracts_meeting_off_centre(degrees: float) -> Scenario:
    """Two Subtract rooms of DIFFERENT sizes, offset along their shared seam (not centred at the
    same point or at the rotation origin), sharing a real coincident plane over only part of each
    footprint, the whole configuration turned `degrees` about Z.

    Built to defeat a sampling grid that only happens to land on a seam when the fixture is
    symmetric about the rotation centre -- a grid-based predicate can pass every symmetric rotated
    fixture and still miss this shape entirely, because the grid lands on the seam BY CONSTRUCTION
    in the symmetric case and nowhere near it here.

    Unrotated (`degrees=0`): `RoomA` 200 x 300 x 200 at (-100, 40, 0) -- its own +X face at x=0,
    y in [-110, 190]. `RoomB` 140 x 180 x 200 at (70, -60, 0) -- its own -X face at x=0, y in
    [-150, 30]. The shared x=0 patch is y in [-110, 30] (140 wide) x z in [-100, 100] (200 tall) --
    a real 28000 uu^2 area, off-centre for both rooms and for the rotation origin alike.
    """
    return _scenario([
        brush("Shell", (4096, 4096, 4096), (0, 0, 0)),
        _as_subtract(_rotated_brush("RoomA", (200, 300, 200), (-100, 40), degrees)),
        _as_subtract(_rotated_brush("RoomB", (140, 180, 200), (70, -60), degrees)),
    ])


def two_subtracts_meeting_at_one_edge(degrees: float) -> Scenario:
    """`two_cubes_meeting_at_one_edge`, recast as two Subtract rooms carved from a solid Shell
    instead of two Adds standing in a Subtract's void. An edge is not a contact for `connects`
    either -- the shared footprint at every candidate plane is a zero-area sliver."""
    return _scenario([
        brush("Shell", (4096, 4096, 4096), (0, 0, 0)),
        _as_subtract(_rotated_brush("PrismA", (100, 100, 100), (-50, -50), degrees)),
        _as_subtract(_rotated_brush("PrismB", (100, 100, 100), (50, 50), degrees)),
    ])


def mover_wrongly_tagged_as_subtract() -> Scenario:
    """A Mover carrying a stray `CsgOper=CSG_Subtract` prop -- something no `uedcli` builder emits
    (a Mover authors no `CsgOper` at all, `make_brush_actor`'s own docstring), but nothing stops an
    IMPORTED level's actor block from carrying one anyway. `kind_of`/`_kind` must still read it as
    `mover`, never as `subtract` from the raw prop alone -- a Mover is excluded from world CSG
    entirely and has no void of its own to be continuous with anything.

    Trunk order: Shell, Room, Door.
    * `Shell` 2048^3 Add at (0, 0, 0)
    * `Room`  512^3 Subtract at (0, 0, 0)
    * `Door`  64 x 8 x 128 `DeusEx.DeusExMover` at (0, 0, 0), fully inside `Room`'s void, with a
      stray `CsgOper=CSG_Subtract` prop forced onto it
    """
    door = make_brush_actor("Door", cube(64, 8, 128), location=_dec((0, 0, 0)),
                            mover_class="DeusEx.DeusExMover")
    door = dataclasses.replace(door, props=list(door.props) + [("CsgOper", "CSG_Subtract")])
    return _scenario([
        brush("Shell", (2048, 2048, 2048), (0, 0, 0)),
        brush("Room", (512, 512, 512), (0, 0, 0), csg="subtract"),
        door,
    ])


# --------------------------------------------------------------------- Task 14 round 3

def two_adds_meeting_off_centre(degrees: float) -> Scenario:
    """The `touches` twin of `two_rotated_subtracts_meeting_off_centre`: two DIFFERENTLY-SIZED Add
    rooms sharing a real coincident plane over only part of each footprint (not symmetric about the
    rotation origin), turned `degrees` about Z. Used to regress the shared `_self_consistent_plane`/
    `_reproject_uv` fix in `pair_touches` ITSELF -- review found the tolerance mismatch between
    `_same_plane` (1e-6) and `_cell_slice`'s near-parallel-face skip (1e-9) was already live in
    shipped `touches`, not just in the new `connects` code that first exposed it.

    Trunk order: Outer, RoomA, RoomB. `Outer` 4096^3 Subtract is the void the two Adds live in.
    Unrotated: `RoomA` 200 x 300 x 200 at (-100, 40, 0); `RoomB` 140 x 180 x 200 at (70, -60, 0) --
    the same shared x=0 patch as the connects fixture (y in [-110, 30], 140 x 200 = 28000 uu^2)."""
    return _scenario([
        brush("Outer", (4096, 4096, 4096), (0, 0, 0), csg="subtract"),
        _rotated_brush("RoomA", (200, 300, 200), (-100, 40), degrees),
        _rotated_brush("RoomB", (140, 180, 200), (70, -60), degrees),
    ])


def partial_merge_below_half_extent() -> Scenario:
    """Two Subtract rooms overlapping by a real 3-D volume that is well UNDER half of either room's
    own extent, and offset on all three axes -- no plane either room authors coincides with the
    other's, so this shape has no shared boundary plane at all, only a genuine interior overlap.

    Trunk order: Shell, RoomA, RoomB.
    * `Shell` 2048^3 Add at (0, 0, 0)
    * `RoomA` 300 x 400 x 300 Subtract at (150, 200, 150)  -- x,y,z in [0,300]/[0,400]/[0,300]
    * `RoomB` 300 x 400 x 300 Subtract at (350, 320, 250)  -- x,y,z in [200,500]/[120,520]/[100,400]

    Shared volume: x in [200,300] (100), y in [120,400] (280), z in [100,300] (200) -- a real
    100 x 280 x 200 uu^3 region, void on both sides. `RoomA`'s own centroid (150,200,150) is
    OUTSIDE `RoomB`'s extent and vice versa (RoomB's centroid (350,320,250) is outside RoomA's) --
    the exact shape a centroid-only containment test misses."""
    return _scenario([
        brush("Shell", (2048, 2048, 2048), (0, 0, 0)),
        brush("RoomA", (300, 400, 300), (150, 200, 150), csg="subtract"),
        brush("RoomB", (300, 400, 300), (350, 320, 250), csg="subtract"),
    ])


def doorway_off_the_probe_cross() -> Scenario:
    """Two Subtract rooms sharing a full 512 x 512 wall plane, split by an intact Wall with a real
    100 x 100 uu `Doorway` carved through it -- placed deliberately OFF the old 5-point probe
    pattern (the plane's own centre plus the four axis-aligned points ~170.67 uu out from it), so a
    fixed-point sample can walk right past a real, ordinary-sized opening.

    Trunk order: Shell, RoomA, RoomB, Wall, Doorway.
    * `Shell` 2048^3 Add at (0, 0, 0)
    * `RoomA` 576 x 512 x 512 Subtract at (-288, 0, 0)  -- x in [-576, 0]
    * `RoomB` 576 x 512 x 512 Subtract at (288, 0, 0)   -- x in [0, 576]
    * `Wall`  64 x 512 x 512 Add at (0, 0, 0)            -- x in [-32, 32], filling the seam
    * `Doorway` 64 x 100 x 100 Subtract at (0, 90, 90)   -- y,z in [40,140]/[40,140], clear of the
      probe cross (which sits at (0,0,0) and (0, +/-170.67, 0)/(0, 0, +/-170.67))
    """
    return _scenario([
        brush("Shell", (2048, 2048, 2048), (0, 0, 0)),
        brush("RoomA", (576, 512, 512), (-288, 0, 0), csg="subtract"),
        brush("RoomB", (576, 512, 512), (288, 0, 0), csg="subtract"),
        brush("Wall", (64, 512, 512), (0, 0, 0)),
        brush("Doorway", (64, 100, 100), (0, 90, 90), csg="subtract"),
    ])


# --------------------------------------------------------------------- the CSG-kind table

def kind_table_scenario() -> Scenario:
    """One actor of every kind the spec's `crosses` table names, all in one level, so the two
    eligibility tests read as a table rather than as seven separate fixtures. Geometry is
    irrelevant here — only the kinds are under test — so every brush is a 64^3 box on its own
    100uu step along +X.

    Trunk order: Adder, Semi, Nonsolid, Cutter, Inter, Deinter, Door, Lamp.
    """
    from uedcli.builders import PF_NOTSOLID
    door = make_brush_actor("Door", cube(64, 64, 64), location=_dec((600, 0, 0)),
                            mover_class="DeusEx.DeusExMover")
    return _scenario([
        brush("Adder", (64, 64, 64), (0, 0, 0)),
        brush("Semi", (64, 64, 64), (100, 0, 0), poly_flags=PF_SEMISOLID),
        brush("Nonsolid", (64, 64, 64), (200, 0, 0), poly_flags=PF_NOTSOLID),
        brush("Cutter", (64, 64, 64), (300, 0, 0), csg="subtract"),
        oper_brush("Inter", (64, 64, 64), (400, 0, 0), "CSG_Intersect"),
        oper_brush("Deinter", (64, 64, 64), (500, 0, 0), "CSG_Deintersect"),
        door,
        point("Lamp", (700, 0, 0)),
    ])


# --------------------------------------------------------------------- Task 16's scenarios

def nested_niche_with_a_decoration() -> Scenario:
    """The spec's nesting case, with the inner Add NOT poking through. Trunk order:
    Subtract1, Additive2, Subtract3, Additive4.

    * `Subtract1` 1024^3 Subtract at (0, 0, 0)
    * `Additive2` 256 x 64 x 256 Add at (0, 128, 0)
    * `Subtract3` 128 x 128 x 128 Subtract at (0, 128, 0)   — deliberately OVERSIZED past
      `Additive2`'s own y-extent, the routine way to avoid a coplanar face
    * `Additive4` 32 x 32 x 32 Add at (0, 128, 0)            — a decoration wholly inside Subtract3

    `Subtract3`'s authored volume (2097152) is far smaller than `Subtract1`'s (1073741824), so it
    wins the competition and `Subtract1` reports nothing about `Additive4` — even though `Subtract3`
    is not a strict subset of anything. That is the point of a VOLUME rule rather than a nesting one.
    """
    return _scenario([
        brush("Subtract1", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        brush("Additive2", (256, 64, 256), (0, 128, 0)),
        brush("Subtract3", (128, 128, 128), (0, 128, 0), csg="subtract"),
        brush("Additive4", (32, 32, 32), (0, 128, 0)),
    ])


def two_equal_volume_subtracts() -> Scenario:
    """A genuine tie. Trunk order: Shell, EarlierRoom, LaterRoom, Item.

    * `Shell`       2048^3 Add at (0, 0, 0)
    * `EarlierRoom` 512^3 Subtract at (0, 0, 0)
    * `LaterRoom`   512^3 Subtract at (0, 0, 0)   — the SAME box, so the volumes are exactly equal
    * `Item`        a point actor at (0, 0, 0)

    Both contain the Item and their volumes tie within the relative tolerance, so the tie breaks
    toward the LATER one in trunk order.
    """
    return _scenario([
        brush("Shell", (2048, 2048, 2048), (0, 0, 0)),
        brush("EarlierRoom", (512, 512, 512), (0, 0, 0), csg="subtract"),
        brush("LaterRoom", (512, 512, 512), (0, 0, 0), csg="subtract"),
        point("Item", (0, 0, 0)),
    ])


def mover_wrongly_tagged_as_subtract_competes_for_an_item() -> Scenario:
    """`mover_wrongly_tagged_as_subtract`'s own trap, aimed at `contains`'s container gate instead of
    `connects`'s: `Door` is a Mover carrying a stray `CsgOper=CSG_Subtract` prop, wholly inside
    `Room`'s void, with a much SMALLER authored volume than `Room` (65536 vs 134217728). If the
    container gate read the raw `CsgOper` prop instead of the actor's real kind, `Door` would wrongly
    enter the volume competition and WIN it by size, stealing `Item` from `Room`.

    Trunk order: Shell, Room, Door, Item.
    * `Shell` 2048^3 Add at (0, 0, 0)
    * `Room`  512^3 Subtract at (0, 0, 0)
    * `Door`  64 x 8 x 128 `DeusEx.DeusExMover` at (0, 0, 0), stray `CsgOper=CSG_Subtract`
    * `Item`  a point actor at (0, 0, 0) — inside both Room's and Door's own extents
    """
    door = make_brush_actor("Door", cube(64, 8, 128), location=_dec((0, 0, 0)),
                            mover_class="DeusEx.DeusExMover")
    door = dataclasses.replace(door, props=list(door.props) + [("CsgOper", "CSG_Subtract")])
    return _scenario([
        brush("Shell", (2048, 2048, 2048), (0, 0, 0)),
        brush("Room", (512, 512, 512), (0, 0, 0), csg="subtract"),
        door,
        point("Item", (0, 0, 0)),
    ])


# --------------------------------------------------------------------- Task 17's scenarios

def semisolid_pillar_straddled_by_a_subtract() -> Scenario:
    """Trunk order: Room, Pillar, Cutter — the same shape as `pillar_in_room`, but the pillar is
    SEMISOLID. The editor runs every Add/Subtract in its LOOP 2 and only then, after the
    repartition, the semisolid brushes in LOOP 3, so no Subtract in the trunk can ever remove a
    semisolid's matter, whatever trunk order says. Measured: the pillar keeps all 6 faces and its
    full 294912 uu^2 (`uedcli/tests/test_csg_kind_facts.py`).

    The sharpest raw-vs-csg contrast in the spec: raw `carves` claims this pair whenever trunk order
    looks right; csg never does.
    """
    return _scenario([
        brush("Room", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        brush("Pillar", (128, 128, 512), (0, 0, 0), poly_flags=PF_SEMISOLID),
        brush("Cutter", (256, 256, 256), (128, 0, 0), csg="subtract"),
    ])


def partial_and_total_carves() -> Scenario:
    """Trunk order: Shell, Room, Block, FirstCut, SecondCut, Gone, Eraser.

    * `Shell`     2048^3 Add at (0, 0, 0)
    * `Room`      1024^3 Subtract at (0, 0, 0)
    * `Block`     256^3 Add at (0, 0, 0)
    * `FirstCut`  128 x 512 x 512 Subtract at (-64, 0, 0)  — takes the block's -X half
    * `SecondCut` 256 x 512 x 512 Subtract at (0, 0, 0)    — covers FirstCut's region AND new matter
    * `Gone`      64^3 Add at (700, 0, 0)
    * `Eraser`    128^3 Subtract at (700, 0, 0)            — swallows `Gone` entirely

    Exercises three spec rules at once: `FirstCut` and `SecondCut` both carve `Block` (SecondCut's
    overlap is only partial, so it genuinely removes new matter); `Eraser` carves `Gone` even though
    nothing of `Gone` survives; and `Gone` gets no accompanying `touches`, because there is nothing
    left to be flush against.
    """
    return _scenario([
        brush("Shell", (2048, 2048, 2048), (0, 0, 0)),
        brush("Room", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        brush("Block", (256, 256, 256), (0, 0, 0)),
        brush("FirstCut", (128, 512, 512), (-64, 0, 0), csg="subtract"),
        brush("SecondCut", (256, 512, 512), (0, 0, 0), csg="subtract"),
        brush("Gone", (64, 64, 64), (700, 0, 0)),
        brush("Eraser", (128, 128, 128), (700, 0, 0), csg="subtract"),
    ])


# --------------------------------------------------------------------- Task 18's scenarios

def level_with_a_placed_intersect() -> Scenario:
    """Trunk order: Room, Inter. `Inter` is a placed `CSG_Intersect` brush — it contributes nothing
    whatever to the resolved world (`bspBrushCSG` dispatches it to a tail that rewrites the BRUSH's
    own model and never touches the world), so its csg tier is empty and its raw tier treats it as
    Add-like, which the resolved world does not."""
    return _scenario([
        brush("Room", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        oper_brush("Inter", (128, 128, 128), (0, 0, 0), "CSG_Intersect"),
    ])


# --------------------------------------------------------------------- Task 19's scenario

def truncation_probe_level() -> Scenario:
    """A level big enough that the neighborhood is a real subset, small enough to solve whole.

    Trunk order: Shell, then eight 256^3 Add pillars on a 1024uu grid at z = 0, then `Room`
    (a 512^3 Subtract at (0, 0, 0)) and `Probe` (a 128^3 Add at (200, 0, 0), flush against nothing,
    poking into Room's +X wall). Only Shell, Room, Probe and the two nearest pillars meet `Probe`'s
    region; the other six are identity on it.
    """
    actors = [brush("Shell", (4096, 4096, 1024), (0, 0, 0))]
    for i in range(8):
        actors.append(brush(f"Pillar{i}", (256, 256, 256), (1024 * (i - 4) + 512, 1024, 0)))
    actors.append(brush("Room", (512, 512, 512), (0, 0, 0), csg="subtract"))
    actors.append(brush("Probe", (128, 128, 128), (200, 0, 0)))
    return _scenario(actors)


def level_with_a_degenerate_brush() -> Scenario:
    """Trunk order: Room, BadBrush. `BadBrush` carries a PolyList that bounds no valid solid, so
    `decompose_convex` raises `DegenerateBrushError` naming it."""
    from uedcli.model import Brush, Polygon
    flat = Brush(model_name="Model_BadBrush", polys=[
        Polygon(vertices=[(Decimal(0), Decimal(0), Decimal(0)),
                          (Decimal(64), Decimal(0), Decimal(0)),
                          (Decimal(64), Decimal(64), Decimal(0))]),
    ])
    bad = make_brush_actor("BadBrush", flat, location=_dec((0, 0, 0)))
    return _scenario([brush("Room", (1024, 1024, 1024), (0, 0, 0), csg="subtract"), bad])


# ------------------------------------------------------------- final review: CLI-level error paths

def level_with_a_location_less_actor() -> Scenario:
    """Trunk order: Room, Ghost. `Ghost` is a non-brush actor with no `Location` at all -- surveying
    it directly must raise `ActorHasNoLocationError`, not fabricate a neighborhood around the world
    origin."""
    ghost = Actor(name="Ghost", cls="Engine.Light", location=None)
    return _scenario([brush("Room", (256, 256, 256), (0, 0, 0)), ghost])


def level_with_a_malformed_collision_neighbor() -> Scenario:
    """Trunk order: Room, Bad. `Bad` is a point actor next to `Room` with a `CollisionRadius` that
    parses but is out of domain (negative) -- surveying `Room` must raise `CollisionPropertyError`
    naming `Bad`, not silently invert its AABB or crash on a bare comparison."""
    bad = point("Bad", (100, 0, 0), props=[("bCollideActors", "True"), ("bBlockActors", "True"),
                                            ("CollisionRadius", "-30")])
    return _scenario([brush("Room", (256, 256, 256), (0, 0, 0)), bad])
