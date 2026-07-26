from PIL import Image

from uedcli import texture_catalog as tc


def test_it_defines_the_twelve_named_palette_in_order():
    assert tc.PALETTE_NAMES == (
        "black", "white", "grey", "red", "orange", "yellow",
        "green", "blue", "purple", "pink", "brown", "tan",
    )
    # every name maps to an RGB triple in 0..255
    for name, rgb in tc.PALETTE:
        assert len(rgb) == 3 and all(0 <= c <= 255 for c in rgb)


def test_it_parses_group_prefixed_and_groupless_pcx_stems():
    assert tc.parse_pcx_stem("Skins.Wood") == ("Skins", "Wood")
    assert tc.parse_pcx_stem("Wood") == (None, "Wood")
    # only the LAST dot splits group from name (a name can't contain a dot, but a multi-part
    # group could) — group is everything before the last dot
    assert tc.parse_pcx_stem("A.B.Wood") == ("A.B", "Wood")


def test_it_assigns_two_part_refs_but_three_part_on_cross_group_collision():
    # input: list of (stem, group, name)
    stems = [("Skins.Wood", "Skins", "Wood"),
             ("Decor.Wood", "Decor", "Wood"),     # collides with Skins.Wood on Package.Name
             ("Metal", None, "Metal")]            # groupless, no collision
    refs = tc.assign_refs("DeusExDeco", stems)
    assert refs == {
        "Skins.Wood": "DeusExDeco.Skins.Wood",    # 3-part — disambiguated
        "Decor.Wood": "DeusExDeco.Decor.Wood",    # 3-part — disambiguated
        "Metal": "DeusExDeco.Metal",              # 2-part — clean
    }


def test_it_hashes_rgb_pixels_so_palette_recolor_changes_it_but_reencode_does_not():
    base = Image.new("P", (4, 4))
    base.putpalette([0, 0, 0] + [10, 20, 30] * 255)
    base.putdata([1] * 16)                                  # all index 1 -> (10,20,30)
    h1 = tc.image_hash(base)
    h_same = tc.image_hash(base.copy())                     # re-encode-equivalent: same pixels
    assert h1 == h_same
    recolored = Image.new("P", (4, 4))
    recolored.putpalette([0, 0, 0] + [99, 99, 99] * 255)    # SAME indices, different palette
    recolored.putdata([1] * 16)                             # now (99,99,99)
    assert tc.image_hash(recolored) != h1                   # visible change -> different hash


def test_nearest_color_snaps_to_the_palette():
    assert tc.nearest_color((2, 2, 2)) == "black"
    assert tc.nearest_color((250, 250, 250)) == "white"
    assert tc.nearest_color((205, 35, 35)) == "red"


def test_derive_colors_is_ordered_capped_and_thresholded():
    # 70% brownish, 30% greyish -> ["brown", "grey"] (descending share)
    img = Image.new("RGB", (10, 10))
    px = [(110, 70, 40)] * 70 + [(128, 128, 128)] * 30
    img.putdata(px)
    assert tc.derive_colors(img) == ["brown", "grey"]


def test_derive_colors_drops_sub_threshold_and_caps_at_three():
    img = Image.new("RGB", (10, 10))
    # 45 grey, 28 red, 19 blue, 8 green (= 100 px). Green 8% < 12% -> dropped; the other three
    # clear 12% comfortably (wide margins, no value near the threshold) -> ["grey", "red", "blue"]
    # (descending share, cap 3). Shares are EXACT because the 10x10 image is <= THUMB so it is
    # NOT resized (see derive_colors).
    px = ([(128, 128, 128)] * 45 + [(200, 30, 30)] * 28 + [(40, 80, 190)] * 19
          + [(40, 150, 60)] * 8)
    img.putdata(px)
    assert tc.derive_colors(img) == ["grey", "red", "blue"]


def test_derive_colors_monochrome_yields_one_name():
    img = Image.new("RGB", (8, 8), (0, 0, 0))
    assert tc.derive_colors(img) == ["black"]


def test_real_ucc_pcx_decodes_and_derives(tmp_path):
    # Closes spec spike #1: a REAL batchexport PCX (committed by Task 0) must decode faithfully —
    # not just a Pillow-authored one. Skips if the spike was deferred (no live container).
    import pathlib
    fixture = pathlib.Path(__file__).parent / "fixtures" / "sample.pcx"
    if not fixture.exists():
        import pytest
        pytest.skip("no real UCC PCX fixture (Task 0 spike deferred to integration)")
    img = Image.open(fixture)
    assert tc.image_hash(img).startswith("sha256:")
    assert all(c in tc.PALETTE_NAMES for c in tc.derive_colors(img))   # snaps to the vocabulary


def test_derive_colors_high_entropy_keeps_the_single_top_name():
    # 11 distinct palette colors so NO name clears 12%: black=12, the next 10 names=10 each
    # (total 112 px). Every share < 12% -> `kept` is empty -> the fallback keeps the single
    # most-frequent name (black, 12). Exercises the no-name-over-threshold branch.
    img = Image.new("RGB", (16, 7))                  # 112 px
    px = [tc.PALETTE[0][1]] * 12                      # black x12
    for _name, rgb in tc.PALETTE[1:11]:              # 10 more names x10 each = 100
        px += [rgb] * 10
    img.putdata(px)
    assert tc.derive_colors(img) == ["black"]


def test_manifest_json_round_trips_and_save_is_atomic(tmp_path):
    entry = tc.TextureEntry(
        name="Wood", group="Skins", ref="DeusExDeco.Wood", width=256, height=256,
        image_hash="sha256:aa", colors=["brown"], colors_source="auto",
        tags=[], description="", stale=False, removed=False)
    m = tc.Manifest(package="DeusExDeco", package_file="DeusExDeco.utx",
                    package_hash="sha256:bb", textures={"Skins.Wood": entry})
    assert tc.from_json(tc.to_json(m)) == m                    # round-trips
    path = tc.manifest_path(tmp_path, "DeusExDeco")
    tc.save_manifest(path, m)
    assert tc.load_manifest(path) == m
    assert tc.load_manifest(tmp_path / "Absent.json") is None  # missing -> None
    # atomic: no leftover temp beside the manifest
    assert [p.name for p in path.parent.iterdir()] == ["DeusExDeco.json"]


def _exp(stem, name, group, h, colors=("brown",)):
    return tc.ExportedTexture(stem=stem, name=name, group=group, width=64, height=64,
                              image_hash=h, colors=list(colors))


def _classified_entry(stem="Skins.Wood", name="Wood", group="Skins", h="sha256:1",
                      ref="DeusExDeco.Wood", source="auto", removed=False, stale=False):
    return tc.TextureEntry(name=name, group=group, ref=ref, width=64, height=64, image_hash=h,
                           colors=["brown"], colors_source=source, tags=["wood"],
                           description="planks", stale=stale, removed=removed)


def test_reconcile_new_changed_unchanged_removed():
    prior = tc.Manifest(package="P", package_file="P.utx", package_hash="old",
                        textures={"Skins.Wood": _classified_entry(),
                                  "Skins.Gone": _classified_entry(stem="Skins.Gone", name="Gone",
                                                                   h="sha256:9", ref="P.Gone")})
    exported = [_exp("Skins.Wood", "Wood", "Skins", "sha256:2"),      # changed pixels
                _exp("Skins.New", "New", "Skins", "sha256:7")]        # brand new
    out = tc.reconcile(prior, package="P", package_file="P.utx", package_hash="new", exported=exported)
    assert out.textures["Skins.Wood"].stale is True                  # changed -> stale
    assert out.textures["Skins.Wood"].tags == ["wood"]               # classification kept
    assert out.textures["Skins.New"].colors_source == "auto"         # new -> empty/auto
    assert out.textures["Skins.New"].tags == []
    assert out.textures["Skins.Gone"].removed is True                # gone -> removed
    assert out.textures["Skins.Gone"].stale is False                 # removed clears stale
    assert out.textures["Skins.Gone"].tags == ["wood"]               # classification retained


def test_reconcile_preserves_a_set_colors_override_but_redrives_auto():
    prior = tc.Manifest(package="P", package_file="P.utx", package_hash="old", textures={
        "Skins.A": _classified_entry(stem="Skins.A", name="A", h="sha256:1", ref="P.A", source="set"),
        "Skins.B": _classified_entry(stem="Skins.B", name="B", h="sha256:1", ref="P.B", source="auto")})
    # both change pixels; both arrive with auto colors ["grey"]
    exported = [_exp("Skins.A", "A", "Skins", "sha256:2", colors=("grey",)),
                _exp("Skins.B", "B", "Skins", "sha256:2", colors=("grey",))]
    out = tc.reconcile(prior, package="P", package_file="P.utx", package_hash="new", exported=exported)
    assert out.textures["Skins.A"].colors == ["brown"]              # SET override preserved
    assert out.textures["Skins.B"].colors == ["grey"]              # AUTO re-derived


def test_reconcile_rename_carries_classification_at_most_once():
    prior = tc.Manifest(package="P", package_file="P.utx", package_hash="old", textures={
        "Skins.Old": _classified_entry(stem="Skins.Old", name="Old", h="sha256:5", ref="P.Old")})
    # Old is gone; two NEW stems share its image_hash — only the sorted-first inherits
    exported = [_exp("Skins.Zeta", "Zeta", "Skins", "sha256:5"),
                _exp("Skins.Alpha", "Alpha", "Skins", "sha256:5")]
    out = tc.reconcile(prior, package="P", package_file="P.utx", package_hash="new", exported=exported)
    assert out.textures["Skins.Alpha"].tags == ["wood"]            # sorted-first claims it
    assert out.textures["Skins.Alpha"].stale is True
    assert out.textures["Skins.Zeta"].tags == []                  # the other is fresh
    assert "Skins.Old" not in out.textures                        # source stem dropped


def test_reconcile_resurrection_clears_removed():
    prior = tc.Manifest(package="P", package_file="P.utx", package_hash="old", textures={
        "Skins.Wood": _classified_entry(removed=True)})
    exported = [_exp("Skins.Wood", "Wood", "Skins", "sha256:1")]   # same hash, back
    out = tc.reconcile(prior, package="P", package_file="P.utx", package_hash="new", exported=exported)
    assert out.textures["Skins.Wood"].removed is False
    assert out.textures["Skins.Wood"].stale is False              # unchanged pixels
    assert out.textures["Skins.Wood"].tags == ["wood"]            # classification intact


def test_bucket_is_a_total_partition():
    base = dict(name="X", group=None, ref="P.X", width=1, height=1, image_hash="h",
                colors=[], colors_source="auto", tags=[], description="")
    assert tc.bucket(tc.TextureEntry(**base, stale=False, removed=False)) == "unclassified"
    assert tc.bucket(tc.TextureEntry(**{**base, "tags": ["a"]}, stale=False, removed=False)) == "classified"
    assert tc.bucket(tc.TextureEntry(**{**base, "tags": ["a"]}, stale=True, removed=False)) == "stale"
    assert tc.bucket(tc.TextureEntry(**{**base, "tags": ["a"]}, stale=False, removed=True)) == "removed"


def test_validate_colors_rejects_unknown_listing_the_valid_set():
    tc.validate_colors(["brown", "grey"])                       # ok, no raise
    try:
        tc.validate_colors(["brown", "maroon"])
        assert False, "should have raised"
    except ValueError as e:
        assert "maroon" in str(e) and "brown" in str(e)        # names the offender + valid set


def test_classify_set_replaces_fields_sets_source_and_clears_stale():
    e = tc.TextureEntry(name="Wood", group="Skins", ref="DeusExDeco.Wood", width=1, height=1,
                        image_hash="h", colors=["brown"], colors_source="auto", tags=["old"],
                        description="old", stale=True, removed=False)
    m = tc.Manifest(package="DeusExDeco", package_file="x", package_hash="h",
                    textures={"Skins.Wood": e})
    out = tc.classify_set(m, "DeusExDeco.Wood", tags=["wood", "Wood", "WALL"],
                          description="planks", colors=["grey"])
    got = out.textures["Skins.Wood"]
    assert got.tags == ["wood", "wall"]                         # lower-cased + de-duped, order kept
    assert got.description == "planks"
    assert got.colors == ["grey"] and got.colors_source == "set"
    assert got.stale is False                                   # cleared


def test_classify_set_rejects_unknown_ref_and_removed():
    e = tc.TextureEntry(name="Wood", group="Skins", ref="DeusExDeco.Wood", width=1, height=1,
                        image_hash="h", colors=[], colors_source="auto", tags=[], description="",
                        stale=False, removed=True)
    m = tc.Manifest(package="DeusExDeco", package_file="x", package_hash="h",
                    textures={"Skins.Wood": e})
    for ref, msg in [("DeusExDeco.Nope", "DeusExDeco.Nope"), ("DeusExDeco.Wood", "removed")]:
        try:
            tc.classify_set(m, ref, tags=["a"], description=None, colors=None)
            assert False
        except ValueError as err:
            assert msg in str(err)


def _m(package, *entries):
    return tc.Manifest(package=package, package_file=package + ".utx", package_hash="h",
                       textures={e.ref.split(".", 1)[1]: e for e in entries})


def _entry(name, *, tags=(), colors=(), desc="", stale=False, removed=False, pkg="P"):
    return tc.TextureEntry(name=name, group=None, ref=f"{pkg}.{name}", width=1, height=1,
                           image_hash="h", colors=list(colors), colors_source="auto",
                           tags=list(tags), description=desc, stale=stale, removed=removed)


def test_status_counts_partition_per_package_and_total():
    m = _m("P", _entry("A", tags=["x"]), _entry("B"), _entry("C", stale=True, tags=["x"]),
           _entry("D", removed=True))
    counts = tc.status_counts([m])
    assert counts["per_package"]["P"] == {"total": 4, "classified": 1, "unclassified": 1,
                                          "stale": 1, "removed": 1}
    assert counts["total"]["total"] == 4


def test_search_ranks_and_filters_and_excludes_removed():
    m = _m("P",
           _entry("Wall", tags=["metal"], colors=["grey"]),            # exact name "wall"
           _entry("Brick", tags=["wall"], desc="a wall of brick"),     # tag/desc "wall"
           _entry("Gone", tags=["wall"], removed=True))                # removed -> excluded
    assert tc.search([m], "wall", tags=None, colors=None, package=None) == ["P.Wall", "P.Brick"]
    # filter-only (no query): every grey ref, ranked by ref
    assert tc.search([m], None, tags=None, colors=["grey"], package=None) == ["P.Wall"]
    # tag AND precondition
    assert tc.search([m], None, tags=["metal"], colors=None, package=None) == ["P.Wall"]
    assert tc.search([m], "nope", tags=None, colors=None, package=None) == []


def test_all_tags_counts_across_the_catalog():
    m = _m("P", _entry("A", tags=["wall", "metal"]), _entry("B", tags=["wall"]))
    assert tc.all_tags([m], package=None) == [("wall", 2), ("metal", 1)]


def _write_pcx(path, rgb):
    from PIL import Image
    img = Image.new("RGB", (8, 8), rgb)
    img.save(path)                                    # Pillow writes a real PCX from a .pcx suffix


def test_sync_package_builds_manifest_and_preserves_a_set_override(tmp_path):
    import os
    from PIL import Image
    catalog, images = tmp_path / "cat", tmp_path / "img"

    def fake_batchexport(container, package_file, host_dir):
        os.makedirs(host_dir, exist_ok=True)
        p = os.path.join(host_dir, "Skins.Wall.pcx")
        Image.new("RGB", (8, 8), (110, 70, 40)).save(p)      # brownish
        return [p]

    pkg_file = tmp_path / "P.utx"
    pkg_file.write_text("v1")
    m = tc.sync_package(package="P", package_file=str(pkg_file), container="ct",
                        catalog_dir=catalog, images_root=images, force=False,
                        batchexport=fake_batchexport,
                          lock_dir=str(tmp_path / 'locks'))
    assert m.textures["Skins.Wall"].ref == "P.Wall"
    assert m.textures["Skins.Wall"].colors == ["brown"]
    assert (images / "P" / "Skins.Wall.png").exists()        # viewable PNG written
    assert tc.load_manifest(tc.manifest_path(catalog, "P")) == m

    # a human override, then a content change + re-sync: override must survive
    m2 = tc.classify_set(m, "P.Wall", tags=None, description=None, colors=["grey"])
    tc.save_manifest(tc.manifest_path(catalog, "P"), m2)
    pkg_file.write_text("v2-different-hash")

    def fake_batchexport2(container, package_file, host_dir):
        os.makedirs(host_dir, exist_ok=True)
        p = os.path.join(host_dir, "Skins.Wall.pcx")
        Image.new("RGB", (8, 8), (40, 80, 190)).save(p)      # now blue pixels
        return [p]

    m3 = tc.sync_package(package="P", package_file=str(pkg_file), container="ct",
                         catalog_dir=catalog, images_root=images, force=False,
                         batchexport=fake_batchexport2,
                          lock_dir=str(tmp_path / 'locks'))
    assert m3.textures["Skins.Wall"].colors == ["grey"]      # SET override preserved
    assert m3.textures["Skins.Wall"].stale is True           # pixels changed


def test_sync_package_writes_no_manifest_for_a_textureless_or_unreachable_package(tmp_path):
    catalog = tmp_path / "cat"
    pkg_file = tmp_path / "Code.u"
    pkg_file.write_text("v1")
    out = tc.sync_package(package="Code", package_file=str(pkg_file), container="ct",
                          catalog_dir=catalog, images_root=tmp_path / "img", force=False,
                          batchexport=lambda *a, **k: [],      # no PCX produced
                          lock_dir=str(tmp_path / "locks"))
    assert out is None                                        # no prior, nothing built
    assert not tc.manifest_path(catalog, "Code").exists()     # no manifest written


def test_sync_package_hash_skip_does_not_call_batchexport(tmp_path):
    # T1: when the prior manifest's package_hash equals the current file hash and force=False,
    # batchexport must NOT be called and the prior manifest is returned unchanged.
    catalog, images = tmp_path / "cat", tmp_path / "img"
    pkg_file = tmp_path / "P.utx"
    pkg_file.write_bytes(b"x" * 1337)           # artificial, obviously non-real content

    # Build a prior manifest whose package_hash matches the file's current sha256.
    import hashlib
    real_hash = "sha256:" + hashlib.sha256(b"x" * 1337).hexdigest()
    prior = tc.Manifest(package="P", package_file="P.utx", package_hash=real_hash,
                        textures={"Skins.Wall": _classified_entry(ref="P.Wall")})
    tc.save_manifest(tc.manifest_path(catalog, "P"), prior)

    calls = []

    def spy_batchexport(container, package, host_dir):
        calls.append((container, package, host_dir))
        raise AssertionError("batchexport must not be called on hash-skip")

    out = tc.sync_package(package="P", package_file=str(pkg_file), container="ct",
                          catalog_dir=catalog, images_root=images, force=False,
                          batchexport=spy_batchexport,
                          lock_dir=str(tmp_path / 'locks'))
    assert calls == []                           # never called
    assert out == prior                          # returned the prior manifest unchanged


def test_sync_package_force_calls_batchexport_even_when_hash_unchanged(tmp_path):
    # T2: force=True bypasses the hash-skip fast path even when the file hash is identical.
    import hashlib
    from pathlib import Path
    catalog, images = tmp_path / "cat", tmp_path / "img"
    pkg_file = tmp_path / "P.utx"
    pkg_file.write_bytes(b"x" * 42069)          # artificial content

    real_hash = "sha256:" + hashlib.sha256(b"x" * 42069).hexdigest()
    prior = tc.Manifest(package="P", package_file="P.utx", package_hash=real_hash,
                        textures={"Skins.Wall": _classified_entry(ref="P.Wall")})
    tc.save_manifest(tc.manifest_path(catalog, "P"), prior)

    calls = []

    def counting_batchexport(container, package, host_dir):
        calls.append(package)
        import os
        os.makedirs(host_dir, exist_ok=True)
        p = os.path.join(host_dir, "Skins.Wall.pcx")
        Image.new("RGB", (4, 4), (110, 70, 40)).save(p)
        return [p]

    out = tc.sync_package(package="P", package_file=str(pkg_file), container="ct",
                          catalog_dir=catalog, images_root=images, force=True,
                          batchexport=counting_batchexport,
                          lock_dir=str(tmp_path / 'locks'))
    assert calls == ["P"]                        # called once despite unchanged hash
    assert out is not None
    assert out.package_hash == real_hash         # hash same — same file


def test_classify_set_raises_when_all_fields_are_none():
    # T3: calling classify_set with tags=None, description=None, colors=None must raise
    # ValueError whose message contains "at least one".
    e = _classified_entry()
    m = tc.Manifest(package="DeusExDeco", package_file="x.utx", package_hash="h",
                    textures={"Skins.Wood": e})
    try:
        tc.classify_set(m, "DeusExDeco.Wood", tags=None, description=None, colors=None)
        assert False, "should have raised ValueError"
    except ValueError as err:
        assert "at least one" in str(err)


def test_reconcile_stale_entry_unchanged_hash_stays_stale():
    # T4: a prior entry already stale (and not removed), re-exported with the SAME image_hash,
    # must remain stale=True — the stale flag is not cleared on an unchanged re-export.
    stale_entry = _classified_entry(h="sha256:7777", stale=True, removed=False)
    prior = tc.Manifest(package="P", package_file="P.utx", package_hash="old",
                        textures={"Skins.Wood": stale_entry})
    exported = [_exp("Skins.Wood", "Wood", "Skins", "sha256:7777")]   # same hash
    out = tc.reconcile(prior, package="P", package_file="P.utx",
                       package_hash="new", exported=exported)
    result = out.textures["Skins.Wood"]
    assert result.stale is True                 # stays stale — only classify set clears it
    assert result.tags == ["wood"]              # classification untouched
    assert result.removed is False


def test_classify_set_three_part_ref_updates_the_right_entry():
    # T5: a cross-group-collision entry whose ref is "Pkg.Group.Name" (3-part) must be
    # addressed by that 3-part ref and the correct entry updated, not misidentified.
    e_skins = tc.TextureEntry(
        name="Wood", group="Skins", ref="P.Skins.Wood", width=1, height=1,
        image_hash="sha256:aa", colors=["brown"], colors_source="auto",
        tags=[], description="", stale=False, removed=False)
    e_decor = tc.TextureEntry(
        name="Wood", group="Decor", ref="P.Decor.Wood", width=1, height=1,
        image_hash="sha256:bb", colors=["grey"], colors_source="auto",
        tags=[], description="", stale=False, removed=False)
    m = tc.Manifest(package="P", package_file="P.utx", package_hash="h",
                    textures={"Skins.Wood": e_skins, "Decor.Wood": e_decor})

    out = tc.classify_set(m, "P.Skins.Wood", tags=["panel"], description=None, colors=None)

    assert out.textures["Skins.Wood"].tags == ["panel"]   # the addressed entry updated
    assert out.textures["Decor.Wood"].tags == []          # the other entry untouched
