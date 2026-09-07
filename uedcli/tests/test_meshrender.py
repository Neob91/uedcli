from types import SimpleNamespace

import pytest

from uedcli import meshrender, utexture


class _FakeMesh:
    """Minimal stand-in exercising both frame_triangles branches."""
    def __init__(self, *, faces=None, wedges=None, materials=None, tris=None, verts,
                 frame_verts=0, special_verts=0):
        self.faces = faces or []
        self.wedges = wedges or []
        self.materials = materials or []
        self.tris = tris or []
        self.verts = verts
        self.frame_verts = frame_verts
        self.special_verts = special_verts


def test_frame_triangles_lodmesh_flags_come_from_materials():
    # One LodMesh triangle: Face (wedges 0,1,2 -> material 0), Materials[0].PolyFlags = 0x20 (PF_TwoSided)
    mesh = _FakeMesh(
        verts=[(0, 0, 0), (10, 0, 0), (0, 10, 0)],
        wedges=[(0, 0, 0), (1, 255, 0), (2, 0, 255)],
        faces=[((0, 1, 2), 0)],
        materials=[(0x20, 5)],  # (PolyFlags, TextureIndex)
    )
    tris = meshrender.frame_triangles(mesh, frame=0)
    assert len(tris) == 1
    v0, v1, v2, uv0, uv1, uv2, material_index, poly_flags = tris[0]
    assert material_index == 0
    assert poly_flags == 0x20


def test_frame_triangles_plain_mesh_flags_come_from_tri():
    # A plain Mesh (no faces/wedges): one FMeshTri with its OWN PolyFlags = 0x08 (PF_Masked)
    mesh = _FakeMesh(
        verts=[(0, 0, 0), (10, 0, 0), (0, 10, 0)],
        tris=[((0, 1, 2), (0, 0, 255, 0, 0, 255), 0x08, 3)],  # (iv, uv, flags, tex)
    )
    tris = meshrender.frame_triangles(mesh, frame=0)
    assert len(tris) == 1
    v0, v1, v2, uv0, uv1, uv2, material_index, poly_flags = tris[0]
    assert material_index == 3        # texture index, unchanged behavior
    assert poly_flags == 0x08         # NOT 0 — this is what Task 1 fixes


class _SkinMesh:
    """A mesh with one material pointing at one mesh-side texture."""
    materials = [(0, 0)]              # (PolyFlags, TextureIndex)
    textures = [1]


class _SkinPkg:
    def object_path(self, _idx):
        return "SkinPkg.Group.GrateTex"


def _skin_resolver(monkeypatch, *, b_masked):
    """Point `resolve_skins`'s internal `utexture.TextureResolver` at a decoded stub."""
    decoded = SimpleNamespace(width=2, height=1, rgb=b"\xff\x00\x00\x00\xff\x00",
                              mask=b"\x01\x00", b_masked=b_masked)
    monkeypatch.setattr(utexture, "TextureResolver",
                        lambda paths, class_index=None: SimpleNamespace(resolve=lambda ref: decoded))


def _skin_error(monkeypatch, case: str):
    """Point `resolve_skins`'s internal resolver at a `TextureError` of `case`."""
    err = utexture.TextureError("SkinPkg.GrateTex", case, f"stub {case}")
    monkeypatch.setattr(utexture, "TextureResolver",
                        lambda paths, class_index=None: SimpleNamespace(resolve=lambda ref: err))


def test_resolve_skins_carries_the_textures_bmasked_flag(monkeypatch):
    """A skin's own `bMasked` reaches the caller: `level photo --native` alpha-tests a bMasked mesh
    skin even when the triangle carries no PF_Masked flag, exactly as it does for a bMasked surface
    texture. Dropping the flag rendered such a skin opaque."""
    _skin_resolver(monkeypatch, b_masked=True)
    skins = meshrender.resolve_skins(_SkinMesh(), _SkinPkg(), {}, [], class_fqcn="Pkg.Class")
    assert skins == {0: (2, 1, b"\xff\x00\x00\x00\xff\x00", True, b"\x01\x00")}

    _skin_resolver(monkeypatch, b_masked=False)
    assert meshrender.resolve_skins(_SkinMesh(), _SkinPkg(), {}, [],
                                    class_fqcn="Pkg.Class")[0][3] is False


def test_resolve_skins_class_override_carries_bmasked_too(monkeypatch):
    """The class-side `MultiSkins`/`Skin` override (which WINS over the mesh's own textures) reports
    the flag the same way — the branch DX characters actually take."""
    _skin_resolver(monkeypatch, b_masked=True)
    defaults = {("multiskins", 1): "Texture'SkinPkg.Group.GrateTex'"}
    skins = meshrender.resolve_skins(_SkinMesh(), _SkinPkg(), defaults, [], class_fqcn="Pkg.Class")
    assert skins[1][3] is True


def test_resolve_skins_procedural_skin_renders_red(monkeypatch):
    """A procedural (bitmap-less) skin decodes to `no-mip-data` and renders as solid RED, not a
    hard-fail (owner ruling 2026-09-07). Needs the widened resolver (class_index) so an
    `Engine.Texture` descendant resolves to `no-mip-data` at all, not `unknown-texture`."""
    _skin_error(monkeypatch, "no-mip-data")
    skins = meshrender.resolve_skins(_SkinMesh(), _SkinPkg(), {}, [], class_fqcn="Pkg.Class")
    assert skins == {0: meshrender.PROCEDURAL_RED}


def test_resolve_skins_genuine_undecodable_skin_still_raises(monkeypatch):
    """A non-procedural undecodable skin still hard-fails, naming it and the case (spec §4) — only
    procedural is substituted, never a real error."""
    _skin_error(monkeypatch, "unknown-texture")
    with pytest.raises(meshrender.PreviewError, match="unknown-texture"):
        meshrender.resolve_skins(_SkinMesh(), _SkinPkg(), {}, [], class_fqcn="Pkg.Class")
