"""labellib — flat label grammar, `*`-only case-insensitive matcher, and the carrier round-trip.

Labels mirror the single-valued `folder` dimension but as a flat sorted SET: a per-actor `labels`
sidecar, `Actor.labels: frozenset[str]`, never emitted to the built map. This pins the pure core
(spec in board item `re-evaluate-whether-reject-nonlevel-target` §2/§4/§6): the single-segment validator shared with folders, the
leading-`-` reject, the `*`-only (no char-class) case-insensitive matcher, and the
`// uedcli-labels:` interchange carrier.
"""
import pytest

from uedcli import folderlib, labellib
from uedcli.model import parse_t3d


# ── folderlib.validate_segment (the shared single-segment charset check) ────────────

def test_validate_segment_accepts_a_plain_token():
    folderlib.validate_segment("lighting")                # no raise


@pytest.mark.parametrize("bad", ["a.b", "", "a/b", "a b", "a,b", "a\\b", "a*b"])
def test_validate_segment_rejects_bad_tokens(bad):
    with pytest.raises(ValueError):
        folderlib.validate_segment(bad)


def test_validate_segment_error_names_the_offending_value():
    with pytest.raises(ValueError, match=r"a\.b"):
        folderlib.validate_segment("a.b")


def test_validate_segment_allows_leading_dash():
    # The leading-`-` rule belongs to labellib, NOT the shared charset (folders lean on this charset).
    folderlib.validate_segment("-x")                      # no raise


# ── labellib.validate_label (segment charset + no leading `-`) ──────────────────────

@pytest.mark.parametrize("ok", ["lighting", "dup-a1", "flammable", "hero", "wing-b"])
def test_validate_label_accepts_valid_labels(ok):
    labellib.validate_label(ok)                           # no raise


def test_validate_label_rejects_leading_dash():
    with pytest.raises(ValueError, match=r"-x"):
        labellib.validate_label("-x")


@pytest.mark.parametrize("bad", ["a.b", "", "a/b", "a b"])
def test_validate_label_rejects_bad_segments(bad):
    with pytest.raises(ValueError):
        labellib.validate_label(bad)


# ── labellib.match_label (`*`-only, case-insensitive) ───────────────────────────────

def test_match_label_prefix_glob():
    assert labellib.match_label("dup-*", "dup-a1")
    assert not labellib.match_label("dup-*", "lighting")


def test_match_label_is_case_insensitive():
    assert labellib.match_label("Torch*", "torch3")
    assert labellib.match_label("LIGHTING", "lighting")


@pytest.mark.parametrize("pat", ["a?", "a[bc]", "[abc]", "roo]"])
def test_match_label_rejects_char_class_metachars(pat):
    with pytest.raises(ValueError):
        labellib.match_label(pat, "anything")


# ── the `// uedcli-labels:` interchange carrier ─────────────────────────────────────

def test_format_labels_carrier_is_sorted_comma_joined():
    assert labellib.format_labels_carrier({"b", "a"}) == "    // uedcli-labels: a,b"


def test_labels_carrier_round_trips():
    line = labellib.format_labels_carrier({"b", "a"})
    m = labellib._LABELS_CARRIER.match(line)
    assert m is not None
    parsed = {s.strip() for s in m.group(1).split(",") if s.strip()}
    assert parsed == {"a", "b"}


# ── parse_t3d reads the carrier into actor.labels ───────────────────────────────────

def test_parse_t3d_reads_the_labels_carrier():
    text = (
        "Begin Map\n"
        "Begin Actor Class=Engine.Light Name=Torch7\n"
        "    // uedcli-labels: a,b\n"
        "End Actor\n"
        "End Map\n"
    )
    level = parse_t3d(text)
    assert level.actors["Torch7"].labels == frozenset({"a", "b"})


def test_parse_t3d_carrier_line_is_not_treated_as_a_prop():
    text = (
        "Begin Map\n"
        "Begin Actor Class=Engine.Light Name=Torch7\n"
        "    // uedcli-labels: lighting\n"
        "End Actor\n"
        "End Map\n"
    )
    actor = parse_t3d(text).actors["Torch7"]
    assert all(key != "//" for key, _ in actor.props)    # the carrier is NOT a body prop
