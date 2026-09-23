"""`uedcli serve`'s staging store for GUI actor edits (Plan Task 5): write/read/clear/discard staged
actor locations with baseline tracking, keyed by session id, plus reference-aware blob eviction. No
app/HTTP involved -- pure unit tests."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from uedcli.serve.snapshots import StagingStore


def test_stage_then_read_staged_round_trips_exact_decimal(tmp_path: Path) -> None:
    store = StagingStore(tmp_path / "sessions", tmp_path / "blobs")
    store.stage("sess1", "Light12", actor_t3d_text="Begin Actor...",
                baseline_location=(Decimal("1.5"), Decimal("2"), Decimal("3")),
                staged_location=(Decimal("1.5"), Decimal("2"), Decimal("4")))
    staged = store.read_staged("sess1")
    assert staged["Light12"].staged_location == (Decimal("1.5"), Decimal("2"), Decimal("4"))


def test_stage_writes_manifest_under_sessions_root_not_blobs_root(tmp_path: Path) -> None:
    store = StagingStore(tmp_path / "sessions", tmp_path / "blobs")
    store.stage("sess1", "Light12", actor_t3d_text="Begin Actor...",
                baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
                staged_location=(Decimal(0), Decimal(0), Decimal(1)))
    assert (tmp_path / "sessions" / "sess1" / "staged.json").exists()


def test_stage_manifest_write_is_atomic(tmp_path: Path, monkeypatch) -> None:
    store = StagingStore(tmp_path / "sessions", tmp_path / "blobs")
    import uedcli.serve.snapshots as mod
    calls = []
    real = mod.atomic_write_json
    monkeypatch.setattr(mod, "atomic_write_json", lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    store.stage("sess1", "Light12", actor_t3d_text="x",
                baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
                staged_location=(Decimal(0), Decimal(0), Decimal(1)))
    assert calls == [1]


def test_clear_actor_removes_only_that_actor(tmp_path: Path) -> None:
    store = StagingStore(tmp_path / "sessions", tmp_path / "blobs")
    store.stage("sess1", "A", actor_t3d_text="x",
                baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
                staged_location=(Decimal(0), Decimal(0), Decimal(1)))
    store.stage("sess1", "B", actor_t3d_text="y",
                baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
                staged_location=(Decimal(0), Decimal(0), Decimal(2)))
    store.clear_actor("sess1", "A")
    assert set(store.read_staged("sess1")) == {"B"}


def test_discard_removes_the_whole_manifest(tmp_path: Path) -> None:
    store = StagingStore(tmp_path / "sessions", tmp_path / "blobs")
    store.stage("sess1", "A", actor_t3d_text="x",
                baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
                staged_location=(Decimal(0), Decimal(0), Decimal(1)))
    store.discard("sess1")
    assert store.read_staged("sess1") == {}


def test_restaging_an_already_staged_actor_keeps_its_original_baseline(tmp_path: Path) -> None:
    """Regression test carried over from the existing test_stage_read_restage_keeps_baseline_
    discard_clear in today's test_serve_snapshots.py: staging the SAME actor a second time (a second
    drag) must NOT overwrite its baseline_location with the caller's newly-supplied value -- the
    baseline is what Save's conflict check compares against the CURRENT trunk, so an overwritten
    baseline would silently corrupt conflict detection."""
    store = StagingStore(tmp_path / "sessions", tmp_path / "blobs")
    store.stage("sess1", "Light12", actor_t3d_text="first",
                baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
                staged_location=(Decimal(0), Decimal(0), Decimal(1)))
    store.stage("sess1", "Light12", actor_t3d_text="second",
                baseline_location=(Decimal(9), Decimal(9), Decimal(9)),  # caller passes a DIFFERENT baseline
                staged_location=(Decimal(0), Decimal(0), Decimal(2)))
    staged = store.read_staged("sess1")
    assert staged["Light12"].baseline_location == (Decimal(0), Decimal(0), Decimal(0))  # original kept
    assert staged["Light12"].staged_location == (Decimal(0), Decimal(0), Decimal(2))  # new value used


def test_two_sessions_staging_the_same_content_share_one_blob(tmp_path: Path) -> None:
    store = StagingStore(tmp_path / "sessions", tmp_path / "blobs")
    store.stage("sess1", "A", actor_t3d_text="same text",
                baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
                staged_location=(Decimal(0), Decimal(0), Decimal(1)))
    store.stage("sess2", "B", actor_t3d_text="same text",
                baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
                staged_location=(Decimal(0), Decimal(0), Decimal(1)))
    h1 = store.read_staged("sess1")["A"].blob_hash
    h2 = store.read_staged("sess2")["B"].blob_hash
    assert h1 == h2
    blob_files = list((tmp_path / "blobs").rglob("*"))
    assert len([f for f in blob_files if f.is_file()]) == 1


def test_evict_unreferenced_blobs_keeps_blobs_named_in_live_hashes(tmp_path: Path) -> None:
    store = StagingStore(tmp_path / "sessions", tmp_path / "blobs")
    store.stage("sess1", "A", actor_t3d_text="keep me",
                baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
                staged_location=(Decimal(0), Decimal(0), Decimal(1)))
    keep_hash = store.read_staged("sess1")["A"].blob_hash
    store.discard("sess1")  # sess1 no longer references it, but pass it as still-live
    result = store.evict_unreferenced_blobs(live_hashes={keep_hash})
    assert result["evicted"] == 0
    assert (tmp_path / "blobs" / keep_hash[:2] / keep_hash).exists()


def test_evict_unreferenced_blobs_removes_blobs_named_in_no_manifest(tmp_path: Path) -> None:
    store = StagingStore(tmp_path / "sessions", tmp_path / "blobs")
    store.stage("sess1", "A", actor_t3d_text="drop me",
                baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
                staged_location=(Decimal(0), Decimal(0), Decimal(1)))
    h = store.read_staged("sess1")["A"].blob_hash
    store.discard("sess1")
    result = store.evict_unreferenced_blobs(live_hashes=set())
    assert result["evicted"] == 1
    assert not (tmp_path / "blobs" / h[:2] / h).exists()
