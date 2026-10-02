"""`class search` (ranked discovery) + `class prewarm` — asset-catalog class arm C4.

End-to-end CLI over the committed UED22 corpus (`uned/UED22/*.u`): a real `ClassIndex` for
enumeration/existence, a tmp catalog dir for the classification shards `search` ranks over. Covers
the ranking order + tie-break, the `--tag`/`--subclass-of`/`--drawtype`/`--include-abstract` filters,
the `--json` shape, and the error dispositions (term-less → exit 2 pointing at `list`; a bad
`--subclass-of`/`--drawtype` → exit 2 naming it; no project → exit 2; empty result → clean exit 0).
`prewarm` warms the persistent schema cache and prints each warmed package stem.
"""
from __future__ import annotations

import glob
import io
import json
import os
from pathlib import Path

import pytest

from uedcli import class_catalog as cc
from uedcli import schema_cache, uprops
from uedcli.classindex import ClassIndex
from uedcli.cli import dispatch, resources
from uedcli.cli.main import build_parser

UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"

# Real classes on the committed corpus.
CRATE = "DeusEx.CrateUnbreakableLarge"
CHAIR = "DeusEx.OfficeChair"
BARREL = "DeusEx.BarrelFire"


def _ued22_index() -> ClassIndex:
    files = [(os.path.splitext(os.path.basename(f))[0], f) for f in glob.glob(str(UED22 / "*.u"))]
    return ClassIndex.from_files(files)


@pytest.fixture
def cli(monkeypatch, capsys, tmp_path):
    """Run `uedcli class …` against UED22 with a tmp catalog dir. Returns
    `run(*argv, stdin="")` → `(rc, stdout, stderr)`. `catalog` is the tmp catalog path so a test can
    seed shards directly."""
    idx = _ued22_index()
    catalog = tmp_path / "catalog"
    monkeypatch.setattr(resources, "resolve_project", lambda args: object())
    monkeypatch.setattr(resources, "class_index", lambda project=None: idx)
    monkeypatch.setattr(resources, "catalog_dir", lambda project=None: str(catalog))
    monkeypatch.setattr(resources, "class_defaults",
                        lambda fqcn, project=None: uprops.resolve_class_defaults(
                            fqcn, resolver=idx.resolver()))

    def _run(*argv, stdin=""):
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        args = build_parser().parse_args(["class", *argv])
        rc = dispatch.dispatch(args)
        cap = capsys.readouterr()
        return rc, cap.out, cap.err

    _run.catalog = catalog
    _run.idx = idx
    return _run


def _seed(cli, ref, tags, desc=""):
    cc.save_shard(cc.shard_path(cli.catalog, ref), cc.ClassShard(ref=ref, tags=tags, description=desc))


# --------------------------------------------------------------------------- terms required

def test_termless_search_exits_2_pointing_at_list(cli):
    rc, out, err = cli("search")
    assert rc == 2 and out == ""
    assert "class list" in err and "Traceback" not in err


def test_blank_only_terms_exit_2(cli):
    rc, out, err = cli("search", "   ")
    assert rc == 2 and out == "" and "class list" in err


# --------------------------------------------------------------------------- ranking

def test_search_matches_a_class_by_name_substring(cli):
    rc, out, err = cli("search", "officechair")
    assert rc == 0, err
    assert CHAIR in out.split()


def test_search_ranks_exact_name_above_a_substring_only_match(cli):
    """A class whose leaf name IS the term (tier 5) sorts above one that only carries it as a tag
    substring (tier 2)."""
    _seed(cli, CRATE, ["office-supplies"])            # "office" only as a tag substring → tier 2
    rc, out, _ = cli("search", "officechair")         # CHAIR leaf == term → tier 5
    lines = out.split()
    assert lines[0] == CHAIR


def test_search_is_and_across_terms(cli):
    """Every term must match. A class matching only one of two terms is excluded."""
    _seed(cli, CRATE, ["crate", "storage"], "a big storage crate")
    rc, out, _ = cli("search", "crate", "storage")
    assert CRATE in out.split()
    rc, out, _ = cli("search", "crate", "nonexistenttermxyz")
    assert out == ""                                  # the second term matches nothing → dropped


def test_search_tie_break_is_ref_ascending(cli):
    """Two classes with the SAME score sort by ref ascending — deterministic output. Both real
    corpus classes carry the same made-up tag, so both match only via the exact tag (tier 4)."""
    _seed(cli, CRATE, ["widgetzz"])
    _seed(cli, CHAIR, ["widgetzz"])
    rc, out, err = cli("search", "widgetzz", "--include-abstract")
    lines = [ln for ln in out.split() if ln in (CRATE, CHAIR)]
    assert lines == sorted([CRATE, CHAIR])            # DeusEx.CrateUnbreakableLarge < DeusEx.OfficeChair


# --------------------------------------------------------------------------- filters

def test_tag_filter_requires_the_exact_tag(cli):
    _seed(cli, CRATE, ["crate", "faces:+z"])
    rc, out, _ = cli("search", "crate", "--tag", "faces:+z")
    assert CRATE in out.split()
    rc, out, _ = cli("search", "crate", "--tag", "faces:+x")   # not present → excluded
    assert CRATE not in out.split()


def test_subclass_of_restricts_the_corpus(cli):
    rc, out, err = cli("search", "chair", "--subclass-of", "DeusEx.OfficeChair")
    assert rc == 0, err
    assert CHAIR in out.split()
    # a base that OfficeChair does not descend from excludes it
    rc, out, _ = cli("search", "chair", "--subclass-of", "Engine.Light")
    assert CHAIR not in out.split()


def test_unknown_subclass_of_exits_2_naming_it(cli):
    rc, out, err = cli("search", "chair", "--subclass-of", "DeusEx.NoSuchBaseXYZ")
    assert rc == 2 and out == ""
    assert "DeusEx.NoSuchBaseXYZ" in err and "Traceback" not in err


def test_drawtype_filter_keeps_only_matching_defaults(cli):
    _seed(cli, CHAIR, ["chair"])
    rc, out, err = cli("search", "chair", "--drawtype", "DT_Mesh")
    assert rc == 0, err
    assert CHAIR in out.split()                       # OfficeChair is a DT_Mesh class
    rc, out, _ = cli("search", "chair", "--drawtype", "DT_Sprite")
    assert CHAIR not in out.split()


def test_drawtype_is_case_insensitive(cli):
    _seed(cli, CHAIR, ["chair"])
    rc, out, err = cli("search", "chair", "--drawtype", "dt_mesh")
    assert rc == 0 and CHAIR in out.split(), err


def test_bad_drawtype_exits_2_naming_it(cli):
    rc, out, err = cli("search", "chair", "--drawtype", "DT_Bogus")
    assert rc == 2 and out == ""
    assert "DT_Bogus" in err and "Traceback" not in err


# --------------------------------------------------------------------------- json / empty / no-project

def test_json_shape(cli):
    _seed(cli, CHAIR, ["chair", "seating"], "an office chair")
    rc, out, _ = cli("search", "officechair", "--json")
    row = next(json.loads(ln) for ln in out.splitlines() if json.loads(ln)["ref"] == CHAIR)
    assert set(row) == {"ref", "score", "classified", "tags", "description"}
    assert row["classified"] is True and row["tags"] == ["chair", "seating"]
    assert row["score"] == 5                          # exact leaf name


def test_json_reports_unclassified_entries_too(cli):
    rc, out, _ = cli("search", "officechair", "--json")
    row = next(json.loads(ln) for ln in out.splitlines() if json.loads(ln)["ref"] == CHAIR)
    assert row["classified"] is False and row["tags"] == [] and row["description"] == ""


def test_empty_result_is_a_clean_exit_0(cli):
    rc, out, err = cli("search", "nomatchtermxyz123")
    assert rc == 0 and out == ""
    assert "no matches" in err and "Traceback" not in err


def test_match_count_goes_to_stderr(cli):
    rc, out, err = cli("search", "officechair")
    assert rc == 0 and CHAIR in out.split()
    assert "match" in err                             # count summary on stderr, not stdout


def test_search_no_package_path_exits_2(cli, monkeypatch):
    monkeypatch.setattr(resources, "class_index",
                        lambda project=None: ClassIndex(_paths={}, _stems={}))
    rc, out, err = cli("search", "chair")
    assert rc == 2 and out == "" and "no package search path" in err and "Traceback" not in err


# --------------------------------------------------------------------------- prewarm

def test_prewarm_warms_and_prints_each_package_stem(cli, monkeypatch):
    warmed: list[tuple] = []
    monkeypatch.setattr(schema_cache, "load_package_schema",
                        lambda path, *, name=None, need_props=False, force=False:
                        warmed.append((name, need_props, force)))
    rc, out, err = cli("prewarm")
    assert rc == 0, err
    stems_out = out.split()
    assert "DeusEx" in stems_out and "Engine" in stems_out
    assert len(stems_out) == len(cli.idx.packages())
    assert all(np is True for _n, np, _f in warmed)   # props warmed too
    assert "warmed" in err


def test_prewarm_one_package(cli, monkeypatch):
    warmed: list = []
    monkeypatch.setattr(schema_cache, "load_package_schema",
                        lambda path, *, name=None, need_props=False, force=False:
                        warmed.append(name))
    rc, out, err = cli("prewarm", "--package", "deusex")   # case-insensitive stem
    assert rc == 0, err
    assert out.split() == ["DeusEx"] and warmed == ["DeusEx"]


def test_prewarm_unknown_package_exits_2_naming_it(cli):
    rc, out, err = cli("prewarm", "--package", "NoSuchPkgXYZ")
    assert rc == 2 and out == ""
    assert "NoSuchPkgXYZ" in err and "Traceback" not in err


def test_prewarm_force_passes_through(cli, monkeypatch):
    seen: list = []
    monkeypatch.setattr(schema_cache, "load_package_schema",
                        lambda path, *, name=None, need_props=False, force=False:
                        seen.append(force))
    rc, out, err = cli("prewarm", "--package", "DeusEx", "--force")
    assert rc == 0 and seen == [True], err
    assert "re-warmed" in err


def test_prewarm_no_package_path_exits_2(cli, monkeypatch):
    monkeypatch.setattr(resources, "class_index",
                        lambda project=None: ClassIndex(_paths={}, _stems={}))
    rc, out, err = cli("prewarm")
    assert rc == 2 and out == "" and "no package search path" in err
