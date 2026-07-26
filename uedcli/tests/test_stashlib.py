from decimal import Decimal

import pytest

from uedcli import stashlib
from uedcli.model import Actor, Brush, Polygon
from uedcli.writes import union_bounds


def _brush_actor(name, texture):
    poly = Polygon(texture=texture, vertices=[
        (Decimal(0), Decimal(0), Decimal(0)),
        (Decimal(64), Decimal(0), Decimal(0)),
        (Decimal(64), Decimal(64), Decimal(0)),
    ])
    return Actor(name=name, cls="Brush", brush=Brush(model_name="Model7", polys=[poly]))


def test_it_collects_texture_packages_only_skipping_engine_and_classes():
    arch = _brush_actor("Arch", "DeusExDeco.Stone.Block")
    light = Actor(name="L1", cls="Light")                     # bare exported class -> no pkg
    floor = _brush_actor("Floor", "Engine.DefaultTexture")   # Engine -> skip

    assert stashlib.referenced_packages([arch, light, floor]) == {"DeusExDeco"}


@pytest.mark.parametrize("bad", ["", "/abs", "..", "a/../b", "a/..", "x\\y", "a/ /b"])
def test_it_rejects_unsafe_member_names(bad):
    with pytest.raises(ValueError):
        stashlib.validate_member_name(bad)


@pytest.mark.parametrize("ok", ["arch_2", "hangar/archway", "a.b-c"])
def test_it_accepts_safe_member_names(ok):
    stashlib.validate_member_name(ok)        # no raise


def test_it_shifts_capture_to_bbox_min_origin_and_records_anchor():
    a = _brush_actor("Arch", "Engine.DefaultTexture")
    a.location = (Decimal(100), Decimal(200), Decimal(50))

    shifted, anchor = stashlib.normalize_for_capture([a])

    assert anchor == (Decimal(100), Decimal(200), Decimal(50))   # original world bbox-min
    lo, _hi = union_bounds(shifted)
    assert lo == (Decimal(0), Decimal(0), Decimal(0))


def test_it_rejects_capturing_an_empty_set():
    with pytest.raises(ValueError, match="no actors"):
        stashlib.normalize_for_capture([])


def test_it_translates_actors_by_a_delta():
    a = _brush_actor("Arch", "Engine.DefaultTexture")
    a.location = (Decimal(0), Decimal(0), Decimal(0))

    moved = stashlib.translate([a], (Decimal(512), Decimal(0), Decimal(128)))

    assert moved[0].location == (Decimal(512), Decimal(0), Decimal(128))


def test_it_sets_group_and_keeps_other_props():
    a = _brush_actor("Arch", "Engine.DefaultTexture")
    a.props = [("CsgOper", "CSG_Add"), ("Group", "old")]

    b = stashlib.with_group(a, "archway")

    assert ("Group", "archway") in b.props
    assert ("Group", "old") not in b.props
    assert ("CsgOper", "CSG_Add") in b.props          # untouched


def test_it_removes_group_when_none():
    a = _brush_actor("Arch", "Engine.DefaultTexture")
    a.props = [("Group", "old")]
    assert all(k != "Group" for k, _ in stashlib.with_group(a, None).props)


def test_it_formats_a_set_summary():
    a = _brush_actor("Arch", "Engine.DefaultTexture")
    a.location = (Decimal(0), Decimal(0), Decimal(0))
    text = stashlib.format_summary("archway", [a])
    assert "archway" in text and "Arch" in text and "Brush" in text


_ARCH_BLOB = "Begin Actor Class=Engine.Brush Name=Arch\n    CsgOper=CSG_Add\nEnd Actor\n"


def test_it_writes_and_reads_a_prefab(tmp_path):
    # A prefab is now a per-actor T3D tree (dir), NOT a single .t3d + .json. read_prefab returns
    # CANONICAL T3D (parse -> emit round-trip), so the read-back is the canonical form.
    full = {"Arch": _ARCH_BLOB}
    stashlib.write_prefab(tmp_path, "hangar/archway", full_level=full, order=["Arch"],
                          packages=["DeusExDeco"], meta={"anchor": ["0", "0", "0"], "ts": 1})
    assert (tmp_path / "hangar" / "archway" / "actors" / "Arch" / "actor.t3d").is_file()
    assert (tmp_path / "hangar" / "archway" / "meta.json").is_file()
    assert (tmp_path / "hangar" / "archway" / "packages").is_file()
    actors, order, packages, meta, folders = stashlib.read_prefab(tmp_path, "hangar/archway")
    assert order == ["Arch"] and packages == ["DeusExDeco"]
    assert "Begin Actor Class=Engine.Brush Name=Arch" in actors["Arch"]
    assert meta == {"anchor": ["0", "0", "0"], "ts": 1}   # split-sibling: ONLY capture extras
    assert folders == {"Arch": None}
    assert stashlib.list_prefabs(tmp_path) == ["hangar/archway"]


def test_it_persists_a_per_member_folder_in_a_prefab(tmp_path):
    stashlib.write_prefab(tmp_path, "p", full_level={"Arch": _ARCH_BLOB}, order=["Arch"],
                          packages=[], meta={}, folders={"Arch": "wing.left"})
    assert (tmp_path / "p" / "actors" / "Arch" / "folder").read_text().strip() == "wing.left"
    _a, _o, _p, _m, folders = stashlib.read_prefab(tmp_path, "p")
    assert folders == {"Arch": "wing.left"}


def test_it_reads_an_old_format_prefab_as_a_hard_cutover_error(tmp_path):
    # HARD CUTOVER (decisions 2026-07-18 addendum, sub-choice 1): an old single-blob prefab is NOT
    # auto-converted; read raises a clean, actionable OldFormatPrefab (never a traceback), and the
    # name still LISTS so the error surfaces on use rather than a misleading "not found".
    (tmp_path / "old.t3d").write_text("Begin Map\n" + _ARCH_BLOB + "End Map\n")
    (tmp_path / "old.json").write_text('{"order": ["Arch"], "packages": []}')
    assert "old" in stashlib.list_prefabs(tmp_path)
    with pytest.raises(stashlib.OldFormatPrefab, match="old-format prefab 'old' — re-capture it"):
        stashlib.read_prefab(tmp_path, "old")


def test_it_refuses_to_overwrite_a_prefab_without_force(tmp_path):
    full = {"Arch": _ARCH_BLOB}
    stashlib.write_prefab(tmp_path, "a", full_level=full, order=["Arch"], packages=[], meta={})
    with pytest.raises(FileExistsError):
        stashlib.write_prefab(tmp_path, "a", full_level=full, order=["Arch"], packages=[], meta={})
    stashlib.write_prefab(tmp_path, "a", full_level=full, order=["Arch"], packages=[], meta={},
                          force=True)        # force overwrites


def test_it_refuses_a_prefab_name_that_escapes_the_root(tmp_path):
    with pytest.raises(ValueError):
        stashlib.write_prefab(tmp_path, "../escape", full_level={}, order=[], packages=[], meta={})
