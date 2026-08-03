"""`texture` noun CLI round-trip — asset-catalog TEXTURE arm (T3–T6).

End-to-end over synthetic `.utx` on a tmp search path, joined with a REAL `ClassIndex` over the
committed `uned/UED22` corpus (for the class hierarchy and the `bMasked` class default). Covers
list/show/preview/search, classify set·unset·status·tags, the two-layer identity (identical pixels
behind different masks share ONE shard; masked/group are Layer-2 facts), refuse-then-force, the
procedural name-key, colour pre-fill/override, and the error dispositions (each exits 2, no
traceback).
"""
from __future__ import annotations

import glob
import io
import json
import os
from pathlib import Path

import pytest

from PIL import Image

from uedcli import texture_catalog as tc
from uedcli import utexture
from uedcli.classindex import ClassIndex
from uedcli.cli import dispatch, resources
from uedcli.cli.main import build_parser
from uedcli.tests import pkgfixture

UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"
# Only the CODE packages the class hierarchy + bMasked default need (`Engine.Texture` →
# `Engine.Bitmap` → `Core.Object`; `fire.FireTexture` descends from `Engine.Texture`). They carry
# almost no texture EXPORTS, so enumeration/search/status stay over the synthetic corpus and fast —
# the whole DeusEx*.u set would put ~1900 real textures through every decode-all verb.
_CODE_U = [str(UED22 / n) for n in ("core.u", "Engine.u", "fire.u")]

# A brown P8 chain (palette entry 5 = brown), plus a distinct grey chain.
_BROWN_PAL = [(110, 70, 40, 255)] * 256
_GREY_PAL = [(128, 128, 128, 255)] * 256
_CHAIN = pkgfixture.linear_chain(8, 8)                 # every pixel palette-index (x*7)&255


def _packages(dirpath: str) -> list[str]:
    """Write the synthetic corpus. `Grille` and `Twin` share pixels but differ in bMasked → ONE
    identity, two masked facts. `Wall` is grey. `Flame` is a procedural (fire.FireTexture)."""
    specs = {
        "PkgA.utx": pkgfixture.texture_package(name="Grille", mips=_CHAIN, palette=_BROWN_PAL,
                                               bmasked=True, group="Metal"),
        "PkgB.utx": pkgfixture.texture_package(name="Twin", mips=_CHAIN, palette=_BROWN_PAL),
        "Deco.utx": pkgfixture.texture_package(name="Wall", mips=_CHAIN, palette=_GREY_PAL),
        "Fx.utx": pkgfixture.texture_package(name="Flame", mips=[(4, 4, b"")],
                                             class_package="fire", class_name="FireTexture"),
    }
    Path(dirpath).mkdir(parents=True, exist_ok=True)
    for fname, data in specs.items():
        (Path(dirpath) / fname).write_bytes(data)
    return [str(Path(dirpath) / f) for f in specs]


@pytest.fixture(scope="module")
def _index() -> ClassIndex:
    return ClassIndex.from_files([(os.path.splitext(os.path.basename(f))[0], f) for f in _CODE_U])


@pytest.fixture
def cli(monkeypatch, capsys, tmp_path, _index):
    """`run(*argv, stdin="") -> (rc, out, err)` against the synthetic corpus + a tmp catalog dir.
    `catalog` exposes the shard root so a test can inspect / seed shards directly."""
    corpus = _packages(str(tmp_path / "corpus"))
    search = list(_CODE_U) + corpus
    catalog = tmp_path / "catalog"

    monkeypatch.setattr(resources, "resolve_project", lambda args: object())
    monkeypatch.setattr(resources, "class_index", lambda project=None: _index)
    monkeypatch.setattr(resources, "catalog_dir", lambda project=None: str(catalog))
    monkeypatch.setattr(resources, "texture_resolver",
                        lambda project, class_index=None: utexture.TextureResolver(
                            search, class_index=class_index))

    def _run(*argv, stdin=""):
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        args = build_parser().parse_args(["texture", *argv])
        rc = dispatch.dispatch(args)
        cap = capsys.readouterr()
        return rc, cap.out, cap.err

    _run.catalog = catalog
    return _run


# ── list ──────────────────────────────────────────────────────────────────────────────────────────

def test_list_enumerates_every_texture_sorted(cli):
    rc, out, _ = cli("list")
    refs = out.split()
    assert refs == sorted(refs, key=str.casefold)     # case-insensitive, like the class arm
    assert refs == ["Deco.Wall", "Fx.Flame", "PkgA.Grille", "PkgB.Twin"]


def test_list_group_filter_needs_no_decode(cli):
    rc, out, _ = cli("list", "--group", "Metal")
    assert out.split() == ["PkgA.Grille"]


def test_list_masked_filter(cli):
    rc, out, _ = cli("list", "--masked")
    refs = out.split()
    assert "PkgA.Grille" in refs and "PkgB.Twin" not in refs        # only bMasked=true


def test_list_json_row_shape(cli):
    rc, out, _ = cli("list", "--package", "PkgA", "--json")
    row = json.loads(out.strip())
    assert set(row) == {"ref", "identity", "classified", "group", "masked", "preview"}
    assert row["ref"] == "PkgA.Grille" and row["group"] == "Metal"
    assert row["masked"] is True and row["classified"] is False and row["preview"] is None


# ── the two-layer identity ──────────────────────────────────────────────────────────────────────────

def test_identical_pixels_different_masks_share_one_identity_and_shard(cli):
    """Grille (bMasked) and Twin (not) have identical pixels → ONE identity; classifying Grille makes
    Twin read classified too, and a `set` on Twin REFUSES the shared shard. masked stays a Layer-2
    fact (distinct per ref)."""
    _, ga, _ = cli("show", "PkgA.Grille", "--json")
    _, tb, _ = cli("show", "PkgB.Twin", "--json")
    a, b = json.loads(ga), json.loads(tb)
    assert a["identity"] == b["identity"]              # same content identity
    assert a["masked"] is True and b["masked"] is False  # Layer-2 differs
    cli("classify", "set", "PkgA.Grille", "--tags", "grille")
    files = list((cli.catalog / "classified" / "texture").glob("*/*.json"))
    assert len(files) == 1                             # ONE shard for both
    rc, out, err = cli("classify", "set", "PkgB.Twin", "--tags", "other")
    assert rc == 2 and out == "" and "already classified" in err and "Traceback" not in err
    assert tc.load_shard(files[0]).ref == "PkgA.Grille"   # write-once: the first classifier's ref


# ── show ──────────────────────────────────────────────────────────────────────────────────────────

def test_show_reports_facts_identity_and_derived_colors(cli):
    rc, out, _ = cli("show", "PkgB.Twin")
    assert "size:     8x8" in out and "masked:   false" in out
    assert "colors:   brown" in out                   # derived live, no classification yet
    assert "(unclassified)" in out


def test_show_procedural_has_no_bitmap_and_a_name_identity(cli):
    rc, out, _ = cli("show", "Fx.Flame", "--json")
    obj = json.loads(out)
    assert obj["identity"] == "fx.flame" and obj["width"] is None
    assert obj["colors"] == [] and obj["classification"] is None


def test_show_bad_ref_exits_2_naming_it(cli):
    rc, out, err = cli("show", "PkgA.NoSuchTexture")
    assert rc == 2 and out == "" and "PkgA.NoSuchTexture" in err and "Traceback" not in err


def test_show_reads_a_ref_list_from_stdin_and_empty_is_noop(cli):
    rc, out, _ = cli("show", "-", stdin="PkgB.Twin\nDeco.Wall\n")
    assert "PkgB.Twin" in out and "Deco.Wall" in out
    rc, out, _ = cli("show", "-", stdin="")
    assert rc == 0 and out == ""


# ── preview ────────────────────────────────────────────────────────────────────────────────────────

def test_preview_writes_a_png_of_the_right_size(cli, tmp_path):
    rc, out, _ = cli("preview", "PkgB.Twin", "--out", str(tmp_path / "twin.png"))
    ref, path = out.strip().split("\t")
    assert ref == "PkgB.Twin"
    with Image.open(path) as img:
        assert img.size == (8, 8) and img.mode == "RGB"


def test_preview_skeleton_streams_a_ready_to_fill_row(cli, tmp_path):
    rc, out, _ = cli("preview", "PkgB.Twin", "--skeleton", "--out", str(tmp_path / "t.png"))
    row = json.loads(out.strip())
    assert row["ref"] == "PkgB.Twin" and row["tags"] == [] and row["description"] == ""
    assert row["colors"] == ["brown"] and Path(row["preview"]).exists()


def test_preview_procedural_exits_2_naming_the_case(cli, tmp_path):
    rc, out, err = cli("preview", "Fx.Flame", "--out", str(tmp_path / "f.png"))
    assert rc == 2 and out == "" and "no-mip-data" in err and "Fx.Flame" in err


# ── classify set / force / batch ─────────────────────────────────────────────────────────────────────

def test_set_records_the_exact_payload_with_prefilled_colors(cli):
    rc, out, err = cli("classify", "set", "Deco.Wall", "--tags", "wall,stone",
                       "--description", "a grey wall")
    assert rc == 0, err
    _, sj, _ = cli("show", "Deco.Wall", "--json")
    ident = json.loads(sj)["identity"]
    shard = tc.load_shard(tc.shard_path(cli.catalog, ident))
    assert shard.to_json() == {"kind": "texture", "identity": ident, "ref": "Deco.Wall",
                               "tags": ["wall", "stone"], "description": "a grey wall",
                               "colors": ["grey"]}


def test_set_over_existing_refuses_then_force_replaces_without_union(cli):
    cli("classify", "set", "Deco.Wall", "--tags", "wall,stone", "--description", "old")
    rc, out, err = cli("classify", "set", "Deco.Wall", "--tags", "brick")
    assert rc == 2 and "already classified" in err
    rc, _, err = cli("classify", "set", "Deco.Wall", "--tags", "brick", "--force")
    assert rc == 0, err
    _, sj, _ = cli("show", "Deco.Wall", "--json")
    shard = tc.load_shard(tc.shard_path(cli.catalog, json.loads(sj)["identity"]))
    assert shard.tags == ["brick"] and shard.description == ""   # replaced, not unioned; desc wiped


def test_set_colors_override_wins_over_the_prefill(cli):
    cli("classify", "set", "Deco.Wall", "--tags", "wall", "--colors", "blue,green")
    _, sj, _ = cli("show", "Deco.Wall", "--json")
    shard = tc.load_shard(tc.shard_path(cli.catalog, json.loads(sj)["identity"]))
    assert shard.colors == ["blue", "green"]


def test_set_colors_are_lowercased_like_search(cli):
    """A mixed-case palette name is accepted and stored lowercase on `set`, matching how `search
    --color` lowercases — the two must not diverge."""
    cli("classify", "set", "Deco.Wall", "--tags", "wall", "--colors", "Blue,GREEN")
    _, sj, _ = cli("show", "Deco.Wall", "--json")
    shard = tc.load_shard(tc.shard_path(cli.catalog, json.loads(sj)["identity"]))
    assert shard.colors == ["blue", "green"]


def test_set_unknown_color_exits_2(cli):
    rc, out, err = cli("classify", "set", "Deco.Wall", "--tags", "x", "--colors", "chartreuse")
    assert rc == 2 and "chartreuse" in err and "Traceback" not in err


def test_set_procedural_is_classifiable_by_name(cli):
    rc, out, err = cli("classify", "set", "Fx.Flame", "--tags", "fire")
    assert rc == 0, err
    assert tc.load_shard(tc.shard_path(cli.catalog, "fx.flame")).tags == ["fire"]


def test_batch_writes_n_shards_all_or_nothing(cli):
    rows = "\n".join(json.dumps(r) for r in [
        {"ref": "Deco.Wall", "tags": ["wall"]},
        {"ref": "PkgA.Grille", "tags": ["grille"], "colors": ["brown"]},
    ])
    rc, out, err = cli("classify", "set", "-", stdin=rows)
    assert rc == 0, err
    assert set(out.split()) == {"Deco.Wall", "PkgA.Grille"}
    # a bad row rolls the whole batch back
    rows = "\n".join(json.dumps(r) for r in [
        {"ref": "Fx.Flame", "tags": ["fire"]},
        {"ref": "PkgA.NoSuch", "tags": ["x"]},
    ])
    rc, out, err = cli("classify", "set", "-", stdin=rows)
    assert rc == 2 and out == "" and "PkgA.NoSuch" in err
    assert not tc.shard_path(cli.catalog, "fx.flame").exists()


def test_batch_empty_stdin_is_a_clean_noop(cli):
    rc, out, _ = cli("classify", "set", "-", stdin="")
    assert rc == 0 and out == ""


# ── unset ──────────────────────────────────────────────────────────────────────────────────────────

def test_unset_clears_colors_override(cli):
    cli("classify", "set", "Deco.Wall", "--tags", "wall", "--colors", "blue")
    rc, _, err = cli("classify", "unset", "Deco.Wall", "--colors")
    assert rc == 0, err
    _, sj, _ = cli("show", "Deco.Wall", "--json")
    shard = tc.load_shard(tc.shard_path(cli.catalog, json.loads(sj)["identity"]))
    assert shard.colors == []                          # override cleared → search live-derives


def test_unset_all_deletes_the_shard(cli):
    cli("classify", "set", "Fx.Flame", "--tags", "fire")
    rc, _, err = cli("classify", "unset", "Fx.Flame", "--all")
    assert rc == 0, err
    assert not tc.shard_path(cli.catalog, "fx.flame").exists()


def test_unset_unknown_shard_exits_2(cli):
    rc, out, err = cli("classify", "unset", "Deco.Wall", "--all")
    assert rc == 2 and out == "" and "Deco.Wall" in err and "Traceback" not in err


# ── search ─────────────────────────────────────────────────────────────────────────────────────────

def test_search_term_less_exits_2_pointing_at_list(cli):
    rc, out, err = cli("search")
    assert rc == 2 and "list" in err and "Traceback" not in err


def test_search_ranks_and_matches_on_name(cli):
    rc, out, _ = cli("search", "wall")
    assert out.split() == ["Deco.Wall"]


def test_search_color_live_derives_on_an_unclassified_corpus(cli):
    """`--color brown` matches brown textures with an EMPTY classification store (live-derive)."""
    rc, out, _ = cli("search", "grille", "--color", "brown")
    assert "PkgA.Grille" in out.split()
    rc, out, _ = cli("search", "grille", "--color", "green")
    assert out.strip() == ""                           # brown texture is not green


def test_search_tag_filter_uses_the_store(cli):
    cli("classify", "set", "Deco.Wall", "--tags", "wall,stone")
    rc, out, _ = cli("search", "wall", "--tag", "stone")
    assert out.split() == ["Deco.Wall"]
    rc, out, _ = cli("search", "wall", "--tag", "metal")
    assert out.strip() == ""


# ── status / tags ────────────────────────────────────────────────────────────────────────────────────

def test_status_counts_intersection(cli):
    cli("classify", "set", "Deco.Wall", "--tags", "wall")
    rc, out, _ = cli("classify", "status")
    assert out.startswith("classified 1 / ")
    total = int(out.split("/")[1].split()[0])
    assert total >= 3                                  # Grille/Twin share one identity → counted once
    rc, out, _ = cli("classify", "status", "--json")
    assert json.loads(out)["classified"] == 1


def test_tags_vocabulary_with_counts(cli):
    cli("classify", "set", "Deco.Wall", "--tags", "wall,stone")
    cli("classify", "set", "Fx.Flame", "--tags", "stone")
    rc, out, _ = cli("classify", "tags")
    assert "stone\t2" in out and "wall\t1" in out
    rc, out, _ = cli("classify", "tags", "--json")
    assert json.loads(out) == {"stone": 2, "wall": 1}


# ── prewarm + no-path ───────────────────────────────────────────────────────────────────────────────

def test_prewarm_decodes_and_reports(cli):
    rc, out, err = cli("prewarm")
    assert rc == 0 and "warmed" in err


def test_no_package_path_exits_2(cli, monkeypatch):
    monkeypatch.setattr(resources, "class_index",
                        lambda project=None: ClassIndex(_paths={}, _stems={}))
    rc, out, err = cli("list")
    assert rc == 2 and out == "" and "no package search path" in err and "Traceback" not in err
