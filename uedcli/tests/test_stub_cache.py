from uedcli.stub_cache import CacheKey, cached_stub, store_stub, list_manifests


def _key(**overrides) -> CacheKey:
    base = dict(source_sha="src-aaa", dep_shas={"Engine": "e1"}, substrate_id="sub1", toolchain_id="tc1")
    base.update(overrides)
    return CacheKey(**base)


def _built(tmp_path, data=b"V69BYTES"):
    build = tmp_path / "work"
    build.mkdir(exist_ok=True)
    u = build / "DeusExItems.u"
    u.write_bytes(data)
    return u


def test_store_then_cached_returns_the_stub_for_a_matching_key(tmp_path):
    # Arrange
    cache = tmp_path / "cache"
    key = _key()

    # Act
    stored = store_stub(cache, "DeusExItems", _built(tmp_path), key)

    # Assert — bytes landed, and a matching-key lookup finds it.
    assert stored == cache / "DeusExItems.u"
    assert stored.read_bytes() == b"V69BYTES"
    assert cached_stub(cache, "DeusExItems", key) == stored


def test_cached_returns_none_when_the_key_drifted(tmp_path):
    # Arrange — store under one key, look up under a changed source_sha.
    cache = tmp_path / "cache"
    store_stub(cache, "DeusExItems", _built(tmp_path), _key())

    # Act / Assert
    assert cached_stub(cache, "DeusExItems", _key(source_sha="src-CHANGED")) is None


def test_cached_returns_none_when_no_stub_was_built(tmp_path):
    assert cached_stub(tmp_path / "cache", "Nope", _key()) is None


def test_cached_rejects_a_torn_pair_whose_u_does_not_match_the_sidecar(tmp_path):
    # Arrange — store, then a concurrent builder's differing .u lands without a sidecar update.
    cache = tmp_path / "cache"
    store_stub(cache, "DeusExItems", _built(tmp_path), _key())
    (cache / "DeusExItems.u").write_bytes(b"DIFFERENT-CONCURRENT-BYTES")

    # Act / Assert — output_sha no longer re-confirms, so the pair is rejected (rebuild).
    assert cached_stub(cache, "DeusExItems", _key()) is None


def test_list_manifests_returns_each_cached_package_name_sorted(tmp_path):
    # Arrange
    cache = tmp_path / "cache"
    store_stub(cache, "Bravo", _built(tmp_path), _key())
    store_stub(cache, "Alpha", _built(tmp_path), _key())

    # Act
    files = [m.file for m in list_manifests(cache)]

    # Assert
    assert files == ["Alpha.u", "Bravo.u"]


def test_cached_treats_a_corrupt_sidecar_as_a_miss_not_a_crash(tmp_path):
    # Arrange — a built stub, then its sidecar is corrupted (disk error / hand-edit / schema drift).
    cache = tmp_path / "cache"
    store_stub(cache, "DeusExItems", _built(tmp_path), _key())
    (cache / "DeusExItems.json").write_text("{ this is not valid json")

    # Act / Assert — a sidecar that can't be read is a miss (rebuild), never an exception.
    assert cached_stub(cache, "DeusExItems", _key()) is None


def test_cached_reuses_regardless_of_built_at(tmp_path):
    # Arrange — a stub stored, then its sidecar's built_at is changed.
    import json
    cache = tmp_path / "cache"
    store_stub(cache, "DeusExItems", _built(tmp_path), _key())
    sidecar = cache / "DeusExItems.json"
    data = json.loads(sidecar.read_text())
    data["built_at"] = "1999-12-31T23:59:59+00:00"
    sidecar.write_text(json.dumps(data))

    # Act / Assert — built_at is not part of the reuse key.
    assert cached_stub(cache, "DeusExItems", _key()) == cache / "DeusExItems.u"
