"""`class preview` — the asset-catalog class arm C2 (native mesh thumbnail + `--rotate`/azimuth).

Like `test_class_facts`, the end-to-end tests run OFFLINE against the committed UED22 packages: a
real `ClassIndex`, real `resolve_class_defaults`, the promoted `umesh` decoder AND the promoted
`meshrender` rasterizer — the whole class -> Mesh -> decode -> skin -> render path with no game
install. A real render golden is exercised (the committed corpus resolves the crate's skin from its
own `.u`); it is asserted structurally (valid PNG, right size, textured => many colours), not
byte-exact, which would be brittle across Pillow versions.
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import pytest

from uedcli import meshfacts, meshrender, uprops
from uedcli.classindex import ClassIndex
from uedcli.cli import dispatch, resources
from uedcli.cli.main import build_parser

UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"
MESH_CLASS = "DeusEx.CrateUnbreakableLarge"          # DT_Mesh, skin in DeusExDeco.u (resolves offline)


def _ued22_index() -> ClassIndex:
    files = [(os.path.splitext(os.path.basename(f))[0], f) for f in glob.glob(str(UED22 / "*.u"))]
    return ClassIndex.from_files(files)


@pytest.fixture
def preview(monkeypatch, capsys, tmp_path):
    """Run `class preview …` against the committed UED22 corpus → `(rc, stdout, stderr)`. A bare
    `--out` is injected into `tmp_path` unless the argv already names one, so tests never litter."""
    pytest.importorskip("PIL")                        # the rasterizer writes a PNG via Pillow
    idx = _ued22_index()
    monkeypatch.setattr(resources, "resolve_project", lambda args: object())
    monkeypatch.setattr(resources, "class_index", lambda project=None: idx)
    monkeypatch.setattr(resources, "class_defaults",
                        lambda fqcn, project=None: uprops.resolve_class_defaults(
                            fqcn, resolver=idx.resolver()))

    def _run(*argv, out=None):
        if "--out" not in argv:
            out = out or str(tmp_path / "shot.png")
            argv = (*argv, "--out", out)
        args = build_parser().parse_args(["class", "preview", *argv])
        rc = dispatch.dispatch(args)
        cap = capsys.readouterr()
        return rc, cap.out, cap.err

    return _run


def _out_path(stdout: str) -> str:
    """The host path from a `<ref>\\t<path>` stdout line."""
    return stdout.strip().split("\t", 1)[1]


# --------------------------------------------------------------------- render (end to end, offline)

def test_iso_default_single_shot_renders_a_png(preview):
    """The `iso` default produces one 512x512 RGB PNG that actually decoded a skin (many colours —
    not a blank or flat-grey image), proving the class -> mesh -> skin -> raster path end to end."""
    from PIL import Image
    rc, out, err = preview(MESH_CLASS)
    assert rc == 0, err
    ref, path = out.strip().split("\t")
    assert ref == MESH_CLASS
    img = Image.open(path)
    assert img.mode == "RGB" and img.size == (512, 512)
    assert len(img.getcolors(maxcolors=1 << 20)) > 100      # textured: many distinct colours


def test_size_flag_sets_the_edge_length(preview):
    from PIL import Image
    rc, out, _ = preview(MESH_CLASS, "--size", "128")
    assert rc == 0
    assert Image.open(_out_path(out)).size == (128, 128)


def test_out_extension_is_replaced_by_png(preview, tmp_path):
    """`--out shot.jpg` writes shot.png (the bytes are PNG, so the name must say so)."""
    rc, out, _ = preview(MESH_CLASS, out=str(tmp_path / "thumb.jpg"))
    assert rc == 0
    written = _out_path(out)
    assert written.endswith("thumb.png") and os.path.exists(written)


# --------------------------------------------------------------------- azimuth / --rotate / --json

def test_json_carries_ref_path_azimuth_rotate(preview):
    """`--json` prints one object; the default shot's azimuth is the iso yaw (8192 uu = 45deg) and
    rotate is null (no pose applied)."""
    rc, out, _ = preview(MESH_CLASS, "--json")
    assert rc == 0
    obj = json.loads(out)
    assert set(obj) == {"ref", "path", "azimuth", "rotate"}
    assert obj["ref"] == MESH_CLASS and os.path.exists(obj["path"])
    assert obj["azimuth"] == 8192 and obj["rotate"] is None


def test_rotate_renders_and_azimuth_and_pose_reflect_it(preview, tmp_path):
    """`--rotate P,Y,R` renders AND the row's azimuth/pose reflect it: a 90deg yaw (16384 uu) shifts
    azimuth to 8192-16384 mod 65536 = 57344, records the pose, and changes the pixels."""
    rc0, out0, _ = preview(MESH_CLASS, "--json", out=str(tmp_path / "a.png"))
    rc1, out1, _ = preview(MESH_CLASS, "--rotate", "0,16384,0", "--json", out=str(tmp_path / "b.png"))
    assert rc0 == 0 and rc1 == 0
    o0, o1 = json.loads(out0), json.loads(out1)
    assert o1["azimuth"] == 57344 and o1["rotate"] == [0, 16384, 0]
    assert o0["azimuth"] == 8192                                   # unposed baseline
    assert Path(o0["path"]).read_bytes() != Path(o1["path"]).read_bytes()   # the pose changed pixels


def test_default_text_row_is_pipe_clean_azimuth_on_stderr(preview):
    """stdout is `<ref>\\t<path>` only (pipe-clean); the azimuth summary goes to stderr."""
    rc, out, err = preview(MESH_CLASS)
    assert rc == 0
    assert out.count("\n") == 1 and out.startswith(MESH_CLASS + "\t")
    assert "azimuth" not in out and "azimuth 8192" in err


# --------------------------------------------------------------- error dispositions (offline)

@pytest.mark.parametrize("fqcn, drawtype", [
    ("DeusEx.DeusExMover", "DT_Brush"),       # a brush class
    ("DeusEx.LaserEmitter", "DT_None"),       # a no-draw class
])
def test_non_mesh_class_is_not_an_error(preview, fqcn, drawtype):
    """A non-mesh class has nothing to render: exit 0 with a stderr note, NO stdout row (distinct from
    an unresolvable-mesh error) — matching `class show`'s null extents (spec §4)."""
    rc, out, err = preview(fqcn)
    assert rc == 0
    assert out == ""
    assert drawtype in err and "no mesh to preview" in err and "Traceback" not in err


def test_unresolvable_mesh_package_exits_2_naming_it(preview, monkeypatch):
    """A DT_Mesh class whose Mesh package is not on the path exits 2 naming the class and mesh."""
    monkeypatch.setattr(resources, "class_defaults", lambda fqcn, project=None: {
        ("drawtype", 0): "DT_Mesh", ("mesh", 0): "LodMesh'GhostPkg.Missing'"})
    rc, out, err = preview(MESH_CLASS)
    assert rc == 2 and out == ""
    assert MESH_CLASS in err and "GhostPkg.Missing" in err and "Traceback" not in err


def test_mesh_not_a_mesh_export_exits_2_naming_it(preview, monkeypatch):
    monkeypatch.setattr(resources, "class_defaults", lambda fqcn, project=None: {
        ("drawtype", 0): "DT_Mesh", ("mesh", 0): "LodMesh'DeusExDeco.NoSuchMesh'"})
    rc, out, err = preview(MESH_CLASS)
    assert rc == 2 and out == ""
    assert "DeusExDeco.NoSuchMesh" in err and "Traceback" not in err


def test_dt_mesh_with_none_mesh_exits_2(preview, monkeypatch):
    monkeypatch.setattr(resources, "class_defaults", lambda fqcn, project=None: {
        ("drawtype", 0): "DT_Mesh", ("mesh", 0): "None"})
    rc, out, err = preview(MESH_CLASS)
    assert rc == 2 and out == ""
    assert MESH_CLASS in err and "unresolvable" in err and "Traceback" not in err


def test_undecodable_skin_exits_2_naming_it(preview, monkeypatch):
    """A class whose MultiSkins override points at a package not on the path fails to DECODE that
    skin — exit 2 naming the ref, never a traceback or a wrong pixel (spec §4). The mesh itself is a
    real, decodable crate; only the class-side skin is bad."""
    real = uprops.resolve_class_defaults(MESH_CLASS, resolver=_ued22_index().resolver())
    patched = dict(real)
    patched[("multiskins", 0)] = "Texture'GhostPkg.MissingSkin'"
    monkeypatch.setattr(resources, "class_defaults", lambda fqcn, project=None: patched)
    rc, out, err = preview(MESH_CLASS)
    assert rc == 2 and out == ""
    assert "GhostPkg.MissingSkin" in err and "did not decode" in err and "Traceback" not in err


def test_no_package_search_path_exits_2(preview, monkeypatch):
    """`class preview` with no composed .u path exits 2 ('no package search path'), never a
    traceback or an empty success."""
    monkeypatch.setattr(resources, "class_index",
                        lambda project=None: ClassIndex(_paths={}, _stems={}))
    rc, out, err = preview(MESH_CLASS)
    assert rc == 2 and out == ""
    assert "no package search path" in err and "Traceback" not in err


def test_unknown_class_exits_2_no_traceback(preview):
    rc, out, err = preview("DeusEx.NoSuchClassAtAll")
    assert rc == 2 and out == ""
    assert "unknown class" in err and "NoSuchClassAtAll" in err and "Traceback" not in err


# --------------------------------------------------------------------- frame agreement + pure helpers

def test_azimuth_is_iso_yaw_shifted_by_rotate_yaw():
    """Pure: azimuth = iso_yaw(8192) - rotate_yaw, mod 65536 — a mesh-local reading, not world
    facing. Only the yaw component of --rotate moves it."""
    assert meshrender.azimuth_uu((0, 0, 0)) == 8192
    assert meshrender.azimuth_uu((0, 16384, 0)) == 57344       # -8192 mod 65536
    assert meshrender.azimuth_uu((0, 8192, 8192)) == 0         # pitch/roll do not move azimuth
    assert meshrender.azimuth_uu((0, 65536 + 8192, 0)) == 0    # a yaw past a full turn wraps


def test_preview_and_facts_share_one_decode(preview):
    """The picture and the extents read the SAME decoded body (spec §3, §4): `decode_mesh` (preview)
    and `decode_mesh_box` (facts) return the identical box/scale for the class's Mesh, so they cannot
    disagree about the mesh-local frame."""
    idx = _ued22_index()
    ref = meshfacts.parse_mesh_ref(
        uprops.resolve_class_defaults(MESH_CLASS, resolver=idx.resolver())[("mesh", 0)])
    _d, mesh, _pkg = meshfacts.decode_mesh(ref, class_fqcn=MESH_CLASS, resolver=idx.resolver())
    _d2, box, scale = meshfacts.decode_mesh_box(ref, class_fqcn=MESH_CLASS, resolver=idx.resolver())
    assert (box, scale) == (mesh.box, mesh.scale)
