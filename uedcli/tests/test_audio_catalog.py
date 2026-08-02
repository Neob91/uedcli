"""`audio_catalog` — the offline audio classification store (audio arm A3).

Pure engine-core unit tests: shard shape/IO across 2- and 3-part identities, the refuse-then-`--force`
WHOLESALE-replace write rule (no union, no per-field merge), the unset field clears, and the queries.
The CLI round-trip and identity resolution live in `test_sound_cli.py` / `test_music_cli.py`.
"""
from __future__ import annotations

import json

import pytest

from uedcli import audio_catalog as ac


# --------------------------------------------------------------------------- shard shape / IO

def test_shard_payload_is_exactly_kind_ref_tags_description():
    s = ac.AudioShard(kind="sound", ref="DeusExSounds.PistolShot", tags=["weapon"],
                      description="a pistol shot")
    assert s.to_json() == {"kind": "sound", "ref": "DeusExSounds.PistolShot",
                           "tags": ["weapon"], "description": "a pistol shot"}
    assert set(s.to_json()) == {"kind", "ref", "tags", "description"}


def test_two_part_and_three_part_identities_roundtrip_through_disk(tmp_path):
    for ref in ("DeusExSounds.PistolShot", "DeusExSounds.Weapons.Bang"):
        s = ac.AudioShard(kind="sound", ref=ref, tags=["boom"], description="d")
        p = ac.shard_path(tmp_path, "sound", ref)
        ac.save_shard(p, s)
        assert ac.load_shard(p) == s
    # the 3-part identity nests one directory deeper than the 2-part one
    assert ac.shard_path(tmp_path, "sound", "P.G.N") == (
        tmp_path / "classified" / "sound" / "p" / "g" / "n.json")


def test_shard_path_is_casefolded_but_payload_keeps_authored_spelling(tmp_path):
    p1 = ac.shard_path(tmp_path, "sound", "DeusExSounds.PistolShot")
    p2 = ac.shard_path(tmp_path, "sound", "deusexsounds.pistolshot")
    assert p1 == p2
    ac.save_shard(p1, ac.AudioShard(kind="sound", ref="DeusExSounds.PistolShot", tags=[], description="x"))
    assert ac.load_shard(p2).ref == "DeusExSounds.PistolShot"


def test_kind_separates_the_shard_trees(tmp_path):
    assert ac.shard_path(tmp_path, "music", "P.N") != ac.shard_path(tmp_path, "sound", "P.N")


@pytest.mark.parametrize("ref", ["BareName", "P.", ".N", "P..N", ""])
def test_parse_ref_rejects_fewer_than_two_nonempty_components(ref):
    with pytest.raises(ac.AudioCatalogError):
        ac.parse_ref(ref)


def test_parse_ref_accepts_two_and_three_part(tmp_path):
    assert ac.parse_ref("P.N") == ["P", "N"]
    assert ac.parse_ref("P.G.N") == ["P", "G", "N"]


# --------------------------------------------------------------------------- set: refuse / force

def test_first_set_writes_exactly_the_supplied_fields():
    out = ac.set_shard(None, "sound", "P.N", tags=["Boom", "boom", " "], description="d", force=False)
    assert out == ac.AudioShard(kind="sound", ref="P.N", tags=["boom"], description="d")


def test_set_over_an_existing_shard_refuses_naming_the_ref_and_stored_payload():
    prior = ac.AudioShard(kind="sound", ref="P.N", tags=["old"], description="the OLD text")
    with pytest.raises(ac.AudioCatalogError) as e:
        ac.set_shard(prior, "sound", "P.N", tags=["new"], description=None, force=False)
    assert "P.N" in str(e.value) and "the OLD text" in str(e.value)


def test_force_replaces_wholesale_dropping_an_omitted_description():
    """The known `--force` cost, pinned here: a forcing `set` that omits --description WIPES the
    stored one, and does NOT union tags — it is a wholesale replace."""
    prior = ac.AudioShard(kind="sound", ref="P.N", tags=["a", "b"], description="keep?")
    out = ac.set_shard(prior, "sound", "P.N", tags=["c"], description=None, force=True)
    assert out == ac.AudioShard(kind="sound", ref="P.N", tags=["c"], description="")


def test_force_keeps_the_write_once_ref_spelling():
    prior = ac.AudioShard(kind="sound", ref="DeusExSounds.PistolShot", tags=[], description="")
    out = ac.set_shard(prior, "sound", "deusexsounds.pistolshot", tags=["x"], description="y", force=True)
    assert out.ref == "DeusExSounds.PistolShot"


# --------------------------------------------------------------------------- unset

def test_unset_removes_named_tags():
    prior = ac.AudioShard(kind="sound", ref="P.N", tags=["a", "b", "c"], description="d")
    out = ac.unset(prior, remove_tags=["b", "MISSING"], clear_tags=False, clear_description=False)
    assert out.tags == ["a", "c"] and out.description == "d"


def test_unset_bare_clears_all_tags_but_keeps_description():
    prior = ac.AudioShard(kind="sound", ref="P.N", tags=["a"], description="d")
    out = ac.unset(prior, remove_tags=None, clear_tags=True, clear_description=False)
    assert out.tags == [] and out.description == "d"


def test_unset_description_clears_only_the_description():
    prior = ac.AudioShard(kind="sound", ref="P.N", tags=["a"], description="d")
    out = ac.unset(prior, remove_tags=None, clear_tags=False, clear_description=True)
    assert out.tags == ["a"] and out.description == ""


# --------------------------------------------------------------------------- queries

def test_classified_refs_globs_both_two_and_three_part_keys(tmp_path):
    ac.save_shard(ac.shard_path(tmp_path, "sound", "P.N"),
                  ac.AudioShard(kind="sound", ref="P.N", tags=["a", "b"], description=""))
    ac.save_shard(ac.shard_path(tmp_path, "sound", "P.G.N"),
                  ac.AudioShard(kind="sound", ref="P.G.N", tags=["a"], description=""))
    ac.save_shard(ac.shard_path(tmp_path, "music", "M.Song"),
                  ac.AudioShard(kind="music", ref="M.Song", tags=[], description=""))
    assert ac.classified_refs(tmp_path, "sound") == {"p.n", "p.g.n"}
    assert ac.classified_refs(tmp_path, "music") == {"m.song"}          # kind-scoped
    assert ac.is_classified(tmp_path, "sound", "p.g.N") is True
    shards, bad = ac.load_all_shards(tmp_path, "sound")
    assert bad == [] and ac.tag_vocabulary(shards) == [("a", 2), ("b", 1)]


def test_load_all_shards_collects_unreadable_without_raising(tmp_path):
    ac.save_shard(ac.shard_path(tmp_path, "sound", "P.Good"),
                  ac.AudioShard(kind="sound", ref="P.Good", tags=[], description=""))
    bad = ac.shard_path(tmp_path, "sound", "P.Bad")
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("{not json")
    shards, bad_paths = ac.load_all_shards(tmp_path, "sound")
    assert [s.ref for s in shards] == ["P.Good"] and bad_paths == [str(bad)]


def test_load_shard_raises_naming_the_path_on_a_malformed_shard(tmp_path):
    p = ac.shard_path(tmp_path, "sound", "P.N")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"kind": "sound"}')                     # missing ref → KeyError, must not traceback
    with pytest.raises(ac.AudioCatalogError) as e:
        ac.load_shard(p)
    assert str(p) in str(e.value)


def test_save_shard_is_json_stable_on_disk(tmp_path):
    p = ac.shard_path(tmp_path, "music", "M.Song")
    ac.save_shard(p, ac.AudioShard(kind="music", ref="M.Song", tags=["b", "a"], description="d"))
    assert json.loads(p.read_text()) == {"kind": "music", "ref": "M.Song",
                                         "tags": ["b", "a"], "description": "d"}


# --------------------------------------------------------------------------- search ranking

def test_score_leaf_of_a_three_part_ref_is_the_name_not_group_dot_name():
    """The class-arm copy uses `split('.',1)[-1]` and would score the leaf of `P.G.N` as `g.n`,
    missing the exact-name tier. This arm uses `rsplit('.',1)[-1]`."""
    assert ac.score("P.G.PistolShot", [], "", ["pistolshot"]) == 5      # exact leaf name
    assert ac.score("P.G.PistolShot", ["boom"], "", ["boom"]) == 4      # exact tag
    assert ac.score("P.G.PistolShot", [], "", ["p.g"]) == 3             # ref substring
    assert ac.score("P.N", ["seating"], "", ["seat"]) == 2              # tag substring
    assert ac.score("P.N", [], "a loud bang", ["loud"]) == 1           # desc substring


def test_score_is_none_when_any_term_matches_nothing():
    assert ac.score("P.G.Bang", ["boom"], "loud", ["boom", "lamp"]) is None
