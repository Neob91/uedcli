from types import SimpleNamespace

from uedcli import preview_cache as pc


def _proj(tmp_path):
    return SimpleNamespace(root=str(tmp_path))


def test_geometry_round_trips(tmp_path):
    proj = _proj(tmp_path)
    payload = (b"body", [(1, 2)], [0, None], [(4, 4, b"rgb", b"mask")])
    assert pc.load_geometry(proj, "lvl", "abc123abc123") is None
    pc.store_geometry(proj, "lvl", "abc123abc123", payload)
    assert pc.load_geometry(proj, "lvl", "abc123abc123") == payload


def test_geometry_miss_on_different_hash(tmp_path):
    proj = _proj(tmp_path)
    pc.store_geometry(proj, "lvl", "abc123abc123", (b"x", [], [], []))
    assert pc.load_geometry(proj, "lvl", "def456def456") is None


def test_scene_round_trips_and_is_keyed_on_both_hashes(tmp_path):
    proj = _proj(tmp_path)
    payload = ([(1, 2, 3)], [(4, 4, b"rgb", b"mask")])
    pc.store_scene(proj, "lvl", "geomhash1234", "lighthash123", payload)
    assert pc.load_scene(proj, "lvl", "geomhash1234", "lighthash123") == payload
    assert pc.load_scene(proj, "lvl", "geomhash1234", "otherlight12") is None
    assert pc.load_scene(proj, "lvl", "othergeom123", "lighthash123") is None


def test_corrupt_cache_file_reads_as_a_miss(tmp_path):
    proj = _proj(tmp_path)
    pc.store_geometry(proj, "lvl", "abc123abc123", (b"x", [], [], []))
    d = pc._dir(proj)
    for p in d.glob("scenegeo*"):
        p.write_bytes(b"not valid marshal data at all")
    assert pc.load_geometry(proj, "lvl", "abc123abc123") is None


def test_sweep_old_versions_deletes_old_but_keeps_current(tmp_path):
    proj = _proj(tmp_path)
    d = pc._dir(proj)
    old_geo = d / "scenegeo0__lvl__abc123abc123.marshal"
    old_lit = d / "scenelit0__lvl__abc123abc123def456def456.marshal"
    old_geo.write_bytes(b"stale")
    old_lit.write_bytes(b"stale")
    pc.store_geometry(proj, "lvl", "abc123abc123", (b"fresh", [], [], []))
    assert not old_geo.exists() and not old_lit.exists()
    assert pc.load_geometry(proj, "lvl", "abc123abc123") == (b"fresh", [], [], [])


def test_sweep_old_versions_leaves_unrelated_files_alone(tmp_path):
    proj = _proj(tmp_path)
    d = pc._dir(proj)
    other = d / "materialized__lvl__abc123abc123.dx"
    other.write_bytes(b"unrelated")
    pc.store_scene(proj, "lvl", "geomhash1234", "lighthash123", ([], []))
    assert other.exists()
