from collections import ChainMap
from types import SimpleNamespace

import pytest

from uedcli import meshrender, utexture
from uedcli.typedprops import stored_prop_map


class _FakeMesh:
    """Minimal stand-in exercising both frame_triangles branches (and, with `scale`, `render_class`)."""
    def __init__(self, *, faces=None, wedges=None, materials=None, tris=None, verts,
                 frame_verts=0, special_verts=0, scale=(1.0, 1.0, 1.0)):
        self.faces = faces or []
        self.wedges = wedges or []
        self.materials = materials or []
        self.tris = tris or []
        self.verts = verts
        self.frame_verts = frame_verts
        self.special_verts = special_verts
        self.scale = scale


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
    the flag the same way — the branch DX characters actually take. Keyed by the mesh's OWN texture
    index (`_SkinMesh`'s one material's `TextureIndex` is 0), not material ordinal — see
    `resolve-skins-keys-by-material-ordinal-not`."""
    _skin_resolver(monkeypatch, b_masked=True)
    defaults = {("multiskins", 0): "Texture'SkinPkg.Group.GrateTex'"}
    skins = meshrender.resolve_skins(_SkinMesh(), _SkinPkg(), defaults, [], class_fqcn="Pkg.Class")
    assert skins[0][3] is True


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
# `_ThreeSlotMesh`'s three materials point at TEXTURE indices 10/11/12 — deliberately NOT equal to
# their material ordinal (0/1/2) — so a test using it can only pass by keying `MultiSkins`/`Skin`
# lookups on the mesh's real `Textures` index (`Count`), never on material-list position (the exact
# divergence `resolve-skins-keys-by-material-ordinal-not` found live on `DeusExCharacters.GM_Trench`,
# materials 3-6 of 7 landing on the wrong skin one slot over).

class _ThreeSlotMesh:
    """Three material slots, each pointing at its OWN mesh-side texture (indices 10/11/12) — so a
    resolved skin's identity pins exactly which source (actor/class/mesh) won at that slot. Indices
    0-9 are `0` (UE1's "no ref" convention, matching real `Textures` array padding — NOT Python
    `None`, which `upackage.object_path` never receives in production)."""
    materials = [(0, 10), (0, 11), (0, 12)]
    textures = [0] * 10 + [10, 11, 12]


class _ThreeSlotPkg:
    """`object_path` names each texture index distinctly (`Mesh0`/`Mesh1`/`Mesh2`); `0` (no ref)
    resolves to `None`, matching `upackage.Package.object_path`'s real "0 ref -> None" contract."""
    def object_path(self, idx):
        if idx == 0:
            return None
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
    EVERY slot, including slot 0 where a naive "later write wins" merge could go either way. `Skin`
    only ever competes at texture index 0 (`Count == 0`), so this needs a mesh whose material
    actually sits at texture index 0 — `_SkinMesh` (materials=[(0, 0)])."""
    _named_resolver(monkeypatch)
    defaults = {("multiskins", 0): "Texture'SkinPkg.Group.MultiWins'",
               ("skin", 0): "Texture'SkinPkg.Group.SkinLoses'"}
    skins = meshrender.resolve_skins(_SkinMesh(), _SkinPkg(), defaults, [], class_fqcn="Pkg.Class")
    assert skins[0][2][:1] == b"M"    # MultiWins, not SkinLoses


def test_resolve_skins_skin_is_a_slot0_first_fallback_not_a_whole_mesh_override(monkeypatch):
    """`Skin` is a SLOT-0-FIRST fallback: at texture index 0 it beats the mesh's own texture (the
    `i != 0` gate in `UMesh::GetTexture` never applies there — this is the `Count == 0` half,
    confirmed by the reference implementation's own `?` config: `Skin` alone renders, the mesh's
    `Textures(0)` does not); at any OTHER texture index it reaches the mesh ONLY when that slot has
    no texture of its own — the Earth-mesh live-probe finding (slot 1, 480 visible faces:
    `Skin=BRIGHT` left it unchanged, `MultiSkins(1)=BRIGHT` repainted it). A NON-ZERO slot WITH its
    own mesh texture ignores `Skin` entirely — the mutation this test must catch: deleting the
    `t != 0` gate (mesh texture always beats `Skin`) leaves the suite green unless index 0 is
    asserted too."""
    _named_resolver(monkeypatch)
    # Slot 0 (texture index 0): Skin beats the mesh's own texture there (_SkinMesh, one material at
    # texture index 0).
    skins = meshrender.resolve_skins(_SkinMesh(), _SkinPkg(),
                                     {("skin", 0): "Texture'SkinPkg.Group.SkinTex'"}, [],
                                     class_fqcn="Pkg.Class")
    assert skins[0][2][:1] == b"S"
    # A non-zero texture index (11, material 1 of `_ThreeSlotMesh`) HAS its own mesh texture --
    # Skin never even gets checked there, regardless of what `("skin", 0)` says.
    skins = meshrender.resolve_skins(_ThreeSlotMesh(), _ThreeSlotPkg(),
                                     {("skin", 0): "Texture'SkinPkg.Group.SkinTex'"}, [],
                                     class_fqcn="Pkg.Class")
    assert skins[1][2][:1] == b"M"    # Mesh1 (texture index 11) -- Skin does not reach it


def test_resolve_skins_skin_reaches_a_nonzero_slot_with_no_mesh_texture_there(monkeypatch):
    """The other half of the same rule: a non-zero TEXTURE INDEX the mesh has no texture for (its
    `Textures[t]` slot is `0`, UE1's "no ref") DOES fall through to `Skin` -- exactly the `Count &&
    Textures[Count]` branch failing in `UMesh::GetTexture`. Texture index 5 is one of
    `_ThreeSlotMesh`'s padding slots (0-9, all `0`/no-ref) -- a material can validly point at it
    (unlike an out-of-`Textures`-bounds index, which the real engine's data never contains)."""
    _named_resolver(monkeypatch)

    class _Slot1PointsAtAnEmptyTextureSlot(_ThreeSlotMesh):
        materials = [(0, 10), (0, 5)]      # material 1's TextureIndex (5) has no texture (0/no-ref)
    skins = meshrender.resolve_skins(_Slot1PointsAtAnEmptyTextureSlot(), _ThreeSlotPkg(),
                                     {("skin", 0): "Texture'SkinPkg.Group.SkinTex'"}, [],
                                     class_fqcn="Pkg.Class")
    assert skins[1][2][:1] == b"S"    # no mesh texture at texture index 5 -- Skin reaches it


def test_resolve_skins_actor_override_wins_per_element_not_whole_array(monkeypatch):
    """`ChainMap(stored, defaults)` mirrors `_mesh_actor_polys`'s actual merge: the actor's own
    `MultiSkins(10)=` wins at material 0 (real texture index 10); the class default still wins at
    material 1 (texture index 11, the actor didn't restate it); material 2 (texture index 12) falls
    through to the mesh's own texture (neither actor nor class states it) — per-ELEMENT shadowing,
    not the actor's presence blanking the whole array. Keyed by the mesh's real `Textures` index
    (10/11/12), not material ordinal (0/1/2) — `resolve-skins-keys-by-material-ordinal-not`."""
    _named_resolver(monkeypatch)
    class_defaults = {("multiskins", 10): "Texture'SkinPkg.Group.ClassSkin0'",
                      ("multiskins", 11): "Texture'SkinPkg.Group.ClassSkin1'"}
    actor_props = [("MultiSkins(10)", "Texture'SkinPkg.Group.ActorSkin0'")]
    merged = ChainMap(stored_prop_map(actor_props), class_defaults)
    skins = meshrender.resolve_skins(_ThreeSlotMesh(), _ThreeSlotPkg(), merged, [],
                                     class_fqcn="Pkg.Class")
    assert skins[0][2][:1] == b"A"    # ActorSkin0 — actor's own override won
    assert skins[1][2][:1] == b"C"    # ClassSkin1 — class default, actor didn't restate it
    assert skins[2][2][:1] == b"M"    # Mesh2 — neither states it, mesh's own texture survives


def test_resolve_skins_actor_empty_override_falls_through_to_mesh_texture(monkeypatch):
    """An actor stating `MultiSkins(10)=` (empty) or `=None` is the SAME "no ref" signal `_skin_ref`
    already gives a class default — it does not fall back to the class default, it clears the
    override entirely and the mesh's own texture (tier 3) shows, consistent with today's
    class-level None handling. Material 0's real texture index is 10 (`_ThreeSlotMesh`)."""
    _named_resolver(monkeypatch)
    class_defaults = {("multiskins", 10): "Texture'SkinPkg.Group.ClassSkin0'"}
    for empty_text in ("", "None"):
        actor_props = [("MultiSkins(10)", empty_text)]
        merged = ChainMap(stored_prop_map(actor_props), class_defaults)
        skins = meshrender.resolve_skins(_ThreeSlotMesh(), _ThreeSlotPkg(), merged, [],
                                         class_fqcn="Pkg.Class")
        assert skins[0][2][:1] == b"M"    # Mesh0 — override cleared to nothing, not class default


# ── material ordinal != texture index (`resolve-skins-keys-by-material-ordinal-not`, found on
# `DeusExCharacters.GM_Trench`: materials 3-6 of 7 have `TextureIndex` 4/5/6/7 -- NOT 3/4/5/6 --
# and the old material-ordinal-keyed lookup shifted every one of them onto the WRONG MultiSkins
# entry, one slot over) ────────────────────────────────────────────────────────────────────────

class _ShiftedIndexMesh:
    """Shaped like `GM_Trench`: 4 materials, but material 3's `TextureIndex` is 4, not 3 — a gap,
    exactly the pattern that shifted Manderley's skins by one."""
    materials = [(0, 0), (0, 1), (0, 2), (0, 4)]      # (PolyFlags, TextureIndex) -- note the gap
    textures = [20, 21, 22, 0, 24]                     # 5 slots; index 3 unused by any material


class _ShiftedIndexPkg:
    """Names each texture value distinctly (`Tex20`/`Tex21`/`Tex22`/`Tex24`, matching
    `mesh.textures`'s own values); `0` (no ref) resolves to `None`, same as `_ThreeSlotPkg`."""
    def object_path(self, idx):
        if idx == 0:
            return None
        return f"MeshPkg.Group.Tex{idx}"


def test_resolve_skins_keys_multiskins_by_texture_index_not_material_ordinal(monkeypatch):
    """The Manderley regression: material 3's `TextureIndex` is 4, so its `MultiSkins` override
    must come from `MultiSkins(4)`, never `MultiSkins(3)` — keying by material ordinal (the bug)
    would give material 3 the entry meant for texture index 3 (which no material here actually
    uses) instead of its own. Each ref's FIRST LETTER is distinct so the 1-byte resolver tag
    (`_named_resolver`) can tell them apart unambiguously."""
    _named_resolver(monkeypatch)
    defaults = {("multiskins", 0): "Texture'SkinPkg.Group.Alpha'",
               ("multiskins", 1): "Texture'SkinPkg.Group.Bravo'",
               ("multiskins", 2): "Texture'SkinPkg.Group.Charlie'",
               ("multiskins", 3): "Texture'SkinPkg.Group.WrongIfMaterialOrdinal'",
               ("multiskins", 4): "Texture'SkinPkg.Group.Echo'"}
    skins = meshrender.resolve_skins(_ShiftedIndexMesh(), _ShiftedIndexPkg(), defaults, [],
                                     class_fqcn="Pkg.Class")
    assert skins[0][2][:1] == b"A"
    assert skins[1][2][:1] == b"B"
    assert skins[2][2][:1] == b"C"
    # Material 3's real TextureIndex is 4 -- it must get Echo, NOT the ("multiskins", 3) entry
    # ("W...", which nothing real would ever apply to it -- texture index 3 has no material here).
    assert skins[3][2][:1] == b"E"


class _NoMeshTexMesh:
    """One material at texture index 0, whose `Textures[0]` is `0` (no ref) — the mesh contributes
    NO texture of its own, so the only resolve() call in play is the actor/class override's. (An
    EMPTY `textures` list would mean `Textures.Num() == 0`, which the real engine's own
    `DrawLodMesh` loop bound would then never call `GetTexture` for at all — not what this test
    wants to exercise.)"""
    materials = [(0, 0)]
    textures = [0]


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


# ── PF_Translucent/PF_Modulated: no blend compositing, so skip rather than draw opaque (found live
# on `DeusExCharacters.GM_Trench`'s eye-height "glasses lens" materials, which rendered as a solid
# dark band across a character's face — real `PolyFlags` 0x104/0x140, PF_TwoSided|Translucent and
# PF_TwoSided|Modulated) ──────────────────────────────────────────────────────────────────────────

def test_render_class_skips_translucent_triangles(monkeypatch):
    """A material flagged `PF_Translucent` draws nothing (no opaque compositing to fall back to) —
    the whole image stays background, matching a mesh with no triangles rasterized at all."""
    _skin_resolver(monkeypatch, b_masked=False)
    mesh = _FakeMesh(
        verts=[(-50, -50, 0), (50, -50, 0), (0, 50, 0)],
        wedges=[(0, 0, 0), (1, 255, 0), (2, 0, 255)],
        faces=[((0, 1, 2), 0)],
        materials=[(meshrender.PF_TRANSLUCENT, 0)],
    )
    img, _azimuth = meshrender.render_class(mesh, {0: (2, 1, b"\xff\x00\x00\x00\xff\x00", False, b"\x01\x00")},
                                            size=64)
    assert img.getcolors() == [(64 * 64, meshrender._BG)]


def test_render_class_skips_modulated_triangles_too(monkeypatch):
    """Same disposition for `PF_Modulated` (screen-blend) — the other blend mode this mesh format
    uses for glass/energy-field materials."""
    mesh = _FakeMesh(
        verts=[(-50, -50, 0), (50, -50, 0), (0, 50, 0)],
        wedges=[(0, 0, 0), (1, 255, 0), (2, 0, 255)],
        faces=[((0, 1, 2), 0)],
        materials=[(meshrender.PF_MODULATED, 0)],
    )
    img, _azimuth = meshrender.render_class(mesh, {0: (2, 1, b"\xff\x00\x00\x00\xff\x00", False, b"\x01\x00")},
                                            size=64)
    assert img.getcolors() == [(64 * 64, meshrender._BG)]


def test_render_class_still_draws_an_opaque_triangle_with_the_same_shape(monkeypatch):
    """Control: the SAME mesh with `PolyFlags=0` (no translucent/modulated bit) draws normally —
    proves the skip is flag-gated, not a side effect of the fixture shape."""
    mesh = _FakeMesh(
        verts=[(-50, -50, 0), (50, -50, 0), (0, 50, 0)],
        wedges=[(0, 0, 0), (1, 255, 0), (2, 0, 255)],
        faces=[((0, 1, 2), 0)],
        materials=[(0, 0)],
    )
    img, _azimuth = meshrender.render_class(mesh, {0: (2, 1, b"\xff\x00\x00\x00\xff\x00", False, b"\x01\x00")},
                                            size=64)
    colors = img.getcolors()
    assert len(colors) > 1 and any(c != meshrender._BG for _n, c in colors)
