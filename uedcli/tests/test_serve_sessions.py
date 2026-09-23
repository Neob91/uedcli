import pytest
from uedcli.serve.sessions import (
    create_session, get_session, list_sessions, delete_session, touch_session,
    SessionIndexCorruptError,
)


def test_create_session_returns_a_record_with_a_uuid7_id(tmp_path):
    rec = create_session(tmp_path, "unatco")
    assert rec.level == "unatco"
    assert len(rec.id) == 36  # uuid7() returns a dashed 8-4-4-4-12 string, confirmed in uedcli/uuid7.py


def test_create_session_writes_index_json_under_its_own_directory(tmp_path):
    rec = create_session(tmp_path, "unatco")
    assert (tmp_path / rec.id / "index.json").exists()


def test_create_session_defaults_last_seen_generation_to_zero(tmp_path):
    rec = create_session(tmp_path, "unatco")
    assert rec.last_seen_generation == 0


def test_create_session_seeds_last_seen_generation_from_caller(tmp_path):
    # The caller (app.py's create_session_route) passes the level's own current generation, so a
    # fresh session on a level that's already changed since server startup doesn't immediately
    # report `changes_available: True` for something it never had a chance to see.
    rec = create_session(tmp_path, "unatco", last_seen_generation=5)
    assert rec.last_seen_generation == 5
    assert get_session(tmp_path, rec.id).last_seen_generation == 5


def test_get_session_returns_the_created_record(tmp_path):
    rec = create_session(tmp_path, "unatco")
    fetched = get_session(tmp_path, rec.id)
    assert fetched == rec


def test_get_session_missing_id_returns_none(tmp_path):
    assert get_session(tmp_path, "doesnotexist") is None


def test_get_session_corrupt_index_raises_named_error(tmp_path):
    rec = create_session(tmp_path, "unatco")
    (tmp_path / rec.id / "index.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(SessionIndexCorruptError, match=rec.id):
        get_session(tmp_path, rec.id)


def test_list_sessions_returns_every_created_session(tmp_path):
    a = create_session(tmp_path, "unatco")
    b = create_session(tmp_path, "wanchai")
    ids = {s.id for s in list_sessions(tmp_path)}
    assert ids == {a.id, b.id}


def test_list_sessions_skips_a_corrupt_session_and_logs_a_warning(tmp_path, caplog):
    healthy_a = create_session(tmp_path, "unatco")
    corrupt = create_session(tmp_path, "wanchai")
    healthy_b = create_session(tmp_path, "bar")
    (tmp_path / corrupt.id / "index.json").write_text("{not json", encoding="utf-8")

    with caplog.at_level("WARNING", logger="uedcli.serve.sessions"):
        result = list_sessions(tmp_path)

    ids = {s.id for s in result}
    assert ids == {healthy_a.id, healthy_b.id}
    assert corrupt.id not in ids
    assert any(
        record.getMessage() == "session_index_corrupt_skipped" and record.session_id == corrupt.id
        for record in caplog.records
    )


def test_delete_session_removes_the_whole_directory(tmp_path):
    rec = create_session(tmp_path, "unatco")
    delete_session(tmp_path, rec.id)
    assert not (tmp_path / rec.id).exists()
    assert get_session(tmp_path, rec.id) is None


def test_touch_session_updates_last_active_at_when_stale(tmp_path):
    rec = create_session(tmp_path, "unatco")
    old_index = tmp_path / rec.id / "index.json"
    old_index.write_text(old_index.read_text().replace(rec.last_active_at, "2000-01-01T00:00:00Z"))
    touch_session(tmp_path, rec.id)
    assert get_session(tmp_path, rec.id).last_active_at != "2000-01-01T00:00:00Z"


def test_touch_session_is_a_noop_when_recently_touched(tmp_path):
    rec = create_session(tmp_path, "unatco")
    before = get_session(tmp_path, rec.id).last_active_at
    touch_session(tmp_path, rec.id)
    assert get_session(tmp_path, rec.id).last_active_at == before
