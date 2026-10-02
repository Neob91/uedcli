"""`class classify` + `class list --classified/--unclassified/--json` — asset-catalog class arm C3.

End-to-end CLI round-trip over the committed UED22 corpus (`uned/UED22/*.u`): a real `ClassIndex`
for existence/enumeration, a tmp catalog dir for the git-tracked shards. Covers the store round-trip,
the tag union-merge, the description conflict rule, the `mount:`/`faces:` SHAPE check, the JSONL
batch (validate-all-then-write), unset, status/tags, the list filters, and the error dispositions
(each exits 2 cleanly, never a traceback).
"""
from __future__ import annotations

import glob
import io
import json
import os
from pathlib import Path

import pytest

from uedcli import class_catalog as cc
from uedcli import uprops
from uedcli.classindex import ClassIndex
from uedcli.cli import dispatch, resources
from uedcli.cli.main import build_parser

UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"

# Real classes on the committed corpus (see test_class_facts.py).
CRATE = "DeusEx.CrateUnbreakableLarge"
CHAIR = "DeusEx.OfficeChair"


def _ued22_index() -> ClassIndex:
    files = [(os.path.splitext(os.path.basename(f))[0], f) for f in glob.glob(str(UED22 / "*.u"))]
    return ClassIndex.from_files(files)


@pytest.fixture
def cli(monkeypatch, capsys, tmp_path):
    """Run `uedcli class …` against UED22 with a tmp catalog dir. Returns
    `run(*argv, stdin="")` → `(rc, stdout, stderr)`. `catalog` is the tmp catalog path so a test can
    inspect / seed shards directly."""
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
    return _run


# --------------------------------------------------------------------------- set / round-trip

def test_set_records_a_shard_with_the_exact_payload(cli):
    rc, out, err = cli("classify", "set", CRATE, "--tags", "crate,storage",
                       "--description", "an unbreakable crate")
    assert rc == 0, err
    assert out.strip() == CRATE
    shard = cc.load_shard(cc.shard_path(cli.catalog, CRATE))
    assert shard.to_json() == {"kind": "class", "ref": CRATE,
                               "tags": ["crate", "storage"], "description": "an unbreakable crate"}


def test_reset_unions_tags(cli):
    cli("classify", "set", CRATE, "--tags", "crate")
    cli("classify", "set", CRATE, "--tags", "Storage,crate")
    assert cc.load_shard(cc.shard_path(cli.catalog, CRATE)).tags == ["crate", "storage"]


def test_casefolded_path_shares_one_shard_keeping_authored_ref(cli):
    cli("classify", "set", CRATE, "--tags", "a")
    cli("classify", "set", CRATE.lower(), "--tags", "b")       # different casing → same shard
    files = list((cli.catalog / "classified" / "class").glob("*/*.json"))
    assert len(files) == 1
    shard = cc.load_shard(files[0])
    assert shard.ref == CRATE and set(shard.tags) == {"a", "b"}   # ref write-once


def test_conflicting_description_exits_2_printing_stored_text(cli):
    cli("classify", "set", CRATE, "--description", "the ORIGINAL text")
    rc, out, err = cli("classify", "set", CRATE, "--description", "something else")
    assert rc == 2 and out == ""
    assert "the ORIGINAL text" in err and "Traceback" not in err


def test_replace_overwrites_description(cli):
    cli("classify", "set", CRATE, "--description", "old")
    rc, _, err = cli("classify", "set", CRATE, "--description", "new", "--replace")
    assert rc == 0, err
    assert cc.load_shard(cc.shard_path(cli.catalog, CRATE)).description == "new"


def test_identical_description_is_a_noop(cli):
    cli("classify", "set", CRATE, "--description", "same")
    rc, _, err = cli("classify", "set", CRATE, "--description", "same")
    assert rc == 0, err


def test_set_needs_at_least_one_field(cli):
    rc, _, err = cli("classify", "set", CRATE)
    assert rc == 2 and "--tags" in err and "Traceback" not in err


def test_set_unknown_class_exits_2_naming_it(cli):
    rc, out, err = cli("classify", "set", "DeusEx.NoSuchClassHere", "--tags", "x")
    assert rc == 2 and out == ""
    assert "DeusEx.NoSuchClassHere" in err and "Traceback" not in err


def test_set_bad_ref_shape_exits_2(cli):
    rc, _, err = cli("classify", "set", "BareName", "--tags", "x")
    assert rc == 2 and "BareName" in err and "Traceback" not in err


# --------------------------------------------------------------------------- mount:/faces: namespace

def test_faces_axis_tag_is_accepted_and_filters_via_tags(cli):
    rc, _, err = cli("classify", "set", CRATE, "--tags", "faces:+X")   # lowercased by the normalizer
    assert rc == 0, err
    assert cc.load_shard(cc.shard_path(cli.catalog, CRATE)).tags == ["faces:+x"]
    rc, out, _ = cli("classify", "tags")
    assert "faces:+x\t1" in out


@pytest.mark.parametrize("bad", ["faces:foward", "faces:up", "mount:"])
def test_malformed_namespaced_tag_exits_2_naming_it(cli, bad):
    rc, out, err = cli("classify", "set", CRATE, "--tags", bad)
    assert rc == 2 and out == ""
    assert bad in err and "Traceback" not in err
    assert not cc.shard_path(cli.catalog, CRATE).exists()     # nothing written on the reject


def test_mount_value_is_free_text(cli):
    rc, _, err = cli("classify", "set", CRATE, "--tags", "mount:ceiling beam")
    assert rc == 0, err
    assert "mount:ceiling beam" in cc.load_shard(cc.shard_path(cli.catalog, CRATE)).tags


# --------------------------------------------------------------------------- JSONL batch (set -)

def test_batch_writes_n_shards(cli):
    rows = "\n".join(json.dumps(r) for r in [
        {"ref": CRATE, "tags": ["crate"], "description": "a crate"},
        {"ref": CHAIR, "tags": ["chair"]},
    ])
    rc, out, err = cli("classify", "set", "-", stdin=rows)
    assert rc == 0, err
    assert cc.load_shard(cc.shard_path(cli.catalog, CRATE)).tags == ["crate"]
    assert cc.load_shard(cc.shard_path(cli.catalog, CHAIR)).description == ""
    assert set(out.split()) == {CRATE, CHAIR}


def test_batch_empty_stdin_is_a_clean_noop(cli):
    rc, out, err = cli("classify", "set", "-", stdin="")
    assert rc == 0 and out == ""


def test_batch_is_all_or_nothing_on_a_bad_row(cli):
    """A single bad ref aborts the whole batch — the good row before it is NOT written (validate-all-
    then-write; no partial result)."""
    rows = "\n".join(json.dumps(r) for r in [
        {"ref": CRATE, "tags": ["crate"]},
        {"ref": "DeusEx.NoSuchClassHere", "tags": ["x"]},
    ])
    rc, out, err = cli("classify", "set", "-", stdin=rows)
    assert rc == 2 and out == ""
    assert "DeusEx.NoSuchClassHere" in err and "Traceback" not in err
    assert not cc.shard_path(cli.catalog, CRATE).exists()      # the good row rolled back


def test_batch_replace_governs_rows(cli):
    cli("classify", "set", CRATE, "--description", "old")
    rc, _, err = cli("classify", "set", "-", "--replace",
                     stdin=json.dumps({"ref": CRATE, "description": "new"}))
    assert rc == 0, err
    assert cc.load_shard(cc.shard_path(cli.catalog, CRATE)).description == "new"


# --------------------------------------------------------------------------- unset

def _seed(cli, ref, tags, desc=""):
    cc.save_shard(cc.shard_path(cli.catalog, ref), cc.ClassShard(ref=ref, tags=tags, description=desc))


def test_unset_removes_named_tags(cli):
    _seed(cli, CRATE, ["crate", "wood", "storage"])
    rc, out, err = cli("classify", "unset", CRATE, "--tags", "wood,storage")
    assert rc == 0 and out.strip() == CRATE
    assert cc.load_shard(cc.shard_path(cli.catalog, CRATE)).tags == ["crate"]


def test_unset_bare_tags_clears_the_field(cli):
    _seed(cli, CRATE, ["crate", "wood"], "keep me")
    rc, _, err = cli("classify", "unset", CRATE, "--tags")
    assert rc == 0, err
    s = cc.load_shard(cc.shard_path(cli.catalog, CRATE))
    assert s.tags == [] and s.description == "keep me"


def test_unset_description_clears_only_description(cli):
    _seed(cli, CRATE, ["crate"], "drop me")
    rc, _, err = cli("classify", "unset", CRATE, "--description")
    assert rc == 0, err
    s = cc.load_shard(cc.shard_path(cli.catalog, CRATE))
    assert s.tags == ["crate"] and s.description == ""


def test_unset_all_deletes_the_shard(cli):
    _seed(cli, CRATE, ["crate"], "d")
    rc, _, err = cli("classify", "unset", CRATE, "--all")
    assert rc == 0, err
    assert not cc.shard_path(cli.catalog, CRATE).exists()


def test_unset_requires_exactly_one_mode(cli):
    """The `--tags|--description|--all` group is required — argparse enforces it at parse time with
    a clean exit-2 usage message (SystemExit, no traceback)."""
    _seed(cli, CRATE, ["crate"])
    with pytest.raises(SystemExit) as e:
        cli("classify", "unset", CRATE)                        # no mode flag
    assert e.value.code == 2


def test_unset_unknown_shard_exits_2(cli):
    rc, out, err = cli("classify", "unset", CRATE, "--all")    # nothing stored
    assert rc == 2 and out == "" and CRATE in err and "Traceback" not in err


def test_unset_reads_a_name_list_from_stdin(cli):
    _seed(cli, CRATE, ["a"])
    _seed(cli, CHAIR, ["b"])
    rc, out, err = cli("classify", "unset", "-", "--all", stdin=f"{CRATE}\n{CHAIR}\n")
    assert rc == 0, err
    assert not cc.shard_path(cli.catalog, CRATE).exists()
    assert not cc.shard_path(cli.catalog, CHAIR).exists()


def test_unset_empty_stdin_is_a_clean_noop(cli):
    rc, out, err = cli("classify", "unset", "-", "--all", stdin="")
    assert rc == 0 and out == ""


# --------------------------------------------------------------------------- status / tags

def test_status_reports_classified_over_total(cli):
    cli("classify", "set", CRATE, "--tags", "crate")
    rc, out, err = cli("classify", "status")
    assert rc == 0, err
    # "classified 1 / <total> classes"
    assert out.startswith("classified 1 / ")
    total = int(out.split("/")[1].split()[0])
    assert total > 1


def test_status_json(cli):
    cli("classify", "set", CRATE, "--tags", "crate")
    rc, out, _ = cli("classify", "status", "--json")
    obj = json.loads(out)
    assert obj["classified"] == 1 and obj["total"] > 1


def test_tags_vocabulary_with_counts(cli):
    cli("classify", "set", CRATE, "--tags", "crate,storage")
    cli("classify", "set", CHAIR, "--tags", "storage")
    rc, out, _ = cli("classify", "tags")
    assert "storage\t2" in out and "crate\t1" in out
    rc, out, _ = cli("classify", "tags", "--json")
    assert json.loads(out) == {"storage": 2, "crate": 1}


# --------------------------------------------------------------------------- list filters

def test_classified_unclassified_require_flat(cli):
    for flag in ("--classified", "--unclassified"):
        rc, out, err = cli("list", flag)                       # no --flat
        assert rc == 2 and "--flat" in err and "Traceback" not in err


def test_list_classified_and_unclassified_partition(cli):
    cli("classify", "set", CRATE, "--tags", "crate")
    rc, out, _ = cli("list", "--flat", "--package", "DeusEx", "--classified")
    lines = out.split()
    assert CRATE in lines
    rc, out2, _ = cli("list", "--flat", "--package", "DeusEx", "--unclassified")
    assert CRATE not in out2.split()
    assert CHAIR in out2.split()                               # unclassified stays in the worklist


def test_list_json_carries_classified_and_null_preview(cli):
    cli("classify", "set", CRATE, "--tags", "crate")
    rc, out, _ = cli("list", "--flat", "--package", "DeusEx", "--json")
    rows = {json.loads(line)["ref"]: json.loads(line) for line in out.splitlines()}
    assert rows[CRATE]["classified"] is True
    assert rows[CRATE]["preview"] is None                      # cached-only; never rendered here
    assert rows[CHAIR]["classified"] is False
    assert set(rows[CRATE]) == {"ref", "classified", "preview"}


# --------------------------------------------------------------------------- show round-trip

def test_show_prints_stored_classification_text_and_json(cli):
    cli("classify", "set", CRATE, "--tags", "crate,mount:floor",
        "--description", "an unbreakable crate")
    rc, out, _ = cli("show", CRATE)
    assert "Classification:" in out
    assert "crate, mount:floor" in out and "an unbreakable crate" in out
    rc, out, _ = cli("show", CRATE, "--json")
    obj = json.loads(out)
    assert obj["classification"] == {"tags": ["crate", "mount:floor"],
                                     "description": "an unbreakable crate"}


# --------------------------------------------------------------------------- no project

def test_classify_no_package_path_exits_2(cli, monkeypatch):
    monkeypatch.setattr(resources, "class_index",
                        lambda project=None: ClassIndex(_paths={}, _stems={}))
    rc, out, err = cli("classify", "set", CRATE, "--tags", "x")
    assert rc == 2 and out == "" and "no package search path" in err and "Traceback" not in err

