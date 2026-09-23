from pathlib import Path

from uedcli import build_cache


class _Project:
    def __init__(self, root):
        self.root = str(root)
        # No configured budget in the brief's own literal fixture would crash
        # `evict_unreferenced` on the no-override test below (it reads this attribute whenever
        # `max_bytes` isn't passed). 0 exercises the real fallback path (project's own setting,
        # not an override) while still proving the live-reference set is never touched (see
        # test_evict_unreferenced_never_touches_a_live_entry_even_over_budget's explicit override).
        self.build_cache_max_bytes = 0


def test_store_and_load_geometry_round_trips(tmp_path):
    project = _Project(tmp_path)
    build_cache.store_geometry(project, "unatco", "abc123def456", {"polys": []})
    assert build_cache.load_geometry(project, "unatco", "abc123def456") == {"polys": []}


def test_geometry_lives_under_versioned_per_level_path(tmp_path):
    project = _Project(tmp_path)
    build_cache.store_geometry(project, "unatco", "abc123def456", {"polys": []})
    expected = tmp_path / ".uedcli" / "build" / "cache" / "v3" / "unatco" / "geometry" / "abc123def456.marshal"
    assert expected.exists()


def test_lighting_nests_under_its_geometry_hash(tmp_path):
    project = _Project(tmp_path)
    build_cache.store_scene(project, "unatco", "geomhash1234", "lighthash5678", {"polys": []})
    expected = (tmp_path / ".uedcli" / "build" / "cache" / "v3" / "unatco" / "lighting"
                / "geomhash1234" / "lighthash5678.marshal")
    assert expected.exists()


def test_load_scene_missing_entry_is_a_cache_miss_not_an_error(tmp_path):
    project = _Project(tmp_path)
    assert build_cache.load_scene(project, "unatco", "nope", "nope") is None


def test_load_geometry_corrupt_file_degrades_to_cache_miss(tmp_path):
    project = _Project(tmp_path)
    p = tmp_path / ".uedcli" / "build" / "cache" / "v3" / "unatco" / "geometry"
    p.mkdir(parents=True)
    (p / "abc123def456.marshal").write_bytes(b"not marshal data")
    assert build_cache.load_geometry(project, "unatco", "abc123def456") is None


def test_evict_unreferenced_removes_only_entries_with_no_live_reference(tmp_path):
    project = _Project(tmp_path)
    build_cache.store_geometry(project, "unatco", "keepme000001", {"polys": []})
    build_cache.store_geometry(project, "unatco", "dropme000001", {"polys": []})
    result = build_cache.evict_unreferenced(
        project, "unatco", live_geom_hashes={"keepme000001"}, live_pairs=set())
    kept = tmp_path / ".uedcli" / "build" / "cache" / "v3" / "unatco" / "geometry" / "keepme000001.marshal"
    dropped = tmp_path / ".uedcli" / "build" / "cache" / "v3" / "unatco" / "geometry" / "dropme000001.marshal"
    assert kept.exists()
    assert not dropped.exists()
    assert result["evicted"] == 1


def test_evict_unreferenced_never_touches_a_live_entry_even_over_budget(tmp_path):
    project = _Project(tmp_path)
    build_cache.store_geometry(project, "unatco", "onlylive0001", {"polys": list(range(1000))})
    result = build_cache.evict_unreferenced(
        project, "unatco", live_geom_hashes={"onlylive0001"}, live_pairs=set(), max_bytes=1)
    p = tmp_path / ".uedcli" / "build" / "cache" / "v3" / "unatco" / "geometry" / "onlylive0001.marshal"
    assert p.exists()
    assert result["evicted"] == 0


def test_evict_unreferenced_kept_entries_counts_geometry_and_lighting(tmp_path):
    project = _Project(tmp_path)
    build_cache.store_geometry(project, "unatco", "geomhash0001", {"polys": []})
    build_cache.store_scene(project, "unatco", "geomhash0002", "lighthash001", {"polys": []})
    result = build_cache.evict_unreferenced(
        project, "unatco",
        live_geom_hashes={"geomhash0001", "geomhash0002"},
        live_pairs={("geomhash0002", "lighthash001")})
    assert result["evicted"] == 0
    assert result["kept_entries"] == 2


def test_evict_unreferenced_evicts_oldest_unreferenced_first_over_budget(tmp_path):
    import os, time
    project = _Project(tmp_path)
    build_cache.store_geometry(project, "unatco", "older0000001", {"polys": [0] * 500})
    d = tmp_path / ".uedcli" / "build" / "cache" / "v3" / "unatco" / "geometry"
    os.utime(d / "older0000001.marshal", (time.time() - 1000, time.time() - 1000))
    build_cache.store_geometry(project, "unatco", "newer0000001", {"polys": [0] * 500})
    result = build_cache.evict_unreferenced(
        project, "unatco", live_geom_hashes=set(), live_pairs=set(),
        max_bytes=(d / "newer0000001.marshal").stat().st_size)
    assert not (d / "older0000001.marshal").exists()
    assert (d / "newer0000001.marshal").exists()
