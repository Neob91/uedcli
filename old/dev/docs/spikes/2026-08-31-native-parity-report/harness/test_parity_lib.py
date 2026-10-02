"""Offline unit tests for `parity_lib.py` — no editor, no docker, no `uedcli` import needed.

Not part of `bin/test`'s `testpaths = uedcli` collection (this lives under `dev/docs/`, a
dev-tool/spike harness, not the uedcli package) — run directly:
    .venv/bin/python -m pytest dev/docs/spikes/2026-08-31-native-parity-report/harness/test_parity_lib.py
"""
import dataclasses
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import parity_lib as pl  # noqa: E402


def test_content_hash_matches_known_sha256(tmp_path):
    f = tmp_path / "x.dx"
    f.write_bytes(b"hello world")
    assert pl.content_hash(f) == hashlib.sha256(b"hello world").hexdigest()


def test_content_hash_stable_across_calls(tmp_path):
    f = tmp_path / "x.dx"
    f.write_bytes(b"deadbeef" * 1000)
    assert pl.content_hash(f) == pl.content_hash(f)


def test_cache_layout_paths(tmp_path):
    layout = pl.cache_layout(tmp_path, "abc123")
    assert layout.root == tmp_path / "abc123"
    assert layout.meta == tmp_path / "abc123" / "meta.json"
    assert layout.golden == tmp_path / "abc123" / "golden.dx"


def test_cache_incomplete_when_nothing_built(tmp_path):
    layout = pl.cache_layout(tmp_path, "abc123")
    assert not pl.is_cache_complete(layout)


def test_cache_incomplete_when_golden_missing_but_meta_present(tmp_path):
    layout = pl.cache_layout(tmp_path, "abc123")
    pl.write_meta(layout, {"status": "complete"})
    assert not pl.is_cache_complete(layout)


def test_cache_incomplete_when_meta_status_not_complete(tmp_path):
    layout = pl.cache_layout(tmp_path, "abc123")
    layout.root.mkdir(parents=True)
    layout.golden.write_bytes(b"fake")
    pl.write_meta(layout, {"status": "extracting"})
    assert not pl.is_cache_complete(layout)


def test_cache_complete_when_golden_and_meta_agree(tmp_path):
    layout = pl.cache_layout(tmp_path, "abc123")
    layout.root.mkdir(parents=True)
    layout.golden.write_bytes(b"fake")
    pl.write_meta(layout, {"status": "complete", "built_at": "2026-08-31T00:00:00"})
    assert pl.is_cache_complete(layout)
    assert pl.read_meta(layout)["built_at"] == "2026-08-31T00:00:00"


def test_cache_incomplete_on_corrupt_meta_json(tmp_path):
    layout = pl.cache_layout(tmp_path, "abc123")
    layout.root.mkdir(parents=True)
    layout.golden.write_bytes(b"fake")
    layout.meta.write_text("{not json")
    assert not pl.is_cache_complete(layout)
    assert pl.read_meta(layout) is None


def _counts(**kw):
    base = dict(nodes=0, surfs=0, leaves=0, verts=0, points=0, vectors=0)
    base.update(kw)
    return pl.GeometryCounts(**base)


def test_geometry_delta_exact_when_all_six_match():
    g = pl.GeometryDelta(native=_counts(nodes=100, surfs=50), golden=_counts(nodes=100, surfs=50))
    assert g.exact
    assert g.d_nodes == 0 and g.d_surfs == 0


def test_geometry_delta_not_exact_on_any_single_dimension_off():
    # node/surf/leaf match (what breadth_gate.py's looser "EXACT" checks) but verts differ —
    # this must NOT count as exact here, unlike the looser breadth-gate label.
    g = pl.GeometryDelta(
        native=_counts(nodes=6321, surfs=3616, leaves=762, verts=10763, points=6339, vectors=599),
        golden=_counts(nodes=6321, surfs=3616, leaves=762, verts=10758, points=6339, vectors=599))
    assert not g.exact
    assert g.d_verts == 5


@dataclasses.dataclass
class _Node:
    """A minimal stand-in for `umodel.BspNode` -- `compare_array_content` is generic over
    `dataclasses.fields`, so a hand-built fixture with a subset of fields exercises the same code
    path without importing `uedcli.native.umodel` (this file stays a pure, no-`uedcli`-import unit
    test, matching its own docstring)."""
    plane: tuple = (0.0, 0.0, 1.0, 0.0)
    i_surf: int = 0
    i_front: int = -1
    i_back: int = -1
    node_flags: int = 0
    i_leaf: tuple = (-1, -1)


def _node(**kw):
    return _Node(**kw)


@dataclasses.dataclass
class _Surf:
    """A minimal stand-in for `umodel.BspSurf`, same rationale as `_Node` above."""
    texture_ref: int = 0
    i_actor: int = 0


def _surf(**kw):
    return _Surf(**kw)


def test_compare_array_content_identical_arrays_are_exact():
    native = [_node(i_surf=0), _node(i_surf=1)]
    golden = [_node(i_surf=0), _node(i_surf=1)]
    r = pl.compare_array_content(native, golden, array_name="nodes")
    assert r.exact
    assert r.indices_differ == 0
    assert r.fields_differ == 0
    assert r.diffs == ()


def test_compare_array_content_catches_matching_counts_but_diverging_tree():
    # The whole point of this build: two arrays with the SAME LENGTH (what the old count-only
    # check called "tree structure EXACT") can still hold genuinely different content per index --
    # e.g. native's build landed nodes in a different order than golden's. Index-for-index
    # comparison must catch this; a structural/reordering-tolerant compare would miss it.
    native = [_node(i_surf=0), _node(i_surf=2), _node(i_surf=1)]
    golden = [_node(i_surf=0), _node(i_surf=1), _node(i_surf=2)]
    r = pl.compare_array_content(native, golden, array_name="nodes")
    assert not r.exact
    assert r.native_len == r.golden_len == 3
    assert r.diverging_indices == (1, 2)
    assert r.indices_differ == 2
    assert r.fields_differ == 2


def test_compare_array_content_counts_every_diverging_field_at_one_index():
    native = [_node(i_surf=9, i_front=5)]
    golden = [_node(i_surf=0, i_front=-1)]
    r = pl.compare_array_content(native, golden, array_name="nodes")
    assert r.indices_differ == 1
    assert r.fields_differ == 2
    assert {d.field for d in r.diffs} == {"i_surf", "i_front"}


def test_compare_array_content_length_mismatch_not_exact_even_with_clean_common_prefix():
    native = [_node(i_surf=0), _node(i_surf=1)]
    golden = [_node(i_surf=0), _node(i_surf=1), _node(i_surf=2)]
    r = pl.compare_array_content(native, golden, array_name="nodes")
    assert not r.exact
    assert r.compared == 2
    assert r.diffs == ()  # the common prefix genuinely agrees -- only the length differs


def test_compare_array_content_float_mismatch_is_bit_exact_no_epsilon():
    # 512.0001 differs from 512.0 by more than one float32 ULP at that magnitude (~6.1e-5) --
    # genuinely two different on-disk f32 bit patterns, not double-precision noise around one.
    native = [_node(plane=(0.0, 0.0, 1.0, 512.0))]
    golden = [_node(plane=(0.0, 0.0, 1.0, 512.0001))]
    r = pl.compare_array_content(native, golden, array_name="nodes")
    assert not r.exact
    assert r.fields_differ == 1
    assert r.diffs[0].field == "plane"


def test_compare_array_content_float32_ulp_noise_below_precision_is_not_a_diff():
    # The flip side, and why comparison is via the on-disk f32 BYTES, not the Python double: two
    # doubles differing by less than one float32 ULP at this magnitude round to the identical f32
    # bit pattern -- genuinely the same on-disk value, must not be reported as a diff.
    native = [_node(plane=(0.0, 0.0, 1.0, 512.0))]
    golden = [_node(plane=(0.0, 0.0, 1.0, 512.00001))]
    r = pl.compare_array_content(native, golden, array_name="nodes")
    assert r.exact


def test_compare_array_content_negative_zero_is_a_real_diff_not_masked_by_bare_uneq():
    # Regression for a review-caught bug: bare `!=` says `-0.0 != 0.0` is False, so a genuine
    # on-disk byte divergence (a plausible BSP plane-equation output) would be silently missed.
    native = [_node(plane=(-0.0, 0.0, 1.0, 0.0))]
    golden = [_node(plane=(0.0, 0.0, 1.0, 0.0))]
    r = pl.compare_array_content(native, golden, array_name="nodes")
    assert not r.exact
    assert r.diffs[0].field == "plane"


def test_compare_array_content_identical_nan_payload_is_not_a_false_positive():
    # Regression for the other half of the same bug: bare `!=` says NaN != NaN is True, so two
    # bit-identical NaN payloads would wrongly report as differing.
    nan = float("nan")
    native = [_node(plane=(nan, 0.0, 1.0, 0.0))]
    golden = [_node(plane=(nan, 0.0, 1.0, 0.0))]
    r = pl.compare_array_content(native, golden, array_name="nodes")
    assert r.exact


def test_compare_array_content_node_flags_masked_bits_are_not_a_diff():
    # 0x08/0x10 (render-viewport occlusion leftover, board/done/
    # node-flags-8-is-nf-polyoccluded-a-render-only) and 0x40/0x80 (no editor setter found at all,
    # board/inbox/node-flags-0x40-0x80-divergence-from-movers-no) are proven non-derivable from the
    # deterministic build -- masked out of the node_flags comparison specifically.
    native = [_node(node_flags=0x01 | 0x08 | 0x40)]
    golden = [_node(node_flags=0x01 | 0x10 | 0x80)]
    r = pl.compare_array_content(native, golden, array_name="nodes")
    assert r.exact
    assert r.diffs == ()


def test_compare_array_content_node_flags_non_masked_bit_still_a_diff():
    # The mask is narrow: a real divergence outside 0x08/0x10/0x40/0x80 must still be caught.
    native = [_node(node_flags=0x01)]
    golden = [_node(node_flags=0x02)]
    r = pl.compare_array_content(native, golden, array_name="nodes")
    assert not r.exact
    assert r.fields_differ == 1
    assert r.diffs[0].field == "node_flags"


def test_compare_array_content_node_flags_mask_does_not_swallow_other_field_diff():
    # Regression guard: masking node_flags must not accidentally hide a REAL divergence in a
    # different field (e.g. i_leaf) on the same node.
    native = [_node(node_flags=0x08, i_leaf=(3, -1))]
    golden = [_node(node_flags=0x10, i_leaf=(5, -1))]
    r = pl.compare_array_content(native, golden, array_name="nodes")
    assert not r.exact
    assert {d.field for d in r.diffs} == {"i_leaf"}


def test_object_paths_walks_the_outer_chain_for_exports_and_imports():
    # exports: (outer-ref, name); imports: (outer-ref, name). Ref 0 = no outer (top level),
    # positive = 1-based export ref, negative = ~0-based import ref.
    exports = [(0, "MyLevel"), (1, "Model2")]
    imports = [(0, "DeusExItems"), (-1, "Skins"), (-2, "BlackMaskTex")]
    ep, ip = pl.object_paths(exports, imports)
    assert ep == ("MyLevel", "MyLevel.Model2")
    assert ip == ("DeusExItems", "DeusExItems.Skins", "DeusExItems.Skins.BlackMaskTex")


def test_resolve_object_ref_covers_none_export_and_import():
    ep, ip = ("MyLevel", "Brush3"), ("Engine", "Engine.Tex")
    assert pl.resolve_object_ref(0, export_paths=ep, import_paths=ip) == pl.OBJECT_REF_NONE
    assert pl.resolve_object_ref(2, export_paths=ep, import_paths=ip) == "Brush3"
    assert pl.resolve_object_ref(-2, export_paths=ep, import_paths=ip) == "Engine.Tex"


def test_resolve_object_ref_out_of_range_names_the_offending_value():
    with pytest.raises(ValueError, match="9"):
        pl.resolve_object_ref(9, export_paths=("A",), import_paths=())
    with pytest.raises(ValueError, match="-9"):
        pl.resolve_object_ref(-9, export_paths=(), import_paths=("A",))


def test_resolve_surf_refs_replaces_both_ref_fields_and_leaves_the_rest():
    import dataclasses as dc

    @dc.dataclass
    class _Surf:
        texture_ref: int = 0
        i_actor: int = 0
        p_base: int = 0

    surfs = (_Surf(texture_ref=-2, i_actor=1, p_base=7),)
    out = pl.resolve_surf_refs(surfs, export_paths=("Brush3",), import_paths=("A", "A.Tex"))
    assert out[0].i_actor == "Brush3"
    assert out[0].texture_ref == "A.Tex"
    assert out[0].p_base == 7


def test_semantic_resolution_closes_a_pure_export_ordering_false_positive():
    """The live-measured shape (round 8): native and the golden agree on WHICH brush actor owns
    each surf and WHICH texture it wears, but their export/import tables are ordered differently,
    so the raw indices disagree on every surf. Raw-index comparison must false-positive on all
    three; resolved-identity comparison must find zero diffs."""
    # Golden's export table interleaves editor-session objects among the actors; native's groups
    # each brush actor with its shape. Same three brushes, different positions.
    golden_exports = [(0, "LevelInfo0"), (0, "Brush8"), (0, "Camera6"), (0, "Brush3"),
                      (0, "Camera7"), (0, "Brush9")]
    native_exports = [(0, "LevelInfo0"), (0, "Brush3"), (0, "Brush8"), (0, "Brush9")]
    imports = [(0, "Pkg"), (-1, "Grp"), (-2, "Tex")]

    golden_surfs = [_surf(i_actor=2, texture_ref=-3), _surf(i_actor=4, texture_ref=-3),
                    _surf(i_actor=6, texture_ref=-3)]
    native_surfs = [_surf(i_actor=3, texture_ref=-3), _surf(i_actor=2, texture_ref=-3),
                    _surf(i_actor=4, texture_ref=-3)]

    raw = pl.compare_array_content(native_surfs, golden_surfs, array_name="surfs")
    assert raw.indices_differ == 3

    gep, gip = pl.object_paths(golden_exports, imports)
    nep, nip = pl.object_paths(native_exports, imports)
    resolved = pl.compare_array_content(
        pl.resolve_surf_refs(native_surfs, export_paths=nep, import_paths=nip),
        pl.resolve_surf_refs(golden_surfs, export_paths=gep, import_paths=gip),
        array_name="surfs")
    assert resolved.exact


def test_semantic_resolution_still_reports_a_real_identity_mismatch():
    """A genuine content bug -- the two sides name DIFFERENT textures -- must survive resolution."""
    exports = [(0, "Brush3")]
    golden_imports = [(0, "NYCBar"), (-1, "Metal"), (-2, "trough1")]
    native_imports = [(0, "NewYorkCity"), (-1, "Metal"), (-2, "trough1")]
    gep, gip = pl.object_paths(exports, golden_imports)
    nep, nip = pl.object_paths(exports, native_imports)
    r = pl.compare_array_content(
        pl.resolve_surf_refs([_surf(i_actor=1, texture_ref=-3)], export_paths=nep, import_paths=nip),
        pl.resolve_surf_refs([_surf(i_actor=1, texture_ref=-3)], export_paths=gep, import_paths=gip),
        array_name="surfs")
    assert not r.exact
    assert {d.field for d in r.diffs} == {"texture_ref"}


def _content(*, nodes_exact=True, surfs_exact=True, leaves_exact=True):
    diff = pl.FieldDiff(index=1, field="i_surf", native=2, golden=1)
    nodes = pl.ArrayContentResult(array_name="nodes", native_len=3, golden_len=3,
                                  diffs=() if nodes_exact else (diff,))
    surfs = pl.ArrayContentResult(array_name="surfs", native_len=2, golden_len=2,
                                  diffs=() if surfs_exact else (diff,))
    leaves = pl.ArrayContentResult(array_name="leaves", native_len=2, golden_len=2,
                                   diffs=() if leaves_exact else (diff,))
    return pl.ContentComparison(nodes=nodes, surfs=surfs, leaves=leaves)


def test_content_comparison_exact_requires_all_three_arrays_exact():
    assert _content().exact
    assert not _content(nodes_exact=False).exact
    assert not _content(surfs_exact=False).exact
    assert not _content(leaves_exact=False).exact


def test_lighting_summary_partial_not_fully_identical():
    light = pl.LightingSummary(total_records=3345, identical_records=2797,
                               shadow_bits_same=900, shadow_bits_total=1000)
    assert not light.records_fully_identical
    assert round(light.identical_pct, 1) == round(100 * 2797 / 3345, 1)


def test_lighting_summary_fully_identical_at_100_percent():
    light = pl.LightingSummary(total_records=100, identical_records=100,
                               shadow_bits_same=10, shadow_bits_total=10)
    assert light.records_fully_identical


def test_lighting_summary_vacuously_identical_at_zero_records():
    light = pl.LightingSummary(total_records=0, identical_records=0,
                               shadow_bits_same=0, shadow_bits_total=0)
    assert light.records_fully_identical
    assert light.identical_pct == 0.0


def test_full_parity_false_when_geometry_not_exact_even_if_content_and_lighting_full():
    geo = pl.GeometryDelta(native=_counts(nodes=1, verts=2), golden=_counts(nodes=1, verts=3))
    light = pl.LightingSummary(total_records=10, identical_records=10,
                               shadow_bits_same=1, shadow_bits_total=1)
    assert not pl.full_parity(geo, _content(), light)


def test_full_parity_false_when_content_not_exact_even_if_geometry_and_lighting_full():
    # The core regression this build exists to prevent: matching counts plus full lighting must
    # NOT be enough for FULL PARITY if the node/surf content itself genuinely diverges per-index.
    geo = pl.GeometryDelta(native=_counts(nodes=3), golden=_counts(nodes=3))
    light = pl.LightingSummary(total_records=10, identical_records=10,
                               shadow_bits_same=1, shadow_bits_total=1)
    assert not pl.full_parity(geo, _content(nodes_exact=False), light)


def test_full_parity_false_when_lighting_partial_even_if_geometry_and_content_exact():
    geo = pl.GeometryDelta(native=_counts(), golden=_counts())
    light = pl.LightingSummary(total_records=10, identical_records=9,
                               shadow_bits_same=1, shadow_bits_total=1)
    assert not pl.full_parity(geo, _content(), light)


def test_full_parity_true_when_geometry_content_and_lighting_all_exact():
    geo = pl.GeometryDelta(native=_counts(nodes=5), golden=_counts(nodes=5))
    light = pl.LightingSummary(total_records=10, identical_records=10,
                               shadow_bits_same=1, shadow_bits_total=1)
    assert pl.full_parity(geo, _content(), light)


def _unatco_like_report(cache_hit=False, content=None):
    geo = pl.GeometryDelta(
        native=_counts(nodes=6321, surfs=3616, leaves=762, verts=10763, points=6339, vectors=599),
        golden=_counts(nodes=6321, surfs=3616, leaves=762, verts=10758, points=6339, vectors=599))
    light = pl.LightingSummary(total_records=3345, identical_records=2797,
                               shadow_bits_same=920000, shadow_bits_total=922706)
    return pl.ParityReport(source_dx="/x/01_NYC_UNATCOHQ.dx", content_hash="deadbeef" * 8,
                           level_name="unatco", cache_hit=cache_hit, built_at="2026-08-31",
                           geometry=geo, content=content if content is not None else _content(),
                           lighting=light)


def test_report_full_parity_property_reflects_unatco_style_gap():
    report = _unatco_like_report()
    assert report.full_parity is False


def test_format_text_reports_no_for_unatco_style_gap():
    text = pl.format_text(_unatco_like_report())
    assert "FULL PARITY: NO" in text
    assert "NOT EXACT" in text
    assert "PARTIAL" in text
    assert "01_NYC_UNATCOHQ.dx" in text


def test_format_text_cache_hit_shown():
    text = pl.format_text(_unatco_like_report(cache_hit=True))
    assert "HIT (built 2026-08-31)" in text


def test_format_json_roundtrips_full_parity_and_deltas():
    import json
    report = _unatco_like_report()
    data = json.loads(pl.format_json(report))
    assert data["full_parity"] is False
    assert data["geometry"]["deltas"]["verts"] == 5
    assert data["lighting"]["identical_pct"] == report.lighting.identical_pct


def test_format_json_yes_case():
    import json
    geo = pl.GeometryDelta(native=_counts(nodes=1), golden=_counts(nodes=1))
    light = pl.LightingSummary(total_records=5, identical_records=5,
                               shadow_bits_same=1, shadow_bits_total=1)
    report = pl.ParityReport(source_dx="/x/dx.dx", content_hash="ab" * 32, level_name="dx",
                             cache_hit=False, built_at=None, geometry=geo, content=_content(),
                             lighting=light)
    data = json.loads(pl.format_json(report))
    assert data["full_parity"] is True


def test_format_text_reports_content_not_exact_with_field_diff_detail():
    report = dataclasses.replace(_unatco_like_report(), content=_content(nodes_exact=False))
    text = pl.format_text(report)
    assert "Content (index-for-index" in text
    assert "content NOT EXACT" in text
    assert "[1] i_surf: native=2 golden=1" in text


def test_format_text_reports_content_exact_when_counts_and_content_both_match():
    report = dataclasses.replace(_unatco_like_report(), content=_content())
    text = pl.format_text(report)
    assert "content EXACT" in text


def test_format_text_length_mismatch_with_clean_prefix_never_says_content_identical():
    # A regression this self-review caught: a length mismatch with an empty diff list (the common
    # prefix genuinely agrees) must NOT be worded as "content identical" -- it isn't, the array
    # can never serialize byte-identical at different lengths.
    nodes = pl.ArrayContentResult(array_name="nodes", native_len=2, golden_len=3)
    content = pl.ContentComparison(
        nodes=nodes,
        surfs=pl.ArrayContentResult(array_name="surfs", native_len=1, golden_len=1),
        leaves=pl.ArrayContentResult(array_name="leaves", native_len=1, golden_len=1))
    report = dataclasses.replace(_unatco_like_report(), content=content)
    lines = pl.format_text(report).splitlines()
    content_start = next(i for i, l in enumerate(lines) if l.startswith("Content ("))
    node_line = next(l for l in lines[content_start:] if l.strip().startswith("nodes"))
    assert "content identical" not in node_line
    assert "LENGTH MISMATCH" in node_line
    assert "NOT exact" in node_line


def test_format_json_includes_content_breakdown_and_gates_full_parity():
    import json
    report = dataclasses.replace(_unatco_like_report(), content=_content(nodes_exact=False))
    data = json.loads(pl.format_json(report))
    assert data["content"]["exact"] is False
    assert data["content"]["nodes"]["exact"] is False
    assert data["content"]["nodes"]["indices_differ"] == 1
    assert data["content"]["nodes"]["fields_differ"] == 1
    assert data["content"]["surfs"]["exact"] is True
    assert data["full_parity"] is False


def test_full_parity_can_be_no_even_with_geometry_exact_and_lighting_full_due_to_content_alone():
    # A report shaped like what this build's live 6-level check is FOR: geometry counts match
    # (all 6), lighting is fully identical, but content diverges at one node -- FULL PARITY must
    # still be NO, which a count-only tool would have missed entirely.
    geo = pl.GeometryDelta(native=_counts(nodes=100, surfs=50), golden=_counts(nodes=100, surfs=50))
    light = pl.LightingSummary(total_records=20, identical_records=20,
                               shadow_bits_same=5, shadow_bits_total=5)
    report = pl.ParityReport(source_dx="/x/l.dx", content_hash="cd" * 32, level_name="l",
                             cache_hit=False, built_at=None, geometry=geo,
                             content=_content(nodes_exact=False), lighting=light)
    assert report.geometry.exact
    assert light.records_fully_identical
    assert not report.content.exact
    assert report.full_parity is False
