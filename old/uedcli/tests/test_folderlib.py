"""folderlib — stored-path grammar, query-pattern grammar, and the §3 globstar match algorithm.

Pins the NORMATIVE matching definition (spec in board item `actor-folders-hierarchical-actor-organization` §3): the
boundary rules the spec calls out (X.** matches X itself, **.roof matches a top-level roof, * is
exactly one segment / segment-boundary prefix, *.roof ⊂ *.**.roof, case-insensitivity,
folder=None matches nothing, ?/[/] rejected).
"""
import pytest

from uedcli import folderlib


# ── stored-path grammar (validate_folder_path) ──────────────────────────────────────

@pytest.mark.parametrize("path", [
    "castle", "castle.tower.roof", "a", "a.b.c.d.e",
    "seg_1", "plus+minus-", "Mixed.Case.Preserved", "123.456",
])
def test_valid_stored_paths_accepted(path):
    folderlib.validate_folder_path(path)                  # no raise


@pytest.mark.parametrize("path", [
    "", ".", "a.", ".a", "a..b", "a b", "a.b c",
    "a*b", "a,b", "a/b", "a\\b", "a.b*", "**", "a.**",
])
def test_invalid_stored_paths_rejected(path):
    with pytest.raises(ValueError) as e:
        folderlib.validate_folder_path(path)
    assert repr(path) in str(e.value) or "empty" in str(e.value)


def test_stored_path_error_names_the_offending_value():
    with pytest.raises(ValueError, match=r"a\*b"):
        folderlib.validate_folder_path("ok.a*b")


# ── query-pattern grammar (validate_pattern) ───────────────────────────────────────

@pytest.mark.parametrize("pat", [
    "castle", "castle.tower.roof", "*", "**", "castle.*", "castle.**",
    "**.roof", "*.roof", "*.**.roof", "a.*.b.**.c",
])
def test_valid_patterns_accepted(pat):
    folderlib.validate_pattern(pat)                       # no raise


@pytest.mark.parametrize("pat", [
    "", "a?", "a[b]", "[abc]", "a.b?", "***", "a**", "**b", "a*b",
    "a.", ".a", "a..b", "a b",
])
def test_invalid_patterns_rejected(pat):
    with pytest.raises(ValueError):
        folderlib.validate_pattern(pat)


def test_question_and_bracket_rejected_explicitly():
    # ?/[/] are NOT wildcards here (spec §3, B2) — an fnmatch leak would silently accept them.
    for bad in ("roof?", "roo[ft]", "**.roo?"):
        with pytest.raises(ValueError):
            folderlib.validate_pattern(bad)


# ── is_wildcard_free ───────────────────────────────────────────────────────────────

def test_wildcard_free_predicate_is_exact():
    assert folderlib.is_wildcard_free("castle.tower.roof")
    assert not folderlib.is_wildcard_free("castle.*")
    assert not folderlib.is_wildcard_free("**")
    assert not folderlib.is_wildcard_free("**.roof")


# ── the §3 match algorithm (the definition, not the table) ─────────────────────────

def test_none_folder_matches_no_pattern():
    for pat in ("castle", "*", "**", "**.roof"):
        assert folderlib.matches(pat, None) is False


def test_wildcard_free_is_subtree_match():
    # bare = the node AND its whole subtree
    assert folderlib.matches("castle", "castle")
    assert folderlib.matches("castle", "castle.tower")
    assert folderlib.matches("castle", "castle.tower.roof")
    assert folderlib.matches("castle", "castle.moat")


def test_wildcard_free_is_segment_boundary_prefix():
    # `cast` does NOT match `castle` — the prefix must land on a segment boundary
    assert not folderlib.matches("cast", "castle")
    assert not folderlib.matches("castle.tow", "castle.tower")


def test_star_is_exactly_one_segment():
    assert folderlib.matches("castle.*", "castle.tower")
    assert folderlib.matches("castle.*", "castle.moat")
    # NOT the grandchild — `*` is exactly one segment, no subtree extension
    assert not folderlib.matches("castle.*", "castle.tower.roof")
    # NOT the node itself (needs one more segment)
    assert not folderlib.matches("castle.*", "castle")


def test_double_star_matches_zero_or_more_segments():
    # `X.**` matches X itself (the zero-segment `**` / separator-absorption boundary rule)
    assert folderlib.matches("castle.**", "castle")
    assert folderlib.matches("castle.**", "castle.tower")
    assert folderlib.matches("castle.**", "castle.tower.roof")
    # equivalent to bare `castle`
    for f in ("castle", "castle.tower", "castle.tower.roof"):
        assert folderlib.matches("castle.**", f) == folderlib.matches("castle", f)


def test_leading_double_star_matches_top_level():
    # `**.roof` matches a TOP-LEVEL roof (the other boundary of separator-absorption)
    assert folderlib.matches("**.roof", "roof")
    assert folderlib.matches("**.roof", "castle.roof")
    assert folderlib.matches("**.roof", "castle.tower.roof")
    # a `roof` NODE only — not what's under it
    assert not folderlib.matches("**.roof", "castle.roof.tiles")
    # not a partial-segment match
    assert not folderlib.matches("**.roof", "castle.xroof")


def test_star_roof_is_depth_exactly_two():
    assert folderlib.matches("*.roof", "castle.roof")
    assert not folderlib.matches("*.roof", "castle.tower.roof")   # depth 3
    assert not folderlib.matches("*.roof", "roof")                # depth 1


def test_star_roof_is_subset_of_star_doublestar_roof():
    # `*.**.roof` = roof at depth >= 2 (superset of `*.roof`)
    for f in ("castle.roof", "castle.tower.roof", "a.b.c.roof"):
        if folderlib.matches("*.roof", f):
            assert folderlib.matches("*.**.roof", f)
    assert folderlib.matches("*.**.roof", "castle.roof")          # depth 2 included
    assert folderlib.matches("*.**.roof", "castle.tower.roof")    # depth 3
    assert not folderlib.matches("*.**.roof", "roof")             # depth 1 excluded


def test_matching_is_case_insensitive():
    assert folderlib.matches("Castle", "castle.TOWER")
    assert folderlib.matches("**.ROOF", "castle.roof")
    assert folderlib.matches("castle.*", "CASTLE.tower")
