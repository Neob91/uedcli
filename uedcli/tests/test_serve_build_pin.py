"""`uedcli serve`'s on-disk build-pin pointer (plan Task 1): read + resolve-with-degrade over the
existing `preview_cache` scene store. No app/HTTP involved — pure unit tests."""
from __future__ import annotations

import json
from types import SimpleNamespace

from uedcli import preview_cache
from uedcli.serve import build_pin


def _project(tmp_path):
    return SimpleNamespace(root=str(tmp_path))


def test_load_pointer_returns_none_when_absent(tmp_path):
    assert build_pin.load_pointer(_project(tmp_path), "TestLevel") is None


def test_load_pointer_reads_a_hand_written_valid_file(tmp_path):
    project = _project(tmp_path)
    path = build_pin.pointer_path(project, "TestLevel")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"geom_hash": "abc123abc123", "light_hash": "def456def456"}))

    assert build_pin.load_pointer(project, "TestLevel") == ("abc123abc123", "def456def456")


def test_load_pointer_returns_none_for_a_corrupt_file(tmp_path):
    project = _project(tmp_path)
    path = build_pin.pointer_path(project, "TestLevel")
    path.parent.mkdir(parents=True)
    path.write_text("{not valid json")

    assert build_pin.load_pointer(project, "TestLevel") is None


def test_load_pointer_returns_none_for_a_file_missing_expected_keys(tmp_path):
    project = _project(tmp_path)
    path = build_pin.pointer_path(project, "TestLevel")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"geom_hash": "abc123abc123"}))   # no light_hash

    assert build_pin.load_pointer(project, "TestLevel") is None


def test_pointer_path_never_creates_the_build_subdir(tmp_path):
    project = _project(tmp_path)
    build_pin.pointer_path(project, "TestLevel")
    assert not (tmp_path / ".uedcli" / "build").exists()


def test_resolve_pin_returns_none_on_a_cache_miss(tmp_path):
    project = _project(tmp_path)
    assert build_pin.resolve_pin(project, "TestLevel", ("abc123abc123", "def456def456")) is None


def test_resolve_pin_returns_the_cached_payload_on_a_hit(tmp_path):
    project = _project(tmp_path)
    payload = ([1, 2, 3], ["tex"], ["Room"])
    preview_cache.store_scene(project, "TestLevel", "abc123abc123", "def456def456", payload)

    resolved = build_pin.resolve_pin(project, "TestLevel", ("abc123abc123", "def456def456"))

    assert resolved == payload
