from decimal import Decimal

from uedcli.model import parse_t3d
from uedcli.rotation import best_grid_pivot


def _lvl(t3d):
    return list(parse_t3d("Begin Map\n" + t3d + "End Map\n").actors.values())


def test_an_unauthored_location_resolves_to_the_CLASS_default():
    """EVERY actor has an effective Location: an unauthored property takes its **class default**.
    That is why there is no fallback rule — and why the default is NOT assumed to be zero.
    `Engine.Camera` really defaults `Location=(X=-500,Y=-300,Z=300)` (verified live against the
    LUM packages), and `architecture.md` records assuming zero as the bug the typed compare exists
    to remove: a Camera cleared to None once re-imported 655 uu away."""
    cam = _lvl("Begin Actor Class=Engine.Camera Name=C\n    Name=\"C\"\nEnd Actor\n")
    assert best_grid_pivot(cam, lambda fq: (Decimal(-500), Decimal(-300), Decimal(300))) == (
        Decimal(-500), Decimal(-300), Decimal(300))
    # …and a class that does NOT default Location still resolves to the origin.
    assert best_grid_pivot(cam, lambda fq: None) == (Decimal(0), Decimal(0), Decimal(0))


def test_an_unauthored_location_without_a_resolver_is_the_origin():
    """With no `class_default` supplied the origin is used — correct for every class that does not
    default `Location`, which is nearly all of them."""
    actors = _lvl(
        "Begin Actor Class=Brush Name=B\n"
        "    Begin Brush Name=M\n       Begin PolyList\n         Begin Polygon\n"
        "          Vertex +255.000000,+0.000000,+0.000000\n"
        "          Vertex +256.000000,+256.000000,+0.000000\n"
        "          Vertex +260.000000,+0.000000,+0.000000\n         End Polygon\n"
        "       End PolyList\n    End Brush\n    Name=\"B\"\nEnd Actor\n")
    assert best_grid_pivot(actors) == (Decimal(0), Decimal(0), Decimal(0))


def test_fractional_point_locations_are_used_as_authored():
    """Two lights equidistant from the centre tie, so the alphabetically first Name supplies the pivot —
    verbatim, fraction intact. Nothing is averaged and nothing is snapped onto the integer grid."""
    actors = _lvl(
        "Begin Actor Class=Light Name=L1\n    Location=(X=10.500000,Y=0.500000,Z=0.500000)\n    Name=\"L1\"\nEnd Actor\n"
        "Begin Actor Class=Light Name=L2\n    Location=(X=20.500000,Y=0.500000,Z=0.500000)\n    Name=\"L2\"\nEnd Actor\n")
    assert best_grid_pivot(actors) == (Decimal("10.5"), Decimal("0.5"), Decimal("0.5"))


def _brush(name, loc, verts):
    vs = "".join(f"          Vertex {x:+.6f},{y:+.6f},{z:+.6f}\n" for x, y, z in verts)
    return (f"Begin Actor Class=Brush Name={name}\n    Location=(X={loc[0]},Y={loc[1]},Z={loc[2]})\n"
            f"    Begin Brush Name=M\n       Begin PolyList\n         Begin Polygon\n"
            f"{vs}         End Polygon\n       End PolyList\n    End Brush\n"
            f"    Name=\"{name}\"\nEnd Actor\n")


def _point(name, loc):
    return (f"Begin Actor Class=Light Name={name}\n"
            f"    Location=(X={loc[0]},Y={loc[1]},Z={loc[2]})\n    Name=\"{name}\"\nEnd Actor\n")


# ── the own-pivot rule: rotate about a member's AUTHORED Location ─────────────────────────────────

def _cube_at(name, at, side=128):
    """A real generator cube, the form `brush build cube --at` produces: local vertices about the
    origin, world position carried by Location — so the Location IS inside its own world bounds."""
    from uedcli.builders import cube, make_brush_actor
    return make_brush_actor(name, cube(side, side, side),
                            location=tuple(Decimal(str(c)) for c in at))


def test_a_brush_pivots_on_its_own_location():
    """The point that stays fixed when a brush turns about itself IS its Location, so a lone brush
    turns in place — no synthesized coordinate, and the pivot inherits whatever grid it was authored
    on."""
    assert best_grid_pivot([_cube_at("B", (64, 64, 0))]) == (Decimal(64), Decimal(64), Decimal(0))


def test_a_raw_csg_brush_contributes_its_location_unfiltered():
    """Owner decision, 2026-07-26: use the Location of the closest brush, as authored — no filtering
    on whether it sits near the actor's geometry. `Location=(0,0,0)` with WORLD-space vertices is a
    real shipped form (five `revolve` brushes in the TubePlatform trunk carry it, with geometry at
    Y≈1300), so such a set pivots about the world ORIGIN and swings accordingly. `--pivot X,Y,Z` and
    `--pivot-actor` are the escape hatch. Pinned so the behaviour is a recorded choice, not a
    surprise."""
    actors = _lvl(_brush("Bore", (0, 0, 0),
                         [(0, 1216, 128), (0, 1248, 272), (64, 1248, 128)]))
    assert best_grid_pivot(actors) == (Decimal(0), Decimal(0), Decimal(0))


def test_a_lone_point_actor_turns_in_place_and_is_never_snapped():
    """Point actors are usually off-grid, and snapping one would MOVE it. Its Location is the pivot
    verbatim, fraction and all."""
    actors = _lvl(_point("Prop", ("1013.500000", "227.250000", "41.000000")))
    assert best_grid_pivot(actors) == (Decimal("1013.5"), Decimal("227.25"), Decimal("41"))


def test_actors_sharing_one_location_rotate_about_themselves():
    """A zero-extent selection collapses to one point, and that point is the pivot exactly — no
    rounding, no snapping, whatever fraction the Location carries."""
    loc = ("512.250000", "64.750000", "8.000000")
    actors = _lvl(_point("A", loc) + _point("B", loc) + _point("C", loc))
    assert best_grid_pivot(actors) == (Decimal("512.25"), Decimal("64.75"), Decimal(8))


def test_the_member_nearest_the_bbox_centre_supplies_the_pivot():
    # bbox spans x -64..576, centre 256 — exactly `Mid`'s own Location, and it is the sole nearest.
    actors = [_cube_at("Left", (0, 0, 0)), _cube_at("Mid", (256, 0, 0)),
              _cube_at("Right", (512, 0, 0))]
    assert best_grid_pivot(actors) == (Decimal(256), Decimal(0), Decimal(0))


# ── ties: the alphabetically first Name, never an average ────────────────────────────────────────

def test_a_two_way_tie_takes_the_alphabetically_first_name():
    """Owner ruling, 2026-07-26: equidistant members are NOT averaged — the alphabetically first Name
    wins, so the pivot stays a Location that exists in the trunk."""
    actors = [_cube_at("Bravo", (0, 0, 0)), _cube_at("Alpha", (256, 0, 0))]
    assert best_grid_pivot(actors) == (Decimal(256), Decimal(0), Decimal(0))    # Alpha's Location
    # Name decides it, NOT the order the set arrived in — reversing the list changes nothing.
    assert best_grid_pivot(list(reversed(actors))) == (Decimal(256), Decimal(0), Decimal(0))


def test_a_three_way_tie_takes_one_name_and_stays_on_grid():
    """B, C and D are all equidistant from the centre. Averaging them divided by three and produced
    `341.333333, 256, 21.333333`, which put every brush in the set off-grid; taking the alphabetically
    first of the tied Names keeps the pivot an authored, on-grid Location."""
    actors = [_cube_at("A", (0, 0, 0)), _cube_at("B", (256, 0, 0)),
              _cube_at("C", (512, 256, 0)), _cube_at("D", (256, 512, 64))]
    assert best_grid_pivot(actors) == (Decimal(256), Decimal(0), Decimal(0))      # B, not C or D


def test_the_containeryard_sheet_flips_in_place():
    """A 128x128 XZ sheet as `brush build sheet --at 1056,228,112` emits it: local vertices, world
    position in Location. The old rule pivoted about the MIN CORNER (992,228,48) and swung it a full
    128 uu onto a gate post; its own Location is the pivot now, so the flip is in place."""
    actors = _lvl(_brush("S", (1056, 228, 112),
                         [(-64, 0, -64), (64, 0, -64), (64, 0, 64), (-64, 0, 64)]))
    assert best_grid_pivot(actors) == (Decimal(1056), Decimal(228), Decimal(112))


def test_best_grid_pivot_uses_point_actor_locations():
    actors = _lvl(
        "Begin Actor Class=Light Name=L1\n    Location=(X=128.000000,Y=128.000000,Z=0.000000)\n    Name=\"L1\"\nEnd Actor\n"
        "Begin Actor Class=Light Name=L2\n    Location=(X=130.000000,Y=2.000000,Z=0.000000)\n    Name=\"L2\"\nEnd Actor\n")
    # Both are equidistant from the bbox centre (129,65,0), so the alphabetically first Name wins.
    assert best_grid_pivot(actors) == (Decimal(128), Decimal(128), Decimal(0))
