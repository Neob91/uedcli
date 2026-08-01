"""Mesh-format regressions — pin the findings of spike `2026-07-25-native-mesh-decode` so a change
to the decoder (or a package swap) trips a red test instead of drifting unnoticed (uedcli
`dev/docs/rules/spikes.md` "pin the finding, or it rots").

The decoder was promoted out of the spike into `uedcli/umesh.py` (the class arm's mesh facts read
it); these tests now keep the PRODUCTION module honest.

The OFFLINE tests run against the **committed** UED22 v69 packages (`uned/UED22/*.u`), which carry
stock-Unreal 4-byte packed vertices. The Deus Ex v68 side (8-byte vertices) lives in the
user-supplied, gitignored install, so those tests skip when it is absent.

The load-bearing oracle in every test is **consume-to-exact-end**: an export body occupies exactly
`[soff, soff+ssize)`, so a parse that lands on the final byte is structurally correct.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from uedcli import umesh as _umesh_module
from uedcli.upackage import load_package

from .conftest import install_system_root

UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"


def _umesh():
    """The promoted production decoder (`uedcli/umesh.py`)."""
    return _umesh_module


def _pkg_or_skip(path: Path):
    if not path.exists():
        pytest.skip(f"{path} not present")
    return load_package(str(path))


def _parse_all(mod, pkg):
    ok, fails = 0, []
    for j in mod.mesh_exports(pkg):
        try:
            mod.parse_mesh(pkg, j)
            ok += 1
        except Exception as ex:                      # noqa: BLE001 — any desync is a failure
            fails.append((pkg.names[pkg.exports[j]["nm"]], str(ex)))
    return ok, fails


@pytest.mark.parametrize("stem", ["DeusExDeco", "DeusExCharacters", "DeusExItems"])
def test_v69_packages_parse_to_exact_end(stem):
    """Every mesh in the committed v69 (UT-lineage) packages decodes consuming exactly its export
    body — the whole-layout assertion, including the `ULodMesh` tail."""
    mod = _umesh()
    pkg = _pkg_or_skip(UED22 / f"{stem}.u")
    ok, fails = _parse_all(mod, pkg)
    assert not fails, f"{stem}: {len(fails)} mesh(es) failed to decode: {fails[:3]}"
    assert ok > 0


def test_v69_vertex_stride_is_detected_as_packed():
    """Stock-Unreal packages use the 4-byte bit-packed `FMeshVert`, and the decoder DETECTS that
    off the TLazyArray skip offset rather than being told (spike: one decoder, no substrate flag)."""
    mod = _umesh()
    pkg = _pkg_or_skip(UED22 / "DeusExDeco.u")
    strides = {mod.parse_mesh(pkg, j).vert_stride for j in mod.mesh_exports(pkg)[:40]}
    assert strides == {4}, f"expected packed 4-byte verts in a v69 package, got {strides}"


def test_lodmesh_tail_is_not_deusex_specific():
    """The 5-byte `ULodMesh` tail (empty `RemapAnimVerts` + `OldFrameVerts`) tracks LodMesh-vs-Mesh,
    NOT Deus Ex-vs-Unreal: the UT-lineage v69 packages carry it too, so a decoder that treated it as
    a licensee quirk and skipped it on non-DX input would desync. (The spike's first reading called
    it a licensee addition; this test pins the correction.)

    The assertion is STRUCTURAL — both classes present, all consuming to their exact end — not on
    the tail's VALUE: retail v68 writes `OldFrameVerts == FrameVerts`, while the v69 stubs written
    by UED22's own UCC write 0. Only the field's presence is invariant.
    """
    mod = _umesh()
    pkg = _pkg_or_skip(UED22 / "DeusExDeco.u")
    classes = {pkg.object_class_name(j + 1) for j in mod.mesh_exports(pkg)}
    assert {"LodMesh", "Mesh"} <= classes, f"corpus lacks both mesh classes: {classes}"
    ok, fails = _parse_all(mod, pkg)
    assert not fails and ok > 0, f"tail handling desyncs on v69: {fails[:3]}"


def test_anim_seq_group_is_a_single_fname_not_an_array():
    """`FMeshAnimSeq.Group` is ONE FName, not `TArray<FName> Groups`. A grouped sequence is the
    only discriminator (an ungrouped one writes a 0 byte that reads the same either way), so this
    asserts a mesh that actually uses groups decodes — under the TArray reading the group index is
    taken as an element count and the parse detonates."""
    mod = _umesh()
    pkg = _pkg_or_skip(UED22 / "DeusExCharacters.u")
    j = next((j for j in mod.mesh_exports(pkg)
              if pkg.names[pkg.exports[j]["nm"]] == "Pigeon"), None)
    if j is None:
        pytest.skip("Pigeon mesh not in this package")
    m = mod.parse_mesh(pkg, j)
    groups = [seq[1] for seq in m.anim_seqs]
    assert any(g != 0 for g in groups), "expected at least one grouped sequence on Pigeon"


def test_special_verts_precede_the_model_verts_in_each_frame():
    """A wedge's `iVertex` is relative to `frame_base + SpecialVerts`. Pinned as the invariant that
    makes it true: the highest wedge index must fit within `ModelVerts`, and
    `FrameVerts == ModelVerts + SpecialVerts`. (Getting this wrong renders a shredded spike-ball,
    not an obviously-shifted mesh — see the spike.)"""
    mod = _umesh()
    pkg = _pkg_or_skip(UED22 / "DeusExCharacters.u")
    checked = 0
    for j in mod.mesh_exports(pkg):
        m = mod.parse_mesh(pkg, j)
        if not m.wedges or not m.frame_verts:
            continue
        assert m.frame_verts == m.model_verts + m.special_verts, (
            f"{m.name}: FrameVerts {m.frame_verts} != ModelVerts {m.model_verts} "
            f"+ SpecialVerts {m.special_verts}")
        assert max(w[0] for w in m.wedges) < m.model_verts, (
            f"{m.name}: wedge vertex index exceeds ModelVerts")
        checked += 1
    assert checked > 0


# ------------------------------------------------------- Deus Ex v68 (gitignored install)

@pytest.mark.parametrize("stem", ["DeusExDeco", "DeusExCharacters", "DeusExItems"])
def test_v68_deusex_packages_parse_to_exact_end(stem):
    """The same layout decodes the retail Deus Ex v68 packages, whose vertices are the licensee
    8-byte int16 quads — the generic-UE1 claim (one decoder, both formats)."""
    mod = _umesh()
    pkg = _pkg_or_skip(install_system_root() / f"{stem}.u")
    ok, fails = _parse_all(mod, pkg)
    assert not fails, f"{stem}: {len(fails)} mesh(es) failed to decode: {fails[:3]}"
    assert ok > 0


def test_v68_vertex_stride_is_detected_as_eight_byte():
    mod = _umesh()
    pkg = _pkg_or_skip(install_system_root() / "DeusExDeco.u")
    strides = {mod.parse_mesh(pkg, j).vert_stride for j in mod.mesh_exports(pkg)[:40]}
    assert strides == {8}, f"expected Deus Ex 8-byte verts in a v68 package, got {strides}"


def test_v68_keypad3_matches_umodel_ground_truth():
    """Cross-tool validation carried over from spike 2026-06-27 spike 2: umodel exports `Keypad3`
    as NumVertices=18 / NumPolys=10, which are the mesh's Wedges / Faces."""
    mod = _umesh()
    pkg = _pkg_or_skip(install_system_root() / "DeusExDeco.u")
    j = next(j for j in mod.mesh_exports(pkg) if pkg.names[pkg.exports[j]["nm"]] == "Keypad3")
    m = mod.parse_mesh(pkg, j)
    assert (len(m.wedges), len(m.faces)) == (18, 10)
    assert len(m.verts) == 8 and m.vert_stride == 8


def test_v68_old_frame_verts_mirrors_frame_verts():
    """In the RETAIL v68 packages the `ULodMesh` tail's `OldFrameVerts` equals `FrameVerts` — the
    evidence that identified the field. (It is 0 in the UED22-rebuilt v69 stubs, so this is a
    property of the retail data, not of the format; see `test_lodmesh_tail_is_not_deusex_specific`.)
    """
    mod = _umesh()
    pkg = _pkg_or_skip(install_system_root() / "DeusExDeco.u")
    lods = [mod.parse_mesh(pkg, j) for j in mod.mesh_exports(pkg)
            if pkg.object_class_name(j + 1) == "LodMesh"][:40]
    assert lods
    for m in lods:
        assert m.dx_tail_verts == m.frame_verts, f"{m.name}: {m.dx_tail_verts} != {m.frame_verts}"
