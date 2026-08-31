"""Offline unit tests for `parity_lib.py` — no editor, no docker, no `uedcli` import needed.

Not part of `bin/test`'s `testpaths = uedcli` collection (this lives under `dev/docs/`, a
dev-tool/spike harness, not the uedcli package) — run directly:
    .venv/bin/python -m pytest dev/docs/spikes/2026-08-31-native-parity-report/harness/test_parity_lib.py
"""
import hashlib
import sys
from pathlib import Path

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


def test_full_parity_false_when_geometry_not_exact_even_if_lighting_full():
    geo = pl.GeometryDelta(native=_counts(nodes=1, verts=2), golden=_counts(nodes=1, verts=3))
    light = pl.LightingSummary(total_records=10, identical_records=10,
                               shadow_bits_same=1, shadow_bits_total=1)
    assert not pl.full_parity(geo, light)


def test_full_parity_false_when_lighting_partial_even_if_geometry_exact():
    geo = pl.GeometryDelta(native=_counts(), golden=_counts())
    light = pl.LightingSummary(total_records=10, identical_records=9,
                               shadow_bits_same=1, shadow_bits_total=1)
    assert not pl.full_parity(geo, light)


def test_full_parity_true_when_both_exact():
    geo = pl.GeometryDelta(native=_counts(nodes=5), golden=_counts(nodes=5))
    light = pl.LightingSummary(total_records=10, identical_records=10,
                               shadow_bits_same=1, shadow_bits_total=1)
    assert pl.full_parity(geo, light)


def _unatco_like_report(cache_hit=False):
    geo = pl.GeometryDelta(
        native=_counts(nodes=6321, surfs=3616, leaves=762, verts=10763, points=6339, vectors=599),
        golden=_counts(nodes=6321, surfs=3616, leaves=762, verts=10758, points=6339, vectors=599))
    light = pl.LightingSummary(total_records=3345, identical_records=2797,
                               shadow_bits_same=920000, shadow_bits_total=922706)
    return pl.ParityReport(source_dx="/x/01_NYC_UNATCOHQ.dx", content_hash="deadbeef" * 8,
                           level_name="unatco", cache_hit=cache_hit, built_at="2026-08-31",
                           geometry=geo, lighting=light)


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
                             cache_hit=False, built_at=None, geometry=geo, lighting=light)
    data = json.loads(pl.format_json(report))
    assert data["full_parity"] is True
