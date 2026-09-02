"""Offline tests for `sweep_lib.py`'s pure logic -- corpus/skip sets, cache-path resolution, and the
report-JSON -> `LevelResult` conversion (including the owner-flagged content-exact-fraction /
length-mismatch distinction). No docker, no subprocess.

Run directly (same as `test_parity_lib.py`):
    .venv/bin/python -m pytest dev/docs/spikes/2026-08-31-native-parity-report/harness/test_sweep_lib.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sweep_lib as sl  # noqa: E402


def test_corpus_and_skipped_are_disjoint_and_cover_no_duplicates():
    assert len(sl.CORPUS) == len(set(sl.CORPUS)) == 18
    assert len(sl.SKIPPED) == 3
    assert set(sl.CORPUS).isdisjoint(sl.SKIPPED)


def test_skipped_levels_match_the_task_spec():
    assert set(sl.SKIPPED) == {"99_Endgame4.dx", "DXMP_Smuggler.dx", "04_NYC_Street.dx"}


def test_repo_root_finds_real_git_dir_not_worktree_gitlink(tmp_path):
    main = tmp_path / "main"
    (main / ".git").mkdir(parents=True)  # real repo: .git is a DIRECTORY
    worktree = main / ".claude" / "worktrees" / "wt1"
    worktree.mkdir(parents=True)
    (worktree / ".git").write_text("gitdir: /main/.git/worktrees/wt1\n")  # worktree: .git is a FILE
    deep = worktree / "dev" / "docs" / "spikes" / "x" / "harness"
    deep.mkdir(parents=True)

    assert sl.repo_root(deep) == main
    assert sl.repo_root(main) == main


def test_shared_trunk_cache_root_is_fixed_regardless_of_which_worktree_asks(tmp_path):
    main = tmp_path / "main"
    (main / ".git").mkdir(parents=True)
    wt_a = main / ".claude" / "worktrees" / "a"
    wt_b = main / ".claude" / "worktrees" / "b"
    for wt in (wt_a, wt_b):
        wt.mkdir(parents=True)
        (wt / ".git").write_text("gitdir: elsewhere\n")

    expect = main / ".claude" / "worktrees" / "uedcli-parity-trunk-cache"
    assert sl.shared_trunk_cache_root(wt_a) == expect
    assert sl.shared_trunk_cache_root(wt_b) == expect
    assert sl.shared_trunk_cache_root(main) == expect


def _fake_report(*, deltas, content_overrides=None, identical_pct=100.0, shadow_bit_pct=100.0,
                 full_parity=True, cache_hit=True):
    content = {
        "nodes": {"native_len": 10, "golden_len": 10, "indices_differ": 0, "exact": True},
        "surfs": {"native_len": 5, "golden_len": 5, "indices_differ": 0, "exact": True},
        "leaves": {"native_len": 3, "golden_len": 3, "indices_differ": 0, "exact": True},
    }
    if content_overrides:
        for k, v in content_overrides.items():
            content[k].update(v)
    return {
        "cache_hit": cache_hit,
        "geometry": {"deltas": deltas},
        "content": content,
        "lighting": {"identical_pct": identical_pct, "shadow_bit_pct": shadow_bit_pct},
        "full_parity": full_parity,
    }


def test_level_result_all_exact_reports_geometry_6_and_full_parity():
    report = _fake_report(deltas={"nodes": 0, "surfs": 0, "leaves": 0, "verts": 0, "points": 0,
                                  "vectors": 0})
    r = sl.level_result_from_report_json(level="x", dx_path="x.dx", elapsed_s=1.0, report=report)
    assert r.status == "OK"
    assert r.geometry_match_count == 6
    assert r.content_exact_fraction == 1.0
    assert r.content_length_mismatch is False
    assert r.full_parity is True


def test_level_result_partial_geometry_match_counts_correctly():
    report = _fake_report(deltas={"nodes": 0, "surfs": 5, "leaves": 0, "verts": 12, "points": 0,
                                  "vectors": -3})
    r = sl.level_result_from_report_json(level="x", dx_path="x.dx", elapsed_s=1.0, report=report)
    assert r.geometry_match_count == 3  # nodes/leaves/points match, surfs/verts/vectors don't
    assert r.nodes_match is True and r.surfs_match is False


def test_same_length_content_diffs_reduce_fraction_but_no_length_mismatch():
    # 6314 nodes, 862 diverge -- the UNATCO-shaped case: same counts, real content divergence.
    report = _fake_report(
        deltas={"nodes": 0, "surfs": 0, "leaves": 0, "verts": 0, "points": 0, "vectors": 0},
        content_overrides={"nodes": {"native_len": 100, "golden_len": 100, "indices_differ": 20,
                                     "exact": False}})
    r = sl.level_result_from_report_json(level="x", dx_path="x.dx", elapsed_s=1.0, report=report)
    assert r.geometry_match_count == 6          # counts alone look perfect
    assert r.content_length_mismatch is False
    assert 0.0 < r.content_exact_fraction < 1.0  # but real content divergence is visible
    assert "idx differ" in r.notes


def test_length_mismatch_is_flagged_even_with_a_clean_common_prefix():
    report = _fake_report(
        deltas={"nodes": 5, "surfs": 0, "leaves": 0, "verts": 0, "points": 0, "vectors": 0},
        content_overrides={"nodes": {"native_len": 105, "golden_len": 100, "indices_differ": 0,
                                     "exact": False}})
    r = sl.level_result_from_report_json(level="x", dx_path="x.dx", elapsed_s=1.0, report=report)
    assert r.content_length_mismatch is True
    assert "LENGTH MISMATCH" in r.notes


def test_sweep_json_round_trips(tmp_path):
    run = sl.SweepRun(started_at="2026-09-02T00:00:00+00:00", concurrency=2, rebuild_timeout=3600.0,
                      hang_timeout=6300.0,
                      results=(sl.LevelResult(level="a", dx_path="a.dx", status="SKIPPED",
                                              notes="known-unbuildable"),))
    out = tmp_path / "sweep.json"
    sl.write_sweep_json(run, out)
    loaded = sl.read_sweep_json(out)
    assert loaded == run
