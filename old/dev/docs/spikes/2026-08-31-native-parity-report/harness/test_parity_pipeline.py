"""Offline tests for `parity_pipeline.ensure_golden`'s cache orchestration -- mocks out
`extract_trunk`/`build_golden` (the only docker-touching calls) so the hit/miss/repair control flow
is checkable without an editor. `parity_pipeline`'s own extraction/build functions are NOT unit
tested (they need docker + Wine); this file only pins the pure sequencing logic around them.

`build_root()` is deliberately NOT parameterized by `cache_root` (it always lives under this repo's
own `_scratch/`, never `/tmp` -- see its docstring), so unlike the `/tmp`-cached golden/meta half, a
test can't isolate it via `tmp_path`. Each test therefore uses UNIQUE `.dx` content (distinct content
hash -> distinct, collision-free `_scratch/uedcli-parity-cache/<hash>/` dir) and the `_cleanup_build_root`
fixture removes it afterward, so these tests never leak real files into the worktree.

Run directly (not part of `bin/test`, same as `test_parity_lib.py`):
    .venv/bin/python -m pytest dev/docs/spikes/2026-08-31-native-parity-report/harness/test_parity_pipeline.py
"""
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import parity_lib as pl              # noqa: E402
import parity_pipeline as pp         # noqa: E402


@pytest.fixture
def dx_file(tmp_path, request):
    """A `.dx` stand-in whose CONTENT is unique per test (the test's own node id) -- a distinct
    content hash, so `build_root()`'s real-filesystem scratch dir never collides across tests."""
    dx = tmp_path / "level.dx"
    dx.write_bytes(f"fake dx bytes for {request.node.name}".encode())
    h = pl.content_hash(dx)
    yield dx
    shutil.rmtree(pp.build_root(h).parent, ignore_errors=True)


def _touch_trunk(trunk_dir: Path) -> None:
    """Fakes a SUCCESSFUL `extract_trunk` -- must also drop the completion marker real
    `extract_trunk` writes at the very end (`pp._TRUNK_COMPLETE_MARKER`), or `trunk_is_complete`
    (correctly) refuses to trust the trunk and every "hit" test would re-extract."""
    (trunk_dir / "actors").mkdir(parents=True, exist_ok=True)
    (trunk_dir / pp._TRUNK_COMPLETE_MARKER).touch()


def test_cold_start_extracts_builds_and_marks_complete(dx_file, tmp_path):
    cache_root = tmp_path / "cache"
    calls = []

    def fake_extract(dx_path, trunk_dir, *, game, log_path, timeout):
        calls.append(("extract", trunk_dir))
        _touch_trunk(trunk_dir)

    def fake_build(trunk_dir, golden_path, *, game, log_path, timeout):
        calls.append(("build", golden_path))
        golden_path.write_bytes(b"fake golden")

    with patch.object(pp, "extract_trunk", side_effect=fake_extract), \
         patch.object(pp, "build_golden", side_effect=fake_build):
        layout, name, trunk_dir, cache_hit = pp.ensure_golden(dx_file, cache_root=cache_root)

    assert cache_hit is False
    assert name == "level"
    assert [c[0] for c in calls] == ["extract", "build"]
    meta = pl.read_meta(layout)
    assert meta["status"] == "complete"
    assert pl.is_cache_complete(layout)


def test_second_run_is_a_pure_cache_hit_no_extract_or_build(dx_file, tmp_path):
    cache_root = tmp_path / "cache"

    def fake_extract(dx_path, trunk_dir, *, game, log_path, timeout):
        _touch_trunk(trunk_dir)

    def fake_build(trunk_dir, golden_path, *, game, log_path, timeout):
        golden_path.write_bytes(b"fake golden")

    with patch.object(pp, "extract_trunk", side_effect=fake_extract), \
         patch.object(pp, "build_golden", side_effect=fake_build):
        pp.ensure_golden(dx_file, cache_root=cache_root)

    with patch.object(pp, "extract_trunk") as extract_mock, \
         patch.object(pp, "build_golden") as build_mock:
        layout, name, trunk_dir, cache_hit = pp.ensure_golden(dx_file, cache_root=cache_root)

    assert cache_hit is True
    extract_mock.assert_not_called()
    build_mock.assert_not_called()


def test_cache_hit_with_wiped_trunk_repairs_trunk_without_rebuilding_golden_or_touching_meta(
        dx_file, tmp_path):
    """The bug this test pins: a completed golden's `meta.json` must NOT regress to
    "extracting"/"building" just because `_scratch/` (the trunk's home) was wiped between runs --
    only the (cheap) trunk gets repaired; the (expensive) golden is never rebuilt."""
    cache_root = tmp_path / "cache"

    def fake_extract(dx_path, trunk_dir, *, game, log_path, timeout):
        _touch_trunk(trunk_dir)

    def fake_build(trunk_dir, golden_path, *, game, log_path, timeout):
        golden_path.write_bytes(b"fake golden")

    with patch.object(pp, "extract_trunk", side_effect=fake_extract), \
         patch.object(pp, "build_golden", side_effect=fake_build):
        layout, name, trunk_dir, _ = pp.ensure_golden(dx_file, cache_root=cache_root)
    meta_before = pl.read_meta(layout)

    shutil.rmtree(trunk_dir)

    with patch.object(pp, "extract_trunk", side_effect=fake_extract) as extract_mock, \
         patch.object(pp, "build_golden") as build_mock:
        layout2, name2, trunk_dir2, cache_hit = pp.ensure_golden(dx_file, cache_root=cache_root)

    assert cache_hit is True
    extract_mock.assert_called_once()          # trunk was repaired
    build_mock.assert_not_called()              # golden was NOT rebuilt
    assert (trunk_dir2 / "actors").is_dir()
    assert pl.read_meta(layout2) == meta_before  # meta.json untouched by the repair


def test_pipeline_error_is_raised_cleanly_on_extraction_failure(dx_file, tmp_path):
    cache_root = tmp_path / "cache"

    def failing_extract(dx_path, trunk_dir, *, game, log_path, timeout):
        raise pp.PipelineError("trunk extraction failed (exit 1) -- see /tmp/x/extract.log")

    with patch.object(pp, "extract_trunk", side_effect=failing_extract):
        with pytest.raises(pp.PipelineError, match="extract.log"):
            pp.ensure_golden(dx_file, cache_root=cache_root)


def test_partial_crashed_trunk_is_not_treated_as_complete(dx_file, tmp_path):
    """The bug a review round found and this pins: a trunk dir that exists (per-actor writes are
    individually atomic, per `t3dtree`) but whose extraction never finished -- no completion marker
    -- must be re-extracted, never silently reused as if it were the real, full trunk."""
    cache_root = tmp_path / "cache"
    h = pl.content_hash(dx_file)
    partial_trunk = pp.build_root(h) / "maps" / pp.level_name(dx_file)
    (partial_trunk / "actors" / "OneActor").mkdir(parents=True)  # partial: no completion marker

    assert not pp.trunk_is_complete(partial_trunk)

    def fake_extract(dx_path, trunk_dir, *, game, log_path, timeout):
        (trunk_dir / "actors").mkdir(parents=True, exist_ok=True)
        (trunk_dir / "actors" / "AllActors").mkdir()
        (trunk_dir / pp._TRUNK_COMPLETE_MARKER).touch()

    def fake_build(trunk_dir, golden_path, *, game, log_path, timeout):
        golden_path.write_bytes(b"fake golden")

    with patch.object(pp, "extract_trunk", side_effect=fake_extract) as extract_mock, \
         patch.object(pp, "build_golden", side_effect=fake_build):
        pp.ensure_golden(dx_file, cache_root=cache_root)

    extract_mock.assert_called_once()  # the partial trunk was NOT trusted -- re-extracted


def test_level_name_is_derived_from_filename_not_hardcoded():
    assert pp.level_name(Path("/x/01_NYC_UNATCOHQ.dx")) == "01_nyc_unatcohq"
    assert pp.level_name(Path("/x/06_HongKong_WanChai_Market.dx")) == "06_hongkong_wanchai_market"
    assert pp.level_name(Path("/x/weird name!!.dx")) == "weird_name__"


def test_build_root_lives_under_repo_tree_scratch_not_tmp():
    root = pp.build_root("deadbeef")
    assert "/tmp/" not in str(root)
    assert "_scratch" in root.parts
