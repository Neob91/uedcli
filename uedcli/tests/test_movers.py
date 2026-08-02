from decimal import Decimal

import pytest

from uedcli.classindex import ClassRefError
from uedcli.model import Actor
from uedcli import movers
from uedcli.tests.conftest import StubClassIndex, install_system_root

IDX = StubClassIndex()          # the offline class resolver `movers.is_mover` needs


def _mover(props, location=None):
    return Actor(name="M", cls="Engine.Mover", props=list(props), location=location)


def test_is_mover_matches_engine_mover_and_subclasses_not_brush():
    assert movers.is_mover(Actor(name="a", cls="Engine.Mover"), IDX)
    assert movers.is_mover(Actor(name="b", cls="DeusEx.ElevatorMover"), IDX)
    assert movers.is_mover(Actor(name="c", cls="Mover"), IDX)       # bare — resolved via the index
    assert not movers.is_mover(Actor(name="d", cls="Engine.Brush"), IDX)
    assert not movers.is_mover(Actor(name="e", cls="Engine.Light"), IDX)
    assert not movers.is_mover(Actor(name="f", cls=""), IDX)        # classless brush


def test_is_mover_accepts_a_mover_subclass_whose_name_does_not_end_in_mover():
    # The bug the schema-aware gate fixes (board 9.4): both classes really extend
    # DeusEx.DeusExMover / Engine.Mover, but the old bare-name suffix guess rejected them, so
    # `mover key add CEDoor0` answered "is not a Mover".
    assert movers.is_mover(Actor(name="d", cls="CaroneElevatorSet.CEDoor"), IDX)
    assert movers.is_mover(Actor(name="c", cls="CaroneElevatorSet.CaroneElevator"), IDX)
    assert movers.is_mover(Actor(name="g", cls="DeusEx.BreakableGlass"), IDX)


def test_is_mover_rejects_a_class_that_only_ends_in_mover():
    # The other half of the same bug: the suffix guess ACCEPTED anything ending in "Mover". No such
    # class ships on this substrate today (every `*Mover` class on the real path really is a mover),
    # so this pins the RULE with a synthetic class rather than a live example.
    assert not movers.is_mover(Actor(name="p", cls="Synthetic.PaintRemover"), IDX)


# --- it answers or it raises: every unknowable case must fail, never return False ---------------

def test_is_mover_raises_when_the_index_cannot_resolve_engine_mover():
    # No class resolver (no games config / no packages on the path): answering False for every
    # actor would silently report every mover as a static brush, so it must FAIL instead.
    with pytest.raises(ClassRefError) as e:
        movers.is_mover(Actor(name="a", cls="Engine.Mover"), StubClassIndex(resolves=False))
    assert "Engine.Mover" in str(e.value) and "games config" in str(e.value)


def test_is_mover_raises_when_the_actors_own_class_is_off_the_search_path():
    # The narrower silent-False trap: the resolver works, but THIS class's package isn't on the
    # path, so an ancestry walk would answer False for a class that really is a mover.
    idx = StubClassIndex(unknown=("CaroneElevatorSet.CEDoor",))
    with pytest.raises(ClassRefError) as e:
        movers.is_mover(Actor(name="d", cls="CaroneElevatorSet.CEDoor"), idx)
    assert "CaroneElevatorSet.CEDoor" in str(e.value) and "search path" in str(e.value)


def test_is_mover_raises_when_the_ancestor_chain_truncates_before_the_root():
    # `ClassIndex.ancestry` truncates SILENTLY at a missing/unparseable ANCESTOR package; a chain
    # that stops short of Core.Object without hitting Engine.Mover is unknown, not "not a mover".
    idx = StubClassIndex(truncated=("SomeMod.CustomDoor",))
    with pytest.raises(ClassRefError) as e:
        movers.is_mover(Actor(name="d", cls="SomeMod.CustomDoor"), idx)
    assert "SomeMod.CustomDoor" in str(e.value) and "Core.Object" in str(e.value)


def test_is_mover_raises_on_an_unknown_bare_class():
    idx = StubClassIndex(unknown=("Nonesuch",))
    with pytest.raises(ClassRefError) as e:
        movers.is_mover(Actor(name="x", cls="Nonesuch"), idx)
    assert "Nonesuch" in str(e.value)


def test_is_mover_raises_when_bare_candidates_disagree():
    # A cross-package bare-name collision where one candidate is a mover and the other is not:
    # picking either would be a guess, and the point of the schema-aware gate is not to guess.
    idx = StubClassIndex(ambiguous={"Door": {"Engine.Mover", "SomePkg.Door"}})
    with pytest.raises(ClassRefError) as e:
        movers.is_mover(Actor(name="x", cls="Door"), idx)
    assert "Engine.Mover" in str(e.value) and "SomePkg.Door" in str(e.value)


# --- the same predicate against the REAL packages (pins the engine fact, not the stub) ----------

_INSTALL = install_system_root()
_HAVE_INSTALL = all((_INSTALL / f"{p}.u").is_file() for p in ("Core", "Engine", "DeusEx"))
# The case-sensitivity half of the finding needs lowercase-named mover classes, which only the TNM
# mod ships. Guarded SEPARATELY: a stock install must skip that half, not fail on a missing package.
_HAVE_TNM = (_INSTALL / "TNM.u").is_file()


@pytest.mark.skipif(not _HAVE_INSTALL, reason="v68 install (Core/Engine/DeusEx .u) not present")
def test_real_class_hierarchy_decides_mover_ness():
    """The load-bearing engine fact, read out of the game's own `.u` instead of a stub: real Mover
    subclasses whose class NAME does not end in `Mover` ARE movers, and ordinary actors are not.
    Without this, every mover assertion in this file only proves the stub was told the answer."""
    from uedcli.classindex import ClassIndex
    idx = ClassIndex.from_files([(p.stem, str(p)) for p in sorted(_INSTALL.glob("*.u"))])
    # Real movers the retired `bare.endswith("Mover")` guess REJECTED (dev/docs/direction/conventions.md 2026-07-25 10:18
    # UTC + its 11:31 UTC measurement note). (`CaroneElevatorSet.CEDoor`/`CaroneElevator`, the two the
    # item was filed for, live in a PROJECT overlay package rather than the game install, so they are
    # out of this index's reach.)
    rejected_by_the_old_guess = ["DeusEx.BreakableGlass", "DeusEx.BreakableWall"]
    if _HAVE_TNM:
        # Rejected purely because `endswith` is case-sensitive while UE1 `FName`s are not — the half
        # of the finding nothing else pins — plus one ordinary non-`*Mover` name.
        rejected_by_the_old_guess += ["TNM.Barricade", "TNM.fanmover", "TNM.platformmover",
                                      "TNM.weakmover"]
    for cls in ("Engine.Mover", "DeusEx.ElevatorMover", *rejected_by_the_old_guess):
        assert movers.is_mover(Actor(name="a", cls=cls), idx), f"{cls} should read as a Mover"
    for cls in ("Engine.Brush", "Engine.Light", "Engine.Trigger", "DeusEx.DeusExDecoration"):
        assert not movers.is_mover(Actor(name="a", cls=cls), idx), f"{cls} is not a Mover"
    # And the SHAPE of the measurement rather than counts, which are a property of whichever `.u`
    # files happen to sit in this install: strictly more classes descend from `Engine.Mover` than
    # match the name, and no name match is a non-mover — the two halves of "the retired guess was
    # wrong in one direction only, on this substrate". (The absolute figures behind the
    # `dev/docs/rationale/driver.md` 2026-07-25 11:31 UTC note are over the full composed path, which also carries
    # this project's overlay packages.)
    fqcns = idx._all_fqcns()
    descendants = {c for c in fqcns if idx.descends_from(c, "Engine.Mover")}
    suffixed = {c for c in fqcns if c.rpartition(".")[2].endswith("Mover")}
    assert suffixed < descendants, sorted(suffixed - descendants)   # proper subset: no false positive
    assert set(rejected_by_the_old_guess) <= descendants - suffixed


def test_num_keys_defaults_to_two_when_unset():
    assert movers.num_keys(_mover([])) == 2
    assert movers.num_keys(_mover([("NumKeys", "3")])) == 3


def test_mover_keys_reads_offsets_and_resolves_world_pose():
    a = _mover([("KeyPos(1)", "(Z=256.000000)"), ("KeyRot(1)", "(Yaw=16384)"),
                ("NumKeys", "2")], location=(Decimal(0), Decimal(0), Decimal("100")))
    keys = movers.mover_keys(a)              # list of (idx, off_pos, off_rot_uu)
    assert keys[0] == (0, (Decimal(0), Decimal(0), Decimal(0)), (0, 0, 0))
    assert keys[1] == (1, (Decimal(0), Decimal(0), Decimal("256")), (0, 16384, 0))


def test_set_key_pos_writes_indexed_prop_and_bumps_numkeys():
    a = _mover([], location=(Decimal(0), Decimal(0), Decimal(0)))
    movers.set_key_pos(a, 1, (Decimal(0), Decimal(0), Decimal("256")))
    assert ("KeyPos(1)", "(Z=256.000000)") in a.props
    assert movers.num_keys(a) == 2          # index 1 -> NumKeys 2


def test_it_keeps_numkeys_when_a_key_is_zeroed():
    # Engine fact (spike dev/docs/spikes/2026-07-20-mover-numkeys-trailing-zero): UnrealEd does
    # NOT auto-decrement NumKeys when a key's offset goes to zero — NumKeys is the authoritative
    # count, independent of which KeyPos/KeyRot lines are present. So zeroing a key must leave
    # NumKeys unchanged (the shrink is an explicit `remove`, never a side effect of setting zero).
    a = _mover([("KeyPos(5)", "(Z=256.000000)"), ("NumKeys", "6")],
               location=(Decimal(0), Decimal(0), Decimal(0)))
    movers.set_key_pos(a, 5, (Decimal(0), Decimal(0), Decimal(0)))
    assert "KeyPos(5)" not in dict(a.props)        # zero offset stores no line
    assert movers.num_keys(a) == 6                 # ...but the key still counts
    movers.set_key_rot(a, 3, (0, 0, 0))            # zeroing an interior rot key: same
    assert movers.num_keys(a) == 6


def test_set_num_keys_writes_count_and_omits_at_the_default():
    a = _mover([("NumKeys", "3")])
    movers.set_num_keys(a, 6)
    assert dict(a.props)["NumKeys"] == "6"
    movers.set_num_keys(a, 2)                # 2 is the editor default — the line is dropped
    assert "NumKeys" not in dict(a.props)


def test_set_num_keys_is_non_destructive_to_stored_offsets():
    a = _mover([("KeyPos(4)", "(Z=512.000000)"), ("NumKeys", "6")])
    movers.set_num_keys(a, 2)                # lowering keeps the now-dormant offset in place
    assert dict(a.props)["KeyPos(4)"] == "(Z=512.000000)"


def test_check_num_keys_rejects_out_of_range_naming_the_value():
    import pytest
    for bad in (-5, 0, 1, 9, 100):
        with pytest.raises(ValueError, match=f"NumKeys must be 2..8, got {bad}"):
            movers.check_num_keys(bad)
    movers.check_num_keys(2)                 # bounds inclusive — no raise
    movers.check_num_keys(8)


def test_remove_key_compacts_indices_and_decrements_numkeys():
    a = _mover([("KeyPos(1)", "(Z=128.000000)"), ("KeyPos(2)", "(Z=256.000000)"),
                ("KeyRot(2)", "(Yaw=16384)"), ("NumKeys", "3")])
    movers.remove_key(a, 1)
    props = dict(a.props)
    assert "KeyPos(2)" not in props          # old key 2 shifted down to 1
    assert props["KeyPos(1)"] == "(Z=256.000000)"
    assert props["KeyRot(1)"] == "(Yaw=16384)"
    assert props.get("NumKeys", "2") == "2"   # 2 is the default — omitted, per editor parity


def test_canonicalize_folds_keynum_offset_into_location_and_drops_keynum():
    a = _mover([("KeyNum", "2"), ("KeyPos(2)", "(Z=256.000000)"), ("NumKeys", "3")],
               location=(Decimal(0), Decimal(0), Decimal("356")))
    movers.canonicalize_mover(a, IDX)
    assert a.location == (Decimal(0), Decimal(0), Decimal("100"))   # 356 - 256
    assert "KeyNum" not in dict(a.props)
    assert dict(a.props)["KeyPos(2)"] == "(Z=256.000000)"          # offset unchanged
    # idempotent
    movers.canonicalize_mover(a, IDX)
    assert a.location == (Decimal(0), Decimal(0), Decimal("100"))
