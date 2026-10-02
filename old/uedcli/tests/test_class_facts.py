"""`class show` mesh facts — the asset-catalog class arm C1 (signed mesh-local extents, collision,
prepivot, drawtype, parent), with `--json`.

The end-to-end tests run OFFLINE against the committed UED22 packages (`uned/UED22/*.u`): a real
`ClassIndex` over them, real `resolve_class_defaults`, and the promoted `umesh` decoder. Deus Ex's
deco meshes live in `DeusExDeco.u` while the classes that reference them live in `DeusEx.u`, so this
exercises the whole class -> default Mesh -> decoded box -> signed extents path with no game install.
The pure `meshfacts` helpers (signed extents, ref parsing) are unit-tested too.
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import pytest

from uedcli import meshfacts, uprops
from uedcli.classindex import ClassIndex
from uedcli.cli import dispatch, resources
from uedcli.cli.main import build_parser

UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"


def _ued22_index() -> ClassIndex:
    files = [(os.path.splitext(os.path.basename(f))[0], f) for f in glob.glob(str(UED22 / "*.u"))]
    return ClassIndex.from_files(files)


@pytest.fixture
def show(monkeypatch, capsys, tmp_path):
    """Run `class show …` against the committed UED22 corpus and return `(rc, stdout, stderr)`.
    Tests that need a different substrate re-patch the seams via their own `monkeypatch` (same
    instance, applied after this fixture, so it wins). The catalog dir points at an empty tmp dir,
    so classes read as unclassified unless a test writes a shard first."""
    idx = _ued22_index()
    monkeypatch.setattr(resources, "resolve_project", lambda args: object())
    monkeypatch.setattr(resources, "class_index", lambda project=None: idx)
    monkeypatch.setattr(resources, "catalog_dir", lambda project=None: str(tmp_path / "catalog"))
    monkeypatch.setattr(resources, "class_defaults",
                        lambda fqcn, project=None: uprops.resolve_class_defaults(
                            fqcn, resolver=idx.resolver()))

    def _run(*argv):
        args = build_parser().parse_args(["class", "show", *argv])
        rc = dispatch.dispatch(args)
        cap = capsys.readouterr()
        return rc, cap.out, cap.err

    return _run


# ------------------------------------------------------------------- extents (end to end, offline)

def test_extents_are_signed_scaled_and_exact(show):
    """A known mesh class reports the exact signed x/y/z lo..hi in the one mesh-local frame (Scale
    applied per-axis: the mesh box (±320,±320,±224) times (0.125,0.125,0.25))."""
    rc, out, err = show("DeusEx.CrateUnbreakableLarge", "--json")
    assert rc == 0, err
    obj = json.loads(out)
    assert obj["extents"] == {"x": [-40, 40], "y": [-40, 40], "z": [-56, 56]}
    assert obj["mesh"] == "DeusExDeco.CrateUnbreakableLarge"
    assert obj["drawtype"] == "DT_Mesh"
    # SIGNED, not magnitudes: the lo of each axis is negative here.
    assert all(obj["extents"][ax][0] < 0 for ax in "xyz")


def test_extents_keep_an_asymmetric_mesh_asymmetric(show):
    """An asymmetric mesh keeps its asymmetry relative to the pivot (the origin-locating property):
    ComputerSecurity's box is off-centre on y and z, so lo != -hi there."""
    rc, out, _ = show("DeusEx.ComputerSecurity", "--json")
    assert rc == 0
    ext = json.loads(out)["extents"]
    assert ext == {"x": [-11, 11], "y": [-12, 3], "z": [-12, 8]}
    assert ext["y"][0] != -ext["y"][1] and ext["z"][0] != -ext["z"][1]


@pytest.mark.parametrize("fqcn, drawtype", [
    ("DeusEx.DeusExMover", "DT_Brush"),      # a brush class
    ("DeusEx.LaserEmitter", "DT_None"),      # a no-draw class
])
def test_non_mesh_class_reports_null_not_an_error(show, fqcn, drawtype):
    """DT_Brush/DT_None classes have no mesh: `mesh`/`extents` are null (a distinguishable value,
    never a missing key), and it is NOT an error (exit 0)."""
    rc, out, err = show(fqcn, "--json")
    assert rc == 0, err
    obj = json.loads(out)
    assert obj["drawtype"] == drawtype
    assert obj["mesh"] is None and obj["extents"] is None
    assert "mesh" in obj and "extents" in obj            # null, not omitted


def test_json_shape_matches_the_spec(show):
    """The `--json` object carries the §3 fact set: extents per-axis [lo,hi], collision numbers,
    prepivot triple, parent, abstract, placeable."""
    rc, out, _ = show("DeusEx.CrateUnbreakableLarge", "--json")
    obj = json.loads(out)
    assert set(obj) == {"ref", "drawtype", "mesh", "extents", "collision", "prepivot",
                        "parent", "abstract", "placeable", "classification"}
    assert obj["ref"] == "DeusEx.CrateUnbreakableLarge"
    assert obj["collision"] == {"radius": 56.5, "height": 56}   # 56.5 float, 56 integral -> int
    assert obj["prepivot"] == [0, 0, 0]
    assert obj["parent"] == "DeusEx.Containers"
    assert obj["abstract"] is False and obj["placeable"] is True
    assert obj["classification"] is None                        # unclassified → null, not omitted


def test_text_facts_block_is_appended(show):
    """The human `class show` keeps its property schema and appends a Facts block."""
    rc, out, _ = show("DeusEx.CrateUnbreakableLarge")
    assert rc == 0
    assert "Facts:" in out
    assert "drawtype:  DT_Mesh" in out
    assert "mesh:      DeusExDeco.CrateUnbreakableLarge" in out
    assert "extents:   x -40..40  y -40..40  z -56..56" in out
    assert "pre-Origin/RotOrigin, DrawScale not" in out       # the frame note
    assert "collision: radius 56.5  height 56" in out
    assert "prepivot:  0,0,0" in out
    assert "parent:    DeusEx.Containers" in out


def test_facts_are_read_from_resolved_defaults(show):
    """Provenance: the facts equal what `resolve_class_defaults` + the class index produce
    independently — collision/prepivot/drawtype/parent are READ from the (inheritance-aware) resolved
    defaults, never fabricated."""
    idx = _ued22_index()
    fqcn = "DeusEx.OfficeChair"
    d = uprops.resolve_class_defaults(fqcn, resolver=idx.resolver())
    rc, out, _ = show(fqcn, "--json")
    obj = json.loads(out)
    assert obj["drawtype"] == d[("drawtype", 0)]
    assert obj["collision"]["radius"] == float(d[("collisionradius", 0)])
    assert obj["parent"] == idx.ancestry(fqcn)[1]


# --------------------------------------------------------------- error dispositions (offline)

def test_unresolvable_mesh_package_exits_2_naming_it(show, monkeypatch):
    """A per-ref show on a DT_Mesh class whose Mesh package is not on the path exits 2 naming the
    class and mesh — never a traceback."""
    monkeypatch.setattr(resources, "class_defaults", lambda fqcn, project=None: {
        ("drawtype", 0): "DT_Mesh", ("mesh", 0): "LodMesh'GhostPkg.Missing'"})
    rc, out, err = show("DeusEx.CrateUnbreakableLarge")     # a real class (exists on the path)
    assert rc == 2
    assert out == ""                                         # nothing partial on stdout
    assert "DeusEx.CrateUnbreakableLarge" in err and "GhostPkg.Missing" in err
    assert "Traceback" not in err


def test_mesh_not_a_mesh_export_exits_2_naming_it(show, monkeypatch):
    """A DT_Mesh class whose Mesh names a nonexistent mesh in a real package exits 2 naming it."""
    monkeypatch.setattr(resources, "class_defaults", lambda fqcn, project=None: {
        ("drawtype", 0): "DT_Mesh", ("mesh", 0): "LodMesh'DeusExDeco.NoSuchMesh'"})
    rc, out, err = show("DeusEx.CrateUnbreakableLarge")
    assert rc == 2 and out == ""
    assert "DeusExDeco.NoSuchMesh" in err and "Traceback" not in err


def test_dt_mesh_with_none_mesh_exits_2(show, monkeypatch):
    """A DT_Mesh class whose Mesh default is None is unresolvable — exit 2, not a silent null."""
    monkeypatch.setattr(resources, "class_defaults", lambda fqcn, project=None: {
        ("drawtype", 0): "DT_Mesh", ("mesh", 0): "None"})
    rc, out, err = show("DeusEx.CrateUnbreakableLarge")
    assert rc == 2 and out == ""
    assert "DeusEx.CrateUnbreakableLarge" in err and "Traceback" not in err


def test_no_package_search_path_exits_2(show, monkeypatch):
    """`class show` with no composed .u path exits 2 ('no package search path'), not empty success
    and not a traceback."""
    monkeypatch.setattr(resources, "class_index",
                        lambda project=None: ClassIndex(_paths={}, _stems={}))
    rc, out, err = show("DeusEx.CrateUnbreakableLarge")
    assert rc == 2 and out == ""
    assert "no package search path" in err and "Traceback" not in err


# ------------------------------------------------------------------------ pure helpers (meshfacts)

def test_signed_extents_scale_resort_and_round():
    """`Scale` applied per-axis, each axis re-sorted to lo<=hi (a NEGATIVE Scale flips an axis and
    must not yield lo>hi), rounded to integer uu; an off-centre z keeps its seating asymmetry."""
    box = ((-10.0, -4.0, 2.0), (10.0, 4.0, 8.0), 1)
    ext = meshfacts.signed_extents(box, (-2.0, 1.0, 1.0))   # negative x Scale
    assert ext == {"x": [-20, 20], "y": [-4, 4], "z": [2, 8]}
    assert ext["x"][0] <= ext["x"][1]                       # re-sorted despite the flip


@pytest.mark.parametrize("text, expected", [
    ("LodMesh'DeusExDeco.BarStool'", ("DeusExDeco", "BarStool")),
    ("Mesh'Pkg.Group.Name'", ("Pkg", "Name")),             # a grouped ref: package first, name last
    ("None", None), (None, None), ("", None), ("garbage", None),
])
def test_parse_mesh_ref(text, expected):
    assert meshfacts.parse_mesh_ref(text) == expected
