"""New session-scoped build pin (`sessions/<sid>/build.json`, raise-on-corrupt) added by the
persistent-GUI-editing-sessions feature. The level-scoped pin's own coverage lives in
`test_serve_build_pin.py` (re-keyed, not duplicated here)."""
from __future__ import annotations

import pytest
from uedcli.serve.build_pin import (
    session_pointer_path, load_session_pointer, write_session_pointer, SessionPointerCorruptError,
    level_pointer_path, load_level_pointer, write_level_pointer,
)


class _Project:
    def __init__(self, root):
        self.root = str(root)


def test_session_pointer_path_is_under_sessions_dir(tmp_path):
    p = session_pointer_path(tmp_path, "abc123")
    assert p == tmp_path / "abc123" / "build.json"


def test_write_then_load_session_pointer_round_trips(tmp_path):
    write_session_pointer(tmp_path, "abc123", "geomhash0001", "lighthash0001")
    assert load_session_pointer(tmp_path, "abc123") == ("geomhash0001", "lighthash0001")


def test_load_session_pointer_missing_file_raises_named_error(tmp_path):
    with pytest.raises(SessionPointerCorruptError, match="abc123"):
        load_session_pointer(tmp_path, "abc123")


def test_load_session_pointer_corrupt_json_raises_named_error(tmp_path):
    d = tmp_path / "abc123"
    d.mkdir()
    (d / "build.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(SessionPointerCorruptError, match="build.json"):
        load_session_pointer(tmp_path, "abc123")


def test_level_pointer_path_is_under_build_pin_level(tmp_path):
    project = _Project(tmp_path)
    p = level_pointer_path(project, "unatco")
    assert p == tmp_path / ".uedcli" / "build" / "pin" / "unatco" / "current.json"


def test_write_then_load_level_pointer_round_trips(tmp_path):
    project = _Project(tmp_path)
    write_level_pointer(project, "unatco", "geomhash0002", "lighthash0002")
    assert load_level_pointer(project, "unatco") == ("geomhash0002", "lighthash0002")


def test_load_level_pointer_missing_degrades_to_none(tmp_path):
    project = _Project(tmp_path)
    assert load_level_pointer(project, "unatco") is None


def test_load_level_pointer_corrupt_degrades_to_none_not_an_exception(tmp_path):
    project = _Project(tmp_path)
    p = level_pointer_path(project, "unatco")
    p.parent.mkdir(parents=True)
    p.write_text("{not json", encoding="utf-8")
    assert load_level_pointer(project, "unatco") is None
