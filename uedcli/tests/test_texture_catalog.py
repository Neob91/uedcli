"""`texture_catalog` — the offline texture classification store (asset-catalog TEXTURE arm T2).

Pure engine-core unit tests: the identity-keyed shard shape/IO, the hash vs name-keyed path
fan-out, the refuse-over-existing + `--force` REPLACE (no tag union, wiped description), the
write-once ref, the unset field clears (incl. `--colors`), and the `rsplit`-leaf search score.
The CLI round-trip lives in `test_texture_classify.py`.
"""
from __future__ import annotations

import json

import pytest

from uedcli import texture_catalog as tc

HASH = "2eb4f6c49bea0c52c9a1b62f5debee05571345e78ddb92cb3cdbfa21cc7c92f2"
NAME = "fire.flame"


# --------------------------------------------------------------------------- shard shape / IO

def test_shard_payload_is_exactly_kind_identity_ref_tags_description_colors():
    s = tc.TextureShard(identity=HASH, ref="Deco.Wood", tags=["wood"],
                        description="a plank", colors=["brown"])
    assert s.to_json() == {"kind": "texture", "identity": HASH, "ref": "Deco.Wood",
                           "tags": ["wood"], "description": "a plank", "colors": ["brown"]}
    assert set(s.to_json()) == {"kind", "identity", "ref", "tags", "description", "colors"}


def test_shard_roundtrips_through_disk(tmp_path):
    s = tc.TextureShard(identity=HASH, ref="Deco.Wood", tags=["wood", "plank"],
                        description="a plank", colors=["brown", "tan"])
    p = tc.shard_path(tmp_path, HASH)
    tc.save_shard(p, s)
    assert tc.load_shard(p) == s
    assert tc.load_shard(tc.shard_path(tmp_path, "0" * 64)) is None


def test_hash_identity_fans_out_under_the_first_two_hex(tmp_path):
    p = tc.shard_path(tmp_path, HASH)
    assert p.parent.name == HASH[:2] and p.name == f"{HASH}.json"
    assert p.parent.parent.name == "texture"


def test_name_identity_lives_under_name_package_name_casefolded(tmp_path):
    p = tc.shard_path(tmp_path, "Fire.Flame")
    assert p.parent.parent.name == "name" and p.parent.name == "fire" and p.name == "flame.json"


def test_classified_identities_returns_both_hash_and_name_keys(tmp_path):
    tc.save_shard(tc.shard_path(tmp_path, HASH),
                  tc.TextureShard(identity=HASH, ref="P.A", tags=[], description="", colors=[]))
    tc.save_shard(tc.shard_path(tmp_path, NAME),
                  tc.TextureShard(identity=NAME, ref="Fire.Flame", tags=[], description="", colors=[]))
    assert tc.classified_identities(tmp_path) == {HASH, NAME}


# --------------------------------------------------------------------------- set: refuse / force

def test_first_set_takes_the_given_ref_and_fields():
    s = tc.merge_set(None, identity=HASH, ref="Deco.Wood", tags=["Wood", "wood"],
                     description="a plank", colors=["brown"], force=False)
    assert s == tc.TextureShard(identity=HASH, ref="Deco.Wood", tags=["wood"],
                                description="a plank", colors=["brown"])


def test_set_over_an_existing_shard_refuses_naming_it():
    prior = tc.TextureShard(identity=HASH, ref="Deco.Wood", tags=["wood"],
                            description="a plank", colors=["brown"])
    with pytest.raises(tc.TextureCatalogError) as e:
        tc.merge_set(prior, identity=HASH, ref="Other.Twin", tags=["metal"],
                     description=None, colors=None, force=False)
    assert HASH in str(e.value) and "--force" in str(e.value)


def test_force_replaces_wholesale_without_unioning_tags_and_wipes_omitted_description():
    prior = tc.TextureShard(identity=HASH, ref="Deco.Wood", tags=["wood", "plank"],
                            description="a plank", colors=["brown"])
    out = tc.merge_set(prior, identity=HASH, ref="Deco.Wood", tags=["metal"],
                       description=None, colors=None, force=True)
    assert out.tags == ["metal"]               # NOT unioned with the prior wood/plank
    assert out.description == ""                # an omitted description is wiped
    assert out.colors == []


def test_force_keeps_the_write_once_ref_of_the_first_classifier():
    prior = tc.TextureShard(identity=HASH, ref="Deco.Wood", tags=[], description="", colors=[])
    out = tc.merge_set(prior, identity=HASH, ref="Other.Twin", tags=["x"],
                       description=None, colors=None, force=True)
    assert out.ref == "Deco.Wood"              # the first authored ref wins


# --------------------------------------------------------------------------- unset

def test_unset_removes_named_tags_only():
    prior = tc.TextureShard(identity=HASH, ref="P.C", tags=["wood", "plank", "brown"],
                            description="d", colors=["brown"])
    out = tc.unset(prior, remove_tags=["plank", "MISSING"], clear_tags=False,
                   clear_description=False, clear_colors=False)
    assert out.tags == ["wood", "brown"] and out.description == "d" and out.colors == ["brown"]


def test_unset_clears_tags_description_or_colors_independently():
    prior = tc.TextureShard(identity=HASH, ref="P.C", tags=["wood"], description="d",
                            colors=["brown"])
    assert tc.unset(prior, remove_tags=None, clear_tags=True, clear_description=False,
                    clear_colors=False).tags == []
    assert tc.unset(prior, remove_tags=None, clear_tags=False, clear_description=True,
                    clear_colors=False).description == ""
    assert tc.unset(prior, remove_tags=None, clear_tags=False, clear_description=False,
                    clear_colors=True).colors == []


# --------------------------------------------------------------------------- queries

def test_load_all_shards_collects_unreadable_without_raising(tmp_path):
    good = tc.shard_path(tmp_path, HASH)
    tc.save_shard(good, tc.TextureShard(identity=HASH, ref="P.Good", tags=["a"],
                                        description="", colors=[]))
    bad = tc.shard_path(tmp_path, "aa" + "0" * 62)
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("{not json")
    shards, bad_paths = tc.load_all_shards(tmp_path)
    assert [s.ref for s in shards] == ["P.Good"] and bad_paths == [str(bad)]
    assert tc.tag_vocabulary(shards) == [("a", 1)]


def test_save_shard_is_json_stable_on_disk(tmp_path):
    p = tc.shard_path(tmp_path, HASH)
    tc.save_shard(p, tc.TextureShard(identity=HASH, ref="P.C", tags=["b", "a"],
                                     description="d", colors=["blue"]))
    assert json.loads(p.read_text()) == {"kind": "texture", "identity": HASH, "ref": "P.C",
                                         "tags": ["b", "a"], "description": "d",
                                         "colors": ["blue"]}


# --------------------------------------------------------------------------- search score

def test_score_leaf_tier_uses_the_texture_name_even_for_a_three_part_ref():
    """The class store's `split(".", 1)[-1]` would give `Ladder.LadrBrwnMetal` for a 3-part ref,
    so the exact-name tier never fires; `rsplit` extracts the bare Name."""
    assert tc.score("CoreTexMetal.Ladder.LadrBrwnMetal", [], "", ["ladrbrwnmetal"]) == 5
    assert tc.score("Deco.Wood", ["plank"], "", ["wood"]) == 5          # exact leaf
    assert tc.score("Deco.Wood", ["plank"], "", ["plank"]) == 4         # exact tag
    assert tc.score("Deco.Wood", [], "", ["deco"]) == 3                 # ref substring
    assert tc.score("Deco.Wood", ["planks"], "", ["plank"]) == 2        # tag substring
    assert tc.score("Deco.Wood", [], "a wooden plank", ["wooden"]) == 1  # desc substring
    assert tc.score("Deco.Wood", ["plank"], "", ["wood", "lamp"]) is None  # AND drops on a miss
