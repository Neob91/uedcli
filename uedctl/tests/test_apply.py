import errno
from unittest import mock

import pytest

from uedctl import apply as applymod
from uedctl.apply import _install_atomic


def _t3d(cls, name):
    return f'Begin Actor Class={cls} Name={name}\n    Name="{name}"\nEnd Actor\n'


def test_materialized_order_puts_levelinfo_first():
    result = {"B1": "Begin Actor Class=Brush Name=B1\n    Name=\"B1\"\nEnd Actor\n",
              "LI": "Begin Actor Class=LevelInfo Name=LI\n    Name=\"LI\"\nEnd Actor\n"}
    assert applymod._materialized_order(result, ["B1", "LI"]) == ["LI", "B1"]


def test_level_referenced_packages_derives_from_texture_and_class_refs():
    # Only the packages the level's own actors reference (qualified Class= + poly Texture=), NOT the
    # whole composed install — the mass-load reliability fix (decision 2026-07-14).
    from uedctl.model import Actor, Brush, Level, Polygon
    lvl = Level()
    b = Actor(name="B", cls="Engine.Brush")
    b.brush = Brush(model_name="Model0", polys=[
        Polygon(texture="LUM_CoreTex.Tile.grey_stone_tile"),   # -> LUM_CoreTex
        Polygon(texture="grey_stone_tile"),                    # bare -> no package (rides Paths)
        Polygon(texture=None)])                                # untextured -> nothing
    lvl.actors["B"] = b
    lvl.actors["L"] = Actor(name="L", cls="DeusEx.DeusExLight")  # -> DeusEx
    lvl.actors["Bare"] = Actor(name="Bare", cls="Light")        # bare class -> nothing
    # "Engine" (from Engine.Brush) is INCLUDED here; obj_load_entries' _ALWAYS_LOADED filter drops
    # it downstream, not this helper.
    assert applymod._level_referenced_packages(lvl) == ["DeusEx", "Engine", "LUM_CoreTex"]


def test_level_referenced_packages_empty_for_a_bare_engine_only_level():
    from uedctl.model import Actor, Level
    lvl = Level()
    lvl.actors["L"] = Actor(name="L", cls="Light")             # bare, no package
    assert applymod._level_referenced_packages(lvl) == []


def test_install_atomic_replaces_target_from_the_default_staging_dir(tmp_path):
    staging = tmp_path / "staging.dx"; staging.write_bytes(b"NEWBYTES")
    target = tmp_path / "Maps" / "Foo.dx"; target.parent.mkdir()
    target.write_bytes(b"OLDBYTES")
    _install_atomic(staging_host=str(staging), target_host=str(target))
    assert target.read_bytes() == b"NEWBYTES"
    assert not staging.exists()                       # moved, not copied


def test_install_atomic_falls_back_to_a_target_dir_temp_on_exdev(tmp_path):
    # The fallback copies the HOST staging bytes directly (no re-fetch from any container --
    # the bytes are already on the host by the time _install_atomic runs), so this only needs
    # to fake os.replace, not a docker seam.
    staging = tmp_path / "staging.dx"; staging.write_bytes(b"NEWBYTES")
    target = tmp_path / "Foo.dx"; target.write_bytes(b"OLDBYTES")
    real_replace = __import__("os").replace
    calls = {"n": 0}
    def replace_raising_exdev_once(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:                            # the .uedctl/tmp -> target attempt
            raise OSError(errno.EXDEV, "cross-device link")
        return real_replace(src, dst)                  # the target-dir temp -> target attempt
    with mock.patch("uedctl.apply.os.replace", side_effect=replace_raising_exdev_once):
        _install_atomic(staging_host=str(staging), target_host=str(target))
    assert target.read_bytes() == b"NEWBYTES"
    assert not staging.exists()                         # cleaned up
    assert calls["n"] == 2                               # one EXDEV attempt + one successful rename


def test_install_atomic_cleans_up_the_target_dir_temp_if_the_final_rename_fails(tmp_path):
    # Reviewer-flagged leak (finding 4): on the EXDEV path, a failure in the SECOND os.replace
    # (target-dir-tmp -> target) must not strand the dotfile beside the target -- that is
    # exactly the leak class this whole change exists to kill.
    staging = tmp_path / "staging.dx"; staging.write_bytes(b"NEWBYTES")
    target = tmp_path / "Foo.dx"; target.write_bytes(b"OLDBYTES")
    def replace_raising_exdev_then_failing(src, dst):
        if src == str(staging):
            raise OSError(errno.EXDEV, "cross-device link")
        raise OSError(errno.EACCES, "permission denied")     # the target-dir-tmp -> target rename
    with mock.patch("uedctl.apply.os.replace", side_effect=replace_raising_exdev_then_failing):
        with pytest.raises(OSError):
            _install_atomic(staging_host=str(staging), target_host=str(target))
    leftovers = [p for p in tmp_path.iterdir()
                if p.name.startswith(".") and p.name.endswith(".uedctl-tmp.dx")]
    assert leftovers == []                               # no dotfile stranded beside the target
