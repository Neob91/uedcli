from collections import ChainMap
from types import SimpleNamespace

import pytest

from uedcli import meshrender, utexture
from uedcli.typedprops import stored_prop_map


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


# ── per-actor MultiSkins/Skin override (board `per-actor-skins-override-in-native-mesh-render`) ──

class _ThreeSlotMesh:
    """Three material slots, each pointing at its OWN mesh-side texture (indices 10/11/12) — so a
    resolved skin's identity pins exactly which source (actor/class/mesh) won at that slot."""
    materials = [(0, 10), (0, 11), (0, 12)]
    textures = [None] * 10 + [10, 11, 12]


class _ThreeSlotPkg:
    """`object_path` names each texture index distinctly (`Mesh0`/`Mesh1`/`Mesh2`)."""
    def object_path(self, idx):
        return f"MeshPkg.Group.Mesh{idx - 10}"


def _named_resolver(monkeypatch):
    """Every ref resolves to a 1x1 texel whose red channel encodes which ref it was (so a test can
    tell resolved skins apart by identity, not just presence)."""
    def resolve(ref):
        tag = ref.split(".")[-1].encode()[:1] or b"\x00"
        return SimpleNamespace(width=1, height=1, rgb=tag + b"\x00\x00", mask=b"\x01", b_masked=False)
    monkeypatch.setattr(utexture, "TextureResolver",
                        lambda paths, class_index=None: SimpleNamespace(resolve=resolve))


def test_resolve_skins_multiskins_beats_skin_at_every_slot(monkeypatch):
    """Pins `UMesh::GetTexture`'s real precedence (disassembly+live-probe verified,
    `dev/docs/spikes/2026-09-10-multiskin-skin-precedence/`): `MultiSkins[i]` wins over `Skin` at
    EVERY slot, including slot 0 where a naive "later write wins" merge could go either way."""
    _named_resolver(monkeypatch)
    defaults = {("multiskins", 0): "Texture'SkinPkg.Group.MultiWins'",
               ("skin", 0): "Texture'SkinPkg.Group.SkinLoses'"}
    skins = meshrender.resolve_skins(_ThreeSlotMesh(), _ThreeSlotPkg(), defaults, [],
                                     class_fqcn="Pkg.Class")
    assert skins[0][2][:1] == b"M"    # MultiWins, not SkinLoses


def test_resolve_skins_skin_is_a_slot0_first_fallback_not_a_whole_mesh_override(monkeypatch):
    """`Skin` is a SLOT-0-FIRST fallback: at slot 0 it beats the mesh's own texture (the `i != 0`
    gate in `UMesh::GetTexture` never applies there — this is the `Count == 0` half, confirmed by
    the reference implementation's own `?` config: `Skin` alone renders, the mesh's `Textures(0)`
    does not); at any OTHER slot it reaches the mesh ONLY when that slot has no texture of its own —
    the Earth-mesh live-probe finding (slot 1, 480 visible faces: `Skin=BRIGHT` left it unchanged,
    `MultiSkins(1)=BRIGHT` repainted it). A NON-ZERO slot WITH its own mesh texture ignores `Skin`
    entirely — the mutation this test must catch: deleting the `mi != 0` gate (mesh texture always
    beats `Skin`) leaves the suite green unless slot 0 is asserted too."""
    _named_resolver(monkeypatch)
    defaults = {("skin", 0): "Texture'SkinPkg.Group.SkinTex'"}
    skins = meshrender.resolve_skins(_ThreeSlotMesh(), _ThreeSlotPkg(), defaults, [],
                                     class_fqcn="Pkg.Class")
    assert skins[0][2][:1] == b"S"    # slot 0 -- Skin beats the mesh's own texture (Mesh0)
    assert skins[1][2][:1] == b"M"    # slot 1 HAS its own mesh texture (Mesh1) -- Skin does not reach it


def test_resolve_skins_skin_reaches_a_nonzero_slot_with_no_mesh_texture_there(monkeypatch):
    """The other half of the same rule: a non-zero slot the MESH has no texture for (its
    `Materials[i].TextureIndex` out of range) DOES fall through to `Skin` -- exactly the `Count &&
    Textures[Count]` branch failing in `UMesh::GetTexture`."""
    _named_resolver(monkeypatch)

    class _Slot1HasNoMeshTexture(_ThreeSlotMesh):
        materials = [(0, 10), (0, 99)]      # slot 1's TextureIndex (99) is out of range
    skins = meshrender.resolve_skins(_Slot1HasNoMeshTexture(), _ThreeSlotPkg(),
                                     {("skin", 0): "Texture'SkinPkg.Group.SkinTex'"}, [],
                                     class_fqcn="Pkg.Class")
    assert skins[1][2][:1] == b"S"    # no mesh texture at slot 1 -- Skin reaches it


def test_resolve_skins_actor_override_wins_per_element_not_whole_array(monkeypatch):
    """`ChainMap(stored, defaults)` mirrors `_mesh_actor_polys`'s actual merge: the actor's own
    `MultiSkins(0)=` wins at index 0; the class default still wins at index 1 (the actor didn't
    restate it); index 2 falls through to the mesh's own texture (neither actor nor class states
    it) — per-ELEMENT shadowing, not the actor's presence blanking the whole array."""
    _named_resolver(monkeypatch)
    class_defaults = {("multiskins", 0): "Texture'SkinPkg.Group.ClassSkin0'",
                      ("multiskins", 1): "Texture'SkinPkg.Group.ClassSkin1'"}
    actor_props = [("MultiSkins(0)", "Texture'SkinPkg.Group.ActorSkin0'")]
    merged = ChainMap(stored_prop_map(actor_props), class_defaults)
    skins = meshrender.resolve_skins(_ThreeSlotMesh(), _ThreeSlotPkg(), merged, [],
                                     class_fqcn="Pkg.Class")
    assert skins[0][2][:1] == b"A"    # ActorSkin0 — actor's own override won
    assert skins[1][2][:1] == b"C"    # ClassSkin1 — class default, actor didn't restate it
    assert skins[2][2][:1] == b"M"    # Mesh2 — neither states it, mesh's own texture survives


def test_resolve_skins_actor_empty_override_falls_through_to_mesh_texture(monkeypatch):
    """An actor stating `MultiSkins(0)=` (empty) or `=None` is the SAME "no ref" signal `_skin_ref`
    already gives a class default — it does not fall back to the class default, it clears the
    override entirely and the mesh's own texture (tier 3) shows, consistent with today's
    class-level None handling."""
    _named_resolver(monkeypatch)
    class_defaults = {("multiskins", 0): "Texture'SkinPkg.Group.ClassSkin0'"}
    for empty_text in ("", "None"):
        actor_props = [("MultiSkins(0)", empty_text)]
        merged = ChainMap(stored_prop_map(actor_props), class_defaults)
        skins = meshrender.resolve_skins(_ThreeSlotMesh(), _ThreeSlotPkg(), merged, [],
                                         class_fqcn="Pkg.Class")
        assert skins[0][2][:1] == b"M"    # Mesh0 — override cleared to nothing, not class default


class _NoMeshTexMesh:
    """One material slot whose texture index is out of range — the mesh contributes NO texture of
    its own, so the only resolve() call in play is the actor/class override's."""
    materials = [(0, 0)]
    textures: list = []


def test_resolve_skins_error_names_the_ref_not_a_wrong_source_label(monkeypatch):
    """An unresolvable override's error names the ref (spec: error messages include the offending
    value) without claiming it came from "class" when it may have been the ACTOR's own — the
    message is neutral now that `defaults` can carry either source (Part C)."""
    _skin_error(monkeypatch, "unknown-texture")
    actor_props = [("MultiSkins(0)", "Texture'SkinPkg.Group.BadRef'")]
    merged = ChainMap(stored_prop_map(actor_props), {})
    with pytest.raises(meshrender.PreviewError, match="multiskins override") as exc:
        meshrender.resolve_skins(_NoMeshTexMesh(), _SkinPkg(), merged, [], class_fqcn="Pkg.Class")
    assert "class " not in str(exc.value).split(":", 1)[1].split("multiskins")[0]
