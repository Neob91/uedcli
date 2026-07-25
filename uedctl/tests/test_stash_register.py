import pytest

from uedctl import stash_register


# A realistic brush actor blob (a Begin Brush model, a CsgOper) so it round-trips through the shared
# per-actor tree exactly as the trunk would store it.
_ARCH = (
    "Begin Actor Class=Engine.Brush Name=Arch\n"
    "    CsgOper=CSG_Add\n"
    "    Begin Brush Name=Model_Arch\n"
    "    End Brush\n"
    "    Brush=Model'MyLevel.Model_Arch'\n"
    '    Name="Arch"\n'
    "End Actor\n"
)


def _write(reg, sid="arch", **kw):
    reg.write_stash(
        sid,
        full_level={"Arch": _ARCH},
        order=["Arch"],
        packages=["CoreTex"],
        meta={"anchor": ["0", "0", "0"], "ts": 1234567890},
        **kw,
    )


def test_it_roundtrips_write_read_list_drop(tmp_path):
    reg = stash_register.FileStashRegister(tmp_path / "stash")

    _write(reg)

    assert reg.list_stashes() == ["arch"]
    actors, order, packages, meta, folders = reg.read_stash("arch")
    assert order == ["Arch"]
    assert packages == ["CoreTex"]
    assert meta == {"anchor": ["0", "0", "0"], "ts": 1234567890}
    assert "Arch" in actors and "Class=Engine.Brush" in actors["Arch"]
    assert folders == {"Arch": None}

    # The stored tree is the SHARED per-actor layout, not the old flat form.
    assert (reg.root / "arch" / "actors" / "Arch" / "actor.t3d").is_file()
    assert (reg.root / "arch" / "actors" / "Arch" / "order_value").is_file()
    assert (reg.root / "arch" / "meta.json").is_file()
    assert (reg.root / "arch" / "packages").is_file()
    # The stored body has its identity tokens stripped (dir name IS the identity).
    assert "Name=Arch" not in (reg.root / "arch" / "actors" / "Arch" / "actor.t3d").read_text()

    reg.drop_stash("arch")
    assert reg.list_stashes() == []


def test_it_persists_a_per_member_folder_sidecar(tmp_path):
    reg = stash_register.FileStashRegister(tmp_path / "stash")
    reg.write_stash("f", full_level={"Arch": _ARCH}, order=["Arch"], packages=[],
                    meta={}, folders={"Arch": "castle.tower"})
    assert (reg.root / "f" / "actors" / "Arch" / "folder").read_text().strip() == "castle.tower"
    _actors, _order, _pkgs, _meta, folders = reg.read_stash("f")
    assert folders == {"Arch": "castle.tower"}


def test_it_rejects_a_path_hostile_actor_name(tmp_path):
    # The old flat store percent-encoded hostile names; the unified tree makes the dir name the
    # identity VERBATIM and rejects anything that isn't a safe single segment (a real engine object
    # name never contains '/'). The failure is a clean, value-naming ValueError.
    reg = stash_register.FileStashRegister(tmp_path / "stash")
    with pytest.raises(ValueError, match="A/B Light"):
        reg.write_stash(
            "weird",
            full_level={"A/B Light": "Begin Actor Class=Engine.Light Name=x\nEnd Actor\n"},
            order=["A/B Light"],
            packages=[],
            meta={},
        )


def test_it_refuses_overwrite_without_force(tmp_path):
    reg = stash_register.FileStashRegister(tmp_path / "stash")
    _write(reg)

    with pytest.raises(FileExistsError):
        _write(reg)

    # force clears the prior tree entirely (an empty rewrite must leave no ghost actors)
    reg.write_stash("arch", full_level={}, order=[], packages=[], meta={}, force=True)
    actors, order, _packages, _meta, _folders = reg.read_stash("arch")
    assert actors == {} and order == []


def test_it_preserves_surviving_ranks_across_a_rewrite(tmp_path):
    # A rewrite must keep an unchanged member's order_value byte-identical (merge-clean, no churn).
    reg = stash_register.FileStashRegister(tmp_path / "stash")
    reg.write_stash("s", full_level={"Arch": _ARCH, "Arch2": _ARCH.replace("Arch", "Arch2")},
                    order=["Arch", "Arch2"], packages=[], meta={})
    rv_before = (reg.root / "s" / "actors" / "Arch" / "order_value").read_text()
    # rewrite with an extra actor appended
    reg.write_stash("s", full_level={"Arch": _ARCH, "Arch2": _ARCH.replace("Arch", "Arch2"),
                                     "Arch3": _ARCH.replace("Arch", "Arch3")},
                    order=["Arch", "Arch2", "Arch3"], packages=[], meta={}, force=True)
    rv_after = (reg.root / "s" / "actors" / "Arch" / "order_value").read_text()
    assert rv_before == rv_after                        # surviving actor's rank unchanged
    _a, order, _p, _m, _f = reg.read_stash("s")
    assert order == ["Arch", "Arch2", "Arch3"]          # new actor appended after


def test_it_reads_missing_as_empty_like_the_store(tmp_path):
    reg = stash_register.FileStashRegister(tmp_path / "stash")

    # An unknown id returns empties (never raises), mirroring the trunk source's missing-level read.
    assert reg.read_stash("nope") == ({}, [], [], {}, {})
    assert reg.list_stashes() == []
    reg.drop_stash("nope")  # idempotent no-op, like `git rm --ignore-unmatch`


def test_it_treats_a_stale_flat_stash_as_absent(tmp_path):
    # An old FLAT-format entry (loose actors/<name>.t3d files + shared order) is treated as fully
    # absent — read-empty AND exists()==False — so a --target edit says a clean "not found" instead
    # of silently touching zero actors while meta.json survives.
    reg = stash_register.FileStashRegister(tmp_path / "stash")
    stale = reg.root / "old"
    (stale / "actors").mkdir(parents=True)
    (stale / "actors" / "Arch.t3d").write_text(_ARCH)
    (stale / "order").write_text("Arch\n")
    (stale / "meta.json").write_text("{}")
    assert reg.read_stash("old") == ({}, [], [], {}, {})
    assert reg.exists("old") is False


def test_it_omits_phantom_dirs_from_the_listing(tmp_path):
    reg = stash_register.FileStashRegister(tmp_path / "stash")
    _write(reg, "real")

    # A leftover staging dir (crashed/concurrent write) and an empty parent from a nested-id drop
    # must NOT surface as stashes — only dirs carrying a meta.json count.
    (reg.root / ".staging" / "tmp-half-written").mkdir(parents=True)
    (reg.root / "empty-parent").mkdir()

    assert reg.list_stashes() == ["real"]


def test_it_rejects_an_unsafe_id(tmp_path):
    reg = stash_register.FileStashRegister(tmp_path / "stash")
    with pytest.raises(ValueError):
        reg.write_stash("../escape", full_level={}, order=[], packages=[], meta={})
