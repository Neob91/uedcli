"""`audioindex` — offline audio enumeration + the name-keyed identity/collision rule (audio arm A1).

Synthetic `.uax`/`.umx` fixtures for the collision rule (latent, not live on Deus Ex) and the
resolve directions; a real-corpus offline assertion over the git-tracked `uned/UED22` `DeusExSounds.u`
for the enumeration + golden group structure.
"""
from __future__ import annotations

import glob
from collections import Counter

import pytest

from uedcli import audioindex
from uedcli.tests import audiofixture as af
from uedcli.tests.conftest import ued22_root

# The golden DeusExSounds group structure (spike measure.py:_GOLDEN_DEUSEXSOUNDS_GROUPS).
GOLDEN_GROUPS = {"Weapons": 91, "Generic": 85, "Animal": 57, "Player": 56, "Robot": 40,
                 "Special": 38, "UserInterface": 17, "Augmentation": 7, "Pickup": 5, "NPC": 3}


def _write(tmp_path, filename, **kw):
    p = tmp_path / filename
    p.write_bytes(af.audio_package(**kw))
    return (str(p), "fixture")


# --------------------------------------------------------------------------- enumeration

def test_enumerates_sound_exports_with_dotted_refs_and_groups(tmp_path):
    f = _write(tmp_path, "Fx.uax", name="Fx", kind="sound",
               objects=[("Weapons", "PistolShot"), ("Ambient", "Wind")])
    idx = audioindex.AudioIndex.from_files([f], "sound")
    got = {e.ref: (e.identity, e.group, e.package) for e in idx.entries}
    assert got == {
        "Fx.Weapons.PistolShot": ("Fx.PistolShot", "Weapons", "Fx"),
        "Fx.Ambient.Wind": ("Fx.Wind", "Ambient", "Fx"),
    }


def test_music_export_is_enumerated_for_kind_music_not_sound(tmp_path):
    f = _write(tmp_path, "Theme.umx", name="Theme", kind="music",
               objects=[(None, "Theme")], embed=af.it_module("Main Theme"))
    assert [e.ref for e in audioindex.AudioIndex.from_files([f], "music").entries] == ["Theme.Theme"]
    assert audioindex.AudioIndex.from_files([f], "sound").entries == ()


def test_a_root_object_has_a_two_part_ref_and_no_group(tmp_path):
    f = _write(tmp_path, "Fx.uax", name="Fx", kind="sound", objects=[(None, "Beep")])
    (e,) = audioindex.AudioIndex.from_files([f], "sound").entries
    assert (e.ref, e.identity, e.group) == ("Fx.Beep", "Fx.Beep", None)


# --------------------------------------------------------------------------- collision rule

def test_bare_name_collision_promotes_both_to_three_part_identities(tmp_path):
    """Two same-bare-name sounds in different groups of one package → the full dotted identity for
    BOTH; a unique bare name in the same package stays 2-part."""
    f = _write(tmp_path, "Fx.uax", name="Fx", kind="sound",
               objects=[("Weapons", "Bang"), ("Ammo", "Bang"), ("Weapons", "Unique")])
    ids = {e.ref: e.identity for e in audioindex.AudioIndex.from_files([f], "sound").entries}
    assert ids == {
        "Fx.Weapons.Bang": "Fx.Weapons.Bang",
        "Fx.Ammo.Bang": "Fx.Ammo.Bang",
        "Fx.Weapons.Unique": "Fx.Unique",
    }


def test_same_bare_name_in_two_different_packages_is_not_a_collision(tmp_path):
    """Uniqueness is WITHIN a package — the same bare name in two packages stays 2-part in each."""
    a = _write(tmp_path, "A.uax", name="A", kind="sound", objects=[("G", "Bang")])
    b = _write(tmp_path, "B.uax", name="B", kind="sound", objects=[("G", "Bang")])
    ids = {e.ref: e.identity for e in audioindex.AudioIndex.from_files([a, b], "sound").entries}
    assert ids == {"A.G.Bang": "A.Bang", "B.G.Bang": "B.Bang"}


# --------------------------------------------------------------------------- resolve

@pytest.fixture
def resolver(tmp_path):
    f = _write(tmp_path, "Fx.uax", name="Fx", kind="sound",
               objects=[("Weapons", "PistolShot"), ("Weapons", "Bang"), ("Ammo", "Bang")])
    return audioindex.AudioIndex.from_files([f], "sound")


def test_resolve_dotted_ref_reduces_to_the_two_part_identity(resolver):
    assert resolver.resolve("Fx.Weapons.PistolShot") == "Fx.PistolShot"


def test_resolve_two_part_ref_of_a_unique_name(resolver):
    assert resolver.resolve("fx.pistolshot") == "Fx.PistolShot"          # casefolded input


def test_resolve_dotted_ref_of_a_collided_name_is_itself(resolver):
    assert resolver.resolve("Fx.Ammo.Bang") == "Fx.Ammo.Bang"


def test_resolve_ambiguous_two_part_of_a_collided_name_exits_with_error(resolver):
    with pytest.raises(audioindex.AudioRefError) as e:
        resolver.resolve("Fx.Bang")
    assert "Fx.Bang" in str(e.value) and "ambiguous" in str(e.value)


def test_resolve_unknown_ref_names_it(resolver):
    with pytest.raises(audioindex.AudioRefError) as e:
        resolver.resolve("Fx.Nope")
    assert "Fx.Nope" in str(e.value)


def test_unreadable_package_is_skipped_not_fatal(tmp_path, capsys):
    good = _write(tmp_path, "Good.uax", name="Good", kind="sound", objects=[(None, "Ok")])
    bad = tmp_path / "Bad.uax"
    bad.write_bytes(b"not a package at all")
    idx = audioindex.AudioIndex.from_files([good, (str(bad), "x")], "sound")
    assert [e.ref for e in idx.entries] == ["Good.Ok"]
    assert "skipping unreadable package 'Bad'" in capsys.readouterr().err


# --------------------------------------------------------------------------- real corpus (offline, tracked)

def test_deusexsounds_enumerates_the_golden_399_in_ten_groups():
    """Real-corpus offline check over the git-tracked `uned/UED22/DeusExSounds.u`: 399 Sound exports
    in the golden 10-group structure, every bare name unique (the collision rule is latent here)."""
    files = [(f, "x") for f in glob.glob(str(ued22_root() / "**" / "*.u"), recursive=True)]
    idx = audioindex.AudioIndex.from_files(files, "sound")
    dxs = [e for e in idx.entries if e.package == "DeusExSounds"]
    assert len(dxs) == 399
    assert Counter(e.group for e in dxs) == GOLDEN_GROUPS
    assert all(e.identity.count(".") == 1 for e in dxs)                  # 0 collisions → all 2-part
