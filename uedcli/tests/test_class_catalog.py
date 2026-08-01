"""`class_catalog` — the offline class classification store (asset-catalog class arm C3).

Pure engine-core unit tests: shard shape/IO, the tag normalizer, the reserved
`mount:`/`faces:` namespace SHAPE check, the union-merge + description rules, and
the unset field clears. The CLI round-trip lives in `test_class_classify.py`.
"""
from __future__ import annotations

import json

import pytest

from uedcli import class_catalog as cc


# --------------------------------------------------------------------------- shard shape / IO

def test_shard_payload_is_exactly_kind_ref_tags_description():
    """The payload is EXACTLY {kind, ref, tags, description} — no override field
    (owner ruling §8.4)."""
    s = cc.ClassShard(ref="DeusEx.BarStool", tags=["chair"], description="a stool")
    assert s.to_json() == {"kind": "class", "ref": "DeusEx.BarStool",
                           "tags": ["chair"], "description": "a stool"}
    assert set(s.to_json()) == {"kind", "ref", "tags", "description"}


def test_shard_roundtrips_through_disk(tmp_path):
    s = cc.ClassShard(ref="DeusEx.BarStool", tags=["chair", "mount:floor"],
                      description="bar stool")
    p = cc.shard_path(tmp_path, "DeusEx.BarStool")
    cc.save_shard(p, s)
    assert cc.load_shard(p) == s
    assert cc.load_shard(cc.shard_path(tmp_path, "DeusEx.Nope")) is None


def test_shard_path_is_casefolded_but_payload_keeps_authored_spelling(tmp_path):
    """Two differently-cased refs address ONE shard (casefolded path); the payload
    keeps the authored spelling."""
    p1 = cc.shard_path(tmp_path, "DeusEx.BarStool")
    p2 = cc.shard_path(tmp_path, "deusex.barstool")
    assert p1 == p2
    assert p1.parent.name == "deusex" and p1.name == "barstool.json"
    cc.save_shard(p1, cc.ClassShard(ref="DeusEx.BarStool", tags=[], description="x"))
    assert cc.load_shard(p2).ref == "DeusEx.BarStool"


@pytest.mark.parametrize("ref", ["BarStool", "DeusEx.", ".BarStool", "A.B.C", "DeusEx..X", ""])
def test_parse_ref_rejects_non_two_part(ref):
    with pytest.raises(cc.ClassCatalogError):
        cc.parse_ref(ref)


# --------------------------------------------------------------------------- tag normalizer

def test_norm_tags_strips_lowercases_dedupes_and_drops_empties():
    assert cc._norm_tags([" Chair ", "CHAIR", "wood", "", "  "]) == ["chair", "wood"]


# --------------------------------------------------------------------------- namespace SHAPE

@pytest.mark.parametrize("tag", ["faces:+x", "faces:-z", "mount:wall", "mount:floor tile",
                                 "chair", "mount:a"])
def test_validate_accepts_well_shaped_namespaced_and_plain_tags(tag):
    cc.validate_tags([tag])                              # no raise


@pytest.mark.parametrize("tag", ["faces:foward", "faces:+w", "faces:", "faces:up", "mount:"])
def test_validate_rejects_malformed_namespaced_tags(tag):
    with pytest.raises(cc.ClassCatalogError) as e:
        cc.validate_tags([tag])
    assert tag in str(e.value)                           # names the offending token


def test_faces_axis_is_case_normalized_before_the_check():
    """`faces:+X` normalizes to `faces:+x`, which then passes the shape check."""
    cc.validate_tags(cc._norm_tags(["faces:+X"]))        # no raise


# --------------------------------------------------------------------------- merge (set)

def test_merge_unions_tags_through_the_normalizer():
    prior = cc.ClassShard(ref="P.C", tags=["chair"], description="")
    out = cc.merge_set(prior, "P.C", tags=["Wood", "chair", "mount:floor"],
                       description=None, replace=False)
    assert out.tags == ["chair", "wood", "mount:floor"]  # union, de-duped, order-stable


def test_merge_keeps_ref_write_once():
    prior = cc.ClassShard(ref="DeusEx.BarStool", tags=[], description="")
    out = cc.merge_set(prior, "deusex.barstool", tags=["x"], description=None, replace=False)
    assert out.ref == "DeusEx.BarStool"                  # the first authored spelling wins


def test_merge_first_write_takes_the_given_ref_spelling():
    out = cc.merge_set(None, "DeusEx.BarStool", tags=["x"], description=None, replace=False)
    assert out.ref == "DeusEx.BarStool"


def test_merge_sets_description_when_none_stored():
    out = cc.merge_set(cc.ClassShard(ref="P.C", tags=[], description=""),
                       "P.C", tags=None, description="a stool", replace=False)
    assert out.description == "a stool"


def test_merge_identical_description_is_a_noop_not_a_conflict():
    prior = cc.ClassShard(ref="P.C", tags=[], description="a stool")
    out = cc.merge_set(prior, "P.C", tags=None, description="a stool", replace=False)
    assert out.description == "a stool"


def test_merge_conflicting_description_raises_printing_stored_text():
    prior = cc.ClassShard(ref="P.C", tags=[], description="the OLD text")
    with pytest.raises(cc.ClassCatalogError) as e:
        cc.merge_set(prior, "P.C", tags=None, description="new text", replace=False)
    assert "the OLD text" in str(e.value)


def test_merge_replace_overwrites_a_conflicting_description():
    prior = cc.ClassShard(ref="P.C", tags=[], description="old")
    out = cc.merge_set(prior, "P.C", tags=None, description="new", replace=True)
    assert out.description == "new"


def test_merge_rejects_a_malformed_namespaced_tag():
    with pytest.raises(cc.ClassCatalogError):
        cc.merge_set(None, "P.C", tags=["faces:foward"], description=None, replace=False)


# --------------------------------------------------------------------------- unset

def test_unset_removes_named_tags():
    prior = cc.ClassShard(ref="P.C", tags=["chair", "wood", "mount:floor"], description="d")
    out = cc.unset(prior, remove_tags=["wood", "MISSING"], clear_tags=False,
                   clear_description=False)
    assert out.tags == ["chair", "mount:floor"] and out.description == "d"


def test_unset_bare_clears_all_tags_but_keeps_description():
    prior = cc.ClassShard(ref="P.C", tags=["chair"], description="d")
    out = cc.unset(prior, remove_tags=None, clear_tags=True, clear_description=False)
    assert out.tags == [] and out.description == "d"


def test_unset_description_clears_only_the_description():
    prior = cc.ClassShard(ref="P.C", tags=["chair"], description="d")
    out = cc.unset(prior, remove_tags=None, clear_tags=False, clear_description=True)
    assert out.tags == ["chair"] and out.description == ""


# --------------------------------------------------------------------------- queries

def test_classified_refs_and_vocabulary(tmp_path):
    cc.save_shard(cc.shard_path(tmp_path, "DeusEx.BarStool"),
                  cc.ClassShard(ref="DeusEx.BarStool", tags=["chair", "wood"], description=""))
    cc.save_shard(cc.shard_path(tmp_path, "DeusEx.OfficeChair"),
                  cc.ClassShard(ref="DeusEx.OfficeChair", tags=["chair"], description=""))
    assert cc.classified_refs(tmp_path) == {"deusex.barstool", "deusex.officechair"}
    assert cc.is_classified(tmp_path, "deusex.BARSTOOL") is True
    assert cc.is_classified(tmp_path, "DeusEx.Nope") is False
    shards, bad = cc.load_all_shards(tmp_path)
    assert bad == [] and len(shards) == 2
    assert cc.tag_vocabulary(shards) == [("chair", 2), ("wood", 1)]


def test_load_all_shards_collects_unreadable_without_raising(tmp_path):
    good = cc.shard_path(tmp_path, "P.Good")
    cc.save_shard(good, cc.ClassShard(ref="P.Good", tags=[], description=""))
    bad = cc.shard_path(tmp_path, "P.Bad")
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("{not json")
    shards, bad_paths = cc.load_all_shards(tmp_path)
    assert [s.ref for s in shards] == ["P.Good"] and bad_paths == [str(bad)]


def test_save_shard_is_json_stable_on_disk(tmp_path):
    p = cc.shard_path(tmp_path, "P.C")
    cc.save_shard(p, cc.ClassShard(ref="P.C", tags=["b", "a"], description="d"))
    assert json.loads(p.read_text()) == {"kind": "class", "ref": "P.C",
                                         "tags": ["b", "a"], "description": "d"}
