# Native mesh rendering in `level photo --native` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `level photo --native` renders placed `DT_Mesh` actors (decorations, items, weapons,
characters) — currently invisible — using the already-decoded mesh/skin machinery, with no
Rust/FFI change, and switches from a checkerboard-on-missing-ref fallback to a hard error.

**Architecture:** Python resolves each qualifying actor's mesh, world-transforms its frame-0
triangles with a newly-verified placement formula, resolves skins via the existing `class preview`
code path, and emits one `RenderPoly` tuple per triangle into the same list/texture-table
`build_scene` already builds for world polys and movers. The Rust rasterizer (`render.rs`) is
untouched — a mesh triangle is flat, so its UV maps to `RenderPoly`'s existing planar axis
representation via a 2×2 linear solve.

**Tech Stack:** Python 3.12 (`uedcli/`), the existing PyO3 `uedcli_native.render_frame` FFI (unchanged).

**Spec:** `dev/docs/board/to-plan/native-mesh-rendering-in-level-photo-native/spec.md` (read it —
this plan implements it and doesn't restate its rationale). Verified formula reference:
`dev/docs/unrealed/mesh-transform.md`, full derivation `dev/docs/spikes/
2026-09-07-mesh-origin-rotorigin-transform/README.md`.

## Global Constraints

- No `uedcli-native/src/render.rs` or PyO3/FFI changes anywhere in this plan.
- DX-first: build and validate against Deus Ex content; keep all new code substrate-generic (no
  `if deusex`/`if unreal` branches) — `umesh.py` already reads both v68/v69 with one decoder.
- No silent fallback: an unresolvable texture or mesh ref must abort the shot with an error naming
  the actor and the ref — never a placeholder image.
- Movers stay excluded from this path (already rendered separately); sprites stay out of scope.
- Per-actor `Skins[]` override and stock-Unreal/UT99 validation are explicitly OUT of this plan —
  tracked by `per-actor-skins-override-in-native-mesh-render` and
  `validate-native-mesh-render-against-stock` respectively. Don't implement them here.
- Run tests via `bin/test -k <module>` (never bare `pytest`), scoped to what each task touches; run
  the full non-integration suite once before the final commit. `UEDCLI_SKIP_NATIVE=1` is fine for
  every task here (no Rust changes) except none — always skip native rebuilds, they're irrelevant.

---

## File Structure

- **Modify** `uedcli/meshrender.py` — extend `frame_triangles` to also return each triangle's
  `PolyFlags` (currently silently dropped for the `Tris`/plain-`Mesh` case).
- **Create** `uedcli/meshworld.py` — the new mesh-local + actor world-transform math: the verified
  placement formula, the per-triangle UV-affine solve, and an `actor_draw_scale` helper. A LEAF
  module (stdlib + `uedcli.rotation` only), mirroring `texframe.py`'s own "why a leaf" rationale —
  keeps this importable without pulling in `uedcli_native`/`utexture`.
- **Modify** `uedcli/preview_native.py` — `build_scene` gains mesh-actor instancing: resolve each
  `DT_Mesh` actor's mesh + skins, call into `meshworld`, emit `RenderPoly` tuples. `_TextureTable`
  loses its checkerboard fallback.
- **Test**: `uedcli/tests/test_meshworld.py` (new), `uedcli/tests/test_meshrender.py` (extend, or
  create if it doesn't exist — check first), `uedcli/tests/test_preview_native.py` (extend).

---

### Task 1: `frame_triangles` carries per-triangle `PolyFlags`

**Files:**
- Modify: `uedcli/meshrender.py:48-79` (`frame_triangles`)
- Test: `uedcli/tests/test_meshrender.py` (check if this file exists first — `class preview`/
  `resolve_skins`/`frame_triangles` may already have coverage elsewhere, e.g.
  `test_meshfacts.py`/`test_classes.py`; grep before creating a duplicate)

**Interfaces:**
- Produces: `frame_triangles(mesh, frame=0)` now returns
  `list[tuple[v0, v1, v2, uv0, uv1, uv2, material_index, poly_flags]]` — **8-tuples, not 7** (a
  breaking return-shape change; every existing caller must be updated in this same task).

- [ ] **Step 1: Find every existing caller of `frame_triangles`**

```bash
grep -rn "frame_triangles(" uedcli/*.py uedcli/tests/*.py
```
Expected: `meshrender.py`'s own `render_class` (the thumbnail rasterizer) is the only one today.
Note its call site and current tuple-unpacking line for Step 4.

- [ ] **Step 2: Write the failing test**

```python
# uedcli/tests/test_meshrender.py
from uedcli import meshrender


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
```

- [ ] **Step 3: Run it to verify it fails**

```bash
bin/test uedcli/tests/test_meshrender.py -k frame_triangles -v
```
Expected: `test_frame_triangles_plain_mesh_flags_come_from_tri` FAILS (too many/few values to
unpack, or `poly_flags` missing) — `frame_triangles` currently returns 7-tuples. The LodMesh test
may also fail on unpack arity.

- [ ] **Step 4: Implement — extend `frame_triangles` and fix its one caller**

In `uedcli/meshrender.py`, change the two branches of `frame_triangles`:

```python
def frame_triangles(mesh, frame: int = 0):
    """Triangles for one animation frame as
    `(v0, v1, v2, uv0, uv1, uv2, material_index, poly_flags)`.

    A `ULodMesh`'s renderable geometry is in Faces/Wedges (its `Tris` is empty) — Faces index Wedges,
    Wedges index Verts and carry the UV; a plain `UMesh` keeps geometry in `Tris`. `Verts` holds every
    frame back-to-back, so frame `f` starts at `f*FrameVerts`, and each frame begins with
    `SpecialVerts` attachment vertices that are NOT model geometry (a wedge's `iVertex` is relative to
    `frame_base + SpecialVerts`; omitting the shift shreds any mesh with attachments).

    `poly_flags` comes from a DIFFERENT field depending on mesh kind: a LodMesh's
    `Materials[material_index].PolyFlags`, a plain Mesh's own per-triangle `FMeshTri.PolyFlags` —
    they are not interchangeable (`dev/docs/board/.../native-mesh-rendering-in-level-photo-native/
    spec.md`)."""
    base = frame * mesh.frame_verts + mesh.special_verts
    tris = []
    if mesh.faces:
        for (iw, mat) in mesh.faces:
            try:
                w = [mesh.wedges[i] for i in iw]
            except IndexError:
                continue
            vs, uvs = [], []
            for (iv, u, v) in w:
                k = base + iv
                if k >= len(mesh.verts):
                    break
                vs.append(mesh.verts[k])
                uvs.append((u, v))
            if len(vs) == 3:
                flags = mesh.materials[mat][0] if 0 <= mat < len(mesh.materials) else 0
                tris.append((vs[0], vs[1], vs[2], uvs[0], uvs[1], uvs[2], mat, flags))
    else:                                            # plain UMesh: geometry lives in Tris
        for (iv, uv, flags, tex) in mesh.tris:
            vs = [mesh.verts[base + i] for i in iv if base + i < len(mesh.verts)]
            if len(vs) == 3:
                tris.append((vs[0], vs[1], vs[2],
                             (uv[0], uv[1]), (uv[2], uv[3]), (uv[4], uv[5]), tex, flags))
    return tris
```

Then fix `render_class`'s unpacking (the call site found in Step 1) to accept the 8th element —
it's the thumbnail renderer and doesn't need per-triangle flags, so just widen the unpack and
discard it, e.g. `for (v0, v1, v2, uv0, uv1, uv2, mat, _flags) in frame_triangles(mesh):`.

- [ ] **Step 5: Run tests to verify they pass**

```bash
bin/test uedcli/tests/test_meshrender.py -v
```
Expected: PASS, including any pre-existing `render_class`/thumbnail tests (confirms the call-site
fix didn't break it).

- [ ] **Step 6: Commit**

```bash
git add uedcli/meshrender.py uedcli/tests/test_meshrender.py
git commit -m "meshrender: carry per-triangle PolyFlags out of frame_triangles"
```

---

### Task 2: The verified mesh world-transform + `actor_draw_scale`

**Files:**
- Create: `uedcli/meshworld.py`
- Test: `uedcli/tests/test_meshworld.py`

**Interfaces:**
- Consumes: `uedcli.rotation.euler_to_matrix_uu(pitch_uu, yaw_uu, roll_uu)`,
  `uedcli.rotation.actor_matrix(actor)`, `uedcli.rotation.actor_prepivot(actor) -> tuple[Decimal,
  Decimal, Decimal]`, `uedcli.rotation.matmul(A, B)`, `uedcli.rotation.matvec(M, v)`.
- Produces: `mesh_vertex_to_world(v, *, mesh, actor) -> tuple[float, float, float]` — the
  per-vertex transform, called once per mesh vertex. `mesh_actor_linear(mesh, actor) -> list[list
  [float]]` (3×3) — the combined linear map, called ONCE per actor by Task 5 to feed
  `transform.reject_degenerate`/`transform.flip_winding`.

- [ ] **Step 1: Write the failing tests**

Port the RE spike's verified cases directly — do not re-derive them, the spike already pinned them
in `dev/docs/spikes/2026-09-07-mesh-origin-rotorigin-transform/uedcli/tests/
test_mesh_world_transform.py` (8/8 passing there per the spike's own regression suite). Read that
file first; bring its `ComputerPublic`-style non-identity-`RotOrigin` case and its identity-case
control into `uedcli/tests/test_meshworld.py`, adapted to call `meshworld.mesh_vertex_to_world`
(the spike's own harness module name may differ — check `dev/docs/spikes/
2026-09-07-mesh-origin-rotorigin-transform/harness/mesh_world_transform.py` for the exact function
this plan's `meshworld.py` should match, and use it as the reference implementation to port, not a
black box to re-derive from scratch).

At minimum, include:

```python
# uedcli/tests/test_meshworld.py
from uedcli import meshworld


class _FakeActor:
    def __init__(self, *, location=(0, 0, 0), props=()):
        self.location = location
        self.props = list(props)


class _FakeMesh:
    def __init__(self, *, origin=(0.0, 0.0, 0.0), rot_origin=(0, 0, 0), scale=(1.0, 1.0, 1.0)):
        self.origin = origin
        self.rot_origin = rot_origin
        self.scale = scale


def test_identity_everything_is_a_plain_translate():
    actor = _FakeActor(location=(100, 200, 0))
    mesh = _FakeMesh()
    world = meshworld.mesh_vertex_to_world((5, 0, 0), mesh=mesh, actor=actor)
    assert world == (105.0, 200.0, 0.0)


def test_mesh_rot_origin_90_yaw_rotates_in_mesh_local_frame_before_actor_placement():
    # RotOrigin = 90deg yaw (16384 uu); a mesh-local +X vertex should land along actor-local +Y
    # after Ro alone (actor Rotation identity, Location zero) -- this is the ComputerPublic case
    # the spike verified against UMesh::GetFrame.
    actor = _FakeActor(location=(0, 0, 0))
    mesh = _FakeMesh(rot_origin=(0, 16384, 0))
    world = meshworld.mesh_vertex_to_world((10, 0, 0), mesh=mesh, actor=actor)
    assert abs(world[0]) < 1e-6
    assert abs(world[1] - 10.0) < 1e-6

def test_actor_rotation_applies_outside_rot_origin_and_can_cancel_it():
    # CompB from the spike: actor Rotation = -90deg yaw exactly cancels a mesh RotOrigin of +90deg
    # yaw, restoring the mesh-local orientation in world space.
    actor = _FakeActor(location=(0, 0, 0), props=[("Rotation", "(Pitch=0,Yaw=-16384,Roll=0)")])
    mesh = _FakeMesh(rot_origin=(0, 16384, 0))
    world = meshworld.mesh_vertex_to_world((10, 0, 0), mesh=mesh, actor=actor)
    assert abs(world[0] - 10.0) < 1e-6
    assert abs(world[1]) < 1e-6


def test_prepivot_is_unrotated_unlike_the_brush_convention():
    # A rotated actor with PrePivot: PrePivot must be added UNROTATED (architecture.md D8 is the
    # OPPOSITE convention and must NOT be used here).
    actor = _FakeActor(location=(0, 0, 0),
                       props=[("Rotation", "(Pitch=0,Yaw=16384,Roll=0)"),   # +90deg yaw
                              ("PrePivot", "(X=5,Y=0,Z=0)")])
    mesh = _FakeMesh()
    world = meshworld.mesh_vertex_to_world((0, 0, 0), mesh=mesh, actor=actor)
    # PrePivot unrotated: world = Location + PrePivot + R*Ro*Scale*(v - Origin) = (0,0,0)+(5,0,0)+0
    assert abs(world[0] - 5.0) < 1e-6
    assert abs(world[1]) < 1e-6


def test_draw_scale_multiplies_mesh_scale():
    actor = _FakeActor(location=(0, 0, 0), props=[("DrawScale", "2.0")])
    mesh = _FakeMesh(scale=(1.0, 1.0, 1.0))
    world = meshworld.mesh_vertex_to_world((3, 0, 0), mesh=mesh, actor=actor)
    assert abs(world[0] - 6.0) < 1e-6


def test_actor_draw_scale_defaults_to_one():
    assert meshworld.actor_draw_scale(_FakeActor()) == 1.0


def test_actor_draw_scale_reads_prop():
    actor = _FakeActor(props=[("DrawScale", "2.5")])
    assert meshworld.actor_draw_scale(actor) == 2.5


def test_mesh_actor_linear_negative_draw_scale_flips_winding():
    from uedcli.transform import flip_winding
    actor = _FakeActor(props=[("DrawScale", "-1.0")])
    mesh = _FakeMesh()
    L = meshworld.mesh_actor_linear(mesh, actor)
    assert flip_winding(L) is True


def test_mesh_actor_linear_identity_does_not_flip_or_reject():
    from uedcli.transform import flip_winding, reject_degenerate
    actor = _FakeActor()
    mesh = _FakeMesh()
    L = meshworld.mesh_actor_linear(mesh, actor)
    assert flip_winding(L) is False
    reject_degenerate(L, "TestActor")  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
bin/test uedcli/tests/test_meshworld.py -v
```
Expected: FAIL — `uedcli.meshworld` doesn't exist yet.

- [ ] **Step 3: Implement `uedcli/meshworld.py`**

```python
"""Mesh actor world-space vertex placement: `world = Location + PrePivot +
R * Ro * diag(Scale * DrawScale) * (v - Origin)` — verified ✅ source against `UMesh::GetFrame`,
`dev/docs/unrealed/mesh-transform.md` (full derivation: `dev/docs/spikes/
2026-09-07-mesh-origin-rotorigin-transform/`). NOT the brush/CSG convention (`architecture.md`
"D8": `Location + R*(v-PrePivot)`, PrePivot INSIDE the rotation) -- a different call site, a
different PrePivot convention, for the same actor field.

A LEAF: stdlib + `uedcli.rotation` only (mirrors `texframe.py`'s own leaf rationale)."""
from __future__ import annotations

from decimal import Decimal

from .rotation import actor_matrix, actor_prepivot, euler_to_matrix_uu, matmul, matvec


def actor_draw_scale(actor) -> float:
    """The actor's `DrawScale` prop as a float, 1.0 if absent/unparseable (UE1/Deus Ex has no
    separate `DrawScale3D` -- one uniform scalar)."""
    for k, v in actor.props:
        if k == "DrawScale":
            try:
                return float(v)
            except ValueError:
                return 1.0
    return 1.0


def mesh_vertex_to_world(v, *, mesh, actor) -> tuple[float, float, float]:
    """One mesh-local vertex `v` (raw `FMeshVert`, mesh-local units) -> world space, per the
    formula above."""
    origin = mesh.origin
    scale = mesh.scale
    draw_scale = actor_draw_scale(actor)

    # v - Origin, then per-axis Scale*DrawScale
    w = ((float(v[0]) - float(origin[0])) * float(scale[0]) * draw_scale,
         (float(v[1]) - float(origin[1])) * float(scale[1]) * draw_scale,
         (float(v[2]) - float(origin[2])) * float(scale[2]) * draw_scale)

    Ro = euler_to_matrix_uu(*mesh.rot_origin)   # mesh's own RotOrigin; always applied (no identity
                                                  # fast-path skip -- rot_origin is rarely (0,0,0)
                                                  # and euler_to_matrix_uu(0,0,0) is cheap/exact anyway)
    w = matvec(Ro, w)

    R = actor_matrix(actor)                      # None (identity) or the actor's Rotation matrix
    if R is not None:
        w = matvec(R, w)

    loc = tuple(float(c) for c in (actor.location or (0, 0, 0)))
    pp = actor_prepivot(actor)                    # Decimal triple; ADDED UNROTATED (see module doc)
    return (loc[0] + float(pp[0]) + w[0],
            loc[1] + float(pp[1]) + w[1],
            loc[2] + float(pp[2]) + w[2])


def mesh_actor_linear(mesh, actor):
    """The combined mesh-local + actor linear map `L = R * Ro * diag(Scale*DrawScale)`
    (translation excluded) for ONE actor+mesh pair. NOT used by `mesh_vertex_to_world` above
    (which recomputes `R`/`Ro` itself per vertex — this is a separate, cheap, once-per-actor
    call, not a shared hot path). Its only job: feed `transform.reject_degenerate`/
    `transform.flip_winding`, the SAME checks `_mover_actor_world_polys`
    (`preview_native.py`) already runs for movers — required by the spec ("Still worth reusing
    from the mover path... apply them to the combined mesh-local+actor linear map"). A mesh with
    a negative `Scale` axis or negative `DrawScale` needs the same reject/flip handling a
    mirrored mover already gets, or it renders inside-out (culled backwards by `render.rs`'s
    winding-based backface cull)."""
    draw_scale = actor_draw_scale(actor)
    sx, sy, sz = (float(c) * draw_scale for c in mesh.scale)
    S = [[sx, 0.0, 0.0], [0.0, sy, 0.0], [0.0, 0.0, sz]]      # diag(Scale*DrawScale) — built by
                                                                # hand, not `transform.fscale_matrix`
                                                                # (that helper takes an `FScale`
                                                                # object with sheer support meshes
                                                                # don't have; a plain diagonal is
                                                                # simpler and correct here)
    Ro = euler_to_matrix_uu(*mesh.rot_origin)
    L = matmul(Ro, S)
    R = actor_matrix(actor)
    if R is not None:
        L = matmul(R, L)
    return L
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
bin/test uedcli/tests/test_meshworld.py -v
```
Expected: PASS, all cases including the ported spike cases.

- [ ] **Step 5: Cross-check against the spike's own regression suite**

```bash
bin/test dev/docs/spikes/2026-09-07-mesh-origin-rotorigin-transform/../../../uedcli/tests/test_mesh_world_transform.py -v
```
(Adjust the path per whatever the spike actually committed — see spike README "Paths".) Expected:
still PASS — confirms `meshworld.py` didn't silently diverge from the spike's own pinned formula
during the port.

- [ ] **Step 6: Commit**

```bash
git add uedcli/meshworld.py uedcli/tests/test_meshworld.py
git commit -m "Add mesh_vertex_to_world: the RE-verified Mesh/LodMesh placement formula"
```

---

### Task 3: Per-triangle UV-affine solve

**Files:**
- Modify: `uedcli/meshworld.py`
- Test: `uedcli/tests/test_meshworld.py`

**Interfaces:**
- Consumes: nothing new (pure vector math).
- Produces: `solve_uv_frame(v0, v1, v2, uv0, uv1, uv2) -> tuple[base, axis_u, axis_v, pan] | None`
  — `None` for a degenerate (collinear/zero-area) triangle. `base`/`axis_u`/`axis_v` are
  `tuple[float,float,float]`, `pan` is `tuple[float,float]`. `uv0`/`uv1`/`uv2` are already in
  TEXEL units (byte-to-texel conversion happens in the caller, Task 5 — this function doesn't know
  about textures at all).

**Math** (state this in the docstring, it's non-obvious): choose `base = v0`, `pan = uv0`. Let
`e1 = v1-v0`, `e2 = v2-v0` (in-plane edges) and `d1 = uv1-uv0`, `d2 = uv2-uv0` (their target UV
deltas, per U and V independently). For each of U and V, solve the 2×2 system
`[[e1.e1, e1.e2], [e1.e2, e2.e2]] · [alpha, beta] = [d, d2]` (the Gram matrix of the two edges) via
Cramer's rule, giving `axis = alpha*e1 + beta*e2`. The determinant `e1.e1*e2.e2 - (e1.e2)^2` is
(twice the triangle's area)² — zero exactly when the triangle is degenerate, which is the `None`
return trigger. `render.rs` computes UV as `dot(p - uv_base, axis) + pan` for any world point `p`;
by construction this exactly reproduces `uv0`/`uv1`/`uv2` at `v0`/`v1`/`v2`, and (since `p`'s
in-plane component is what's tested against) everywhere else on the triangle's plane too.

- [ ] **Step 1: Write the failing test**

```python
def test_solve_uv_frame_reproduces_target_uv_at_all_three_vertices():
    v0, v1, v2 = (0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 10.0, 0.0)
    uv0, uv1, uv2 = (0.0, 0.0), (64.0, 0.0), (0.0, 64.0)
    frame = meshworld.solve_uv_frame(v0, v1, v2, uv0, uv1, uv2)
    assert frame is not None
    base, axis_u, axis_v, pan = frame

    def uv_at(p):
        rel = tuple(p[i] - base[i] for i in range(3))
        u = sum(rel[i] * axis_u[i] for i in range(3)) + pan[0]
        v = sum(rel[i] * axis_v[i] for i in range(3)) + pan[1]
        return (u, v)

    for p, expected in ((v0, uv0), (v1, uv1), (v2, uv2)):
        got = uv_at(p)
        assert abs(got[0] - expected[0]) < 1e-4
        assert abs(got[1] - expected[1]) < 1e-4


def test_solve_uv_frame_reproduces_uv_at_an_interior_point_too():
    v0, v1, v2 = (0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 10.0, 0.0)
    uv0, uv1, uv2 = (0.0, 0.0), (64.0, 0.0), (0.0, 64.0)
    base, axis_u, axis_v, pan = meshworld.solve_uv_frame(v0, v1, v2, uv0, uv1, uv2)
    midpoint = (5.0, 5.0, 0.0)   # not on the triangle, but still on its PLANE -- the frame must
                                  # hold everywhere on the plane, not just at the 3 vertices
    rel = tuple(midpoint[i] - base[i] for i in range(3))
    u = sum(rel[i] * axis_u[i] for i in range(3)) + pan[0]
    v = sum(rel[i] * axis_v[i] for i in range(3)) + pan[1]
    assert abs(u - 32.0) < 1e-4
    assert abs(v - 32.0) < 1e-4


def test_solve_uv_frame_degenerate_triangle_returns_none():
    # v2 collinear with v0/v1 -> zero area
    v0, v1, v2 = (0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (20.0, 0.0, 0.0)
    assert meshworld.solve_uv_frame(v0, v1, v2, (0, 0), (1, 0), (2, 0)) is None
```

- [ ] **Step 2: Run to verify it fails**

```bash
bin/test uedcli/tests/test_meshworld.py -k solve_uv_frame -v
```
Expected: FAIL — `solve_uv_frame` doesn't exist.

- [ ] **Step 3: Implement**

Append to `uedcli/meshworld.py`:

```python
def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add_scaled(base, e1, e2, alpha, beta):
    return tuple(base[i] + alpha * e1[i] + beta * e2[i] for i in range(3))


def solve_uv_frame(v0, v1, v2, uv0, uv1, uv2):
    """The unique (up to out-of-plane axis component, which never affects an in-plane point) affine
    UV frame `(base, axis_u, axis_v, pan)` such that `dot(p-base, axis) + pan` reproduces the given
    UV at each vertex, for any `p` on the triangle's plane -- see Task 3 docstring in the plan for
    the derivation. Returns `None` for a degenerate (zero-area) triangle."""
    e1 = _sub(v1, v0)
    e2 = _sub(v2, v0)
    e1e1, e1e2, e2e2 = _dot(e1, e1), _dot(e1, e2), _dot(e2, e2)
    det = e1e1 * e2e2 - e1e2 * e1e2
    if abs(det) < 1e-9:
        return None

    def axis_for(d1, d2):
        alpha = (d1 * e2e2 - d2 * e1e2) / det
        beta = (d2 * e1e1 - d1 * e1e2) / det
        return (alpha * e1[0] + beta * e2[0],
                alpha * e1[1] + beta * e2[1],
                alpha * e1[2] + beta * e2[2])

    axis_u = axis_for(uv1[0] - uv0[0], uv2[0] - uv0[0])
    axis_v = axis_for(uv1[1] - uv0[1], uv2[1] - uv0[1])
    return v0, axis_u, axis_v, (uv0[0], uv0[1])
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
bin/test uedcli/tests/test_meshworld.py -v
```
Expected: all PASS (Task 2 + Task 3 tests).

- [ ] **Step 5: Commit**

```bash
git add uedcli/meshworld.py uedcli/tests/test_meshworld.py
git commit -m "Add solve_uv_frame: exact per-triangle affine UV fit for RenderPoly"
```

---

### Task 4: Strict error handling — remove the checkerboard fallback

**Files:**
- Modify: `uedcli/preview_native.py:182-234` (`_checkerboard`, `_TextureTable.index_for`)
- Modify: `uedcli/tests/test_preview_native.py:191`, `:210` (the two existing checkerboard-asserting
  tests — read them first, they need to become error-asserting tests, not be deleted outright,
  unless they'd be exact duplicates of a new test)

**Interfaces:**
- Produces: `_TextureTable.index_for(ref)` now raises `NativePreviewError` (already imported/used
  elsewhere in this file) instead of returning a checkerboard index, for BOTH an unresolvable ref
  (no package/name) and an undecodable one.

- [ ] **Step 1: Read the two existing tests to know exactly what to replace**

```bash
sed -n '180,225p' uedcli/tests/test_preview_native.py
```
Note their exact setup (what makes a ref "unresolvable" in their fixtures) so the replacement
tests exercise the identical scenario, just asserting the new behavior.

- [ ] **Step 2: Write the failing (replacement) tests**

Adapt the two existing tests in place — same fixture/setup, new assertion. Sketch (fill in the
REAL fixture setup you read in Step 1; this is the shape, not literal copy-paste):

```python
def test_unresolvable_texture_ref_raises_not_checkerboard():
    table = preview_native._TextureTable(<the same resolver fixture the old test used>)
    with pytest.raises(preview_native.NativePreviewError, match=r"<the offending ref>"):
        table.index_for("<the same unresolvable ref the old test used>")


def test_undecodable_texture_ref_raises_not_checkerboard():
    # same shape, for the "present but fails to decode" case if the old tests distinguished it
    ...
```

- [ ] **Step 3: Run to verify they fail**

```bash
bin/test uedcli/tests/test_preview_native.py -k texture -v
```
Expected: FAIL (still returns a checkerboard index / raises nothing).

- [ ] **Step 4: Implement — delete `_checkerboard`, make `index_for` raise**

In `uedcli/preview_native.py`, delete the `_checkerboard()` function entirely (lines ~182-191) and
its `_checker_index` bookkeeping in `_TextureTable.__init__`, then replace the fallback branch in
`index_for`:

```python
    def index_for(self, ref: str | None) -> int:
        if not ref:
            return -1                                    # no texture set → flat grey
        key = ref.casefold()
        if key in self._by_ref:
            return self._by_ref[key]
        got = self._resolver.resolve(ref)
        if isinstance(got, TextureError):
            raise NativePreviewError(
                f"texture {ref!r} did not decode [{got.case}]: {got.detail}")
        idx = len(self.table)
        self.table.append((got.width, got.height, got.rgb, got.mask))
        self.bmasked.append(bool(got.b_masked))
        self._by_ref[key] = idx
        return idx
```

Remove the now-dead `self._checker_index = None` line from `__init__` too. Grep for any other
reference to `_checkerboard`/`_checker_index`/`_CHECKER_SIZE`/`_CHECKER_CELL` in the file and
remove them (the constants near the top of the textures section) — dead code, not kept around.

- [ ] **Step 5: Run tests to verify they pass**

```bash
bin/test uedcli/tests/test_preview_native.py -v
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add uedcli/preview_native.py uedcli/tests/test_preview_native.py
git commit -m "preview_native: error on an unresolvable texture ref instead of a checkerboard"
```

---

### Task 5: Wire mesh actors into `build_scene`

This is the integration task — everything from Tasks 1-4 gets called here. Read
`uedcli/cli/commands/classes.py`'s `_run_preview` (lines ~187-219) FIRST as the reference for how
this codebase already resolves a class's `DT_Mesh`/default `Mesh`/skins — this task follows the
same pattern at the actor level, it doesn't invent a new one.

**Files:**
- Modify: `uedcli/preview_native.py` (`build_scene`, plus a new `_mesh_actor_polys` helper
  alongside `_mover_world_polys`)
- Test: `uedcli/tests/test_preview_native.py`

**Interfaces:**
- Consumes: `meshworld.mesh_vertex_to_world`, `meshworld.mesh_actor_linear`,
  `meshworld.solve_uv_frame` (Tasks 2-3), `meshrender.frame_triangles` (Task 1, 8-tuple),
  `meshrender.resolve_skins`, `meshfacts.decode_mesh`, `meshfacts.parse_mesh_ref`,
  `uprops.resolve_class_defaults(fqcn, *, resolver)` (`uedcli/uprops/values.py:508` — NOT
  `uedcli.cli.resources.class_defaults`, see Step 3), `transform.flip_winding`,
  `transform.reject_degenerate`, `transform.DegenerateTransformError`, `_TextureTable.index_for`
  (raises now, per Task 4).
- Produces: `build_scene` includes mesh-actor triangles in its returned `polys` list, using the
  same `(verts_flat, uv_base, uv_axis_u, uv_axis_v, pan, tex_index, masked, poly_flags)` shape
  every other poly source already uses.

**Note on `actor.cls`**: the `Actor` dataclass (`uedcli/model.py`) has NO `class_name` field — the
real field is `actor.cls` (confirmed usage: `classindex.py`, `movers.py`, `cli/commands/mover.py`).
Every snippet below uses `actor.cls` — don't reintroduce `class_name`.

- [ ] **Step 1: Write the failing integration test**

This needs a level fixture with at least one `DT_Mesh` actor and a resolvable class + mesh package
— check `uedcli/tests/test_preview_native.py`'s existing fixtures for how a minimal level/project
with a resolvable class is already built for other tests in this file (there should be a pattern
used for the mover tests) and follow it, pointing at a real mesh class from the committed test
packages (grep `uedcli/tests/fixtures/` for an existing `.u` with a `DT_Mesh` class already used by
`test_classes.py`/`test_meshfacts.py` — reuse the SAME class those tests already use, don't
introduce a new fixture package).

```python
def test_build_scene_includes_a_dt_mesh_actor():
    # Arrange: a level with ONLY the mesh actor (no brushes/movers -- world CSG needs at least one
    # brush actor per build_scene's own "nothing to render" check, so include the SMALLEST brush
    # this file's existing fixtures use, but no mover), so mesh triangles aren't ambiguous against
    # a baseline of other textured polys. Reuse the known DT_Mesh class from
    # uedcli/tests/test_classes.py's `class preview` tests (same package/fixture).
    level_without_mesh, index, search_files = <the same brush-only fixture with NO mesh actor>
    baseline_polys, _ = preview_native.build_scene(level_without_mesh, search_files, index)

    level_with_mesh = <the same fixture PLUS one actor of the known DT_Mesh class>
    polys, textures = preview_native.build_scene(level_with_mesh, search_files, index)

    # Exactly the mesh actor's triangles were added on top of the baseline -- a real proof, not
    # just "some poly has a texture" (which a baseline textured brush poly would also satisfy).
    assert len(polys) > len(baseline_polys)
    new_polys = polys[len(baseline_polys):] if polys[:len(baseline_polys)] == baseline_polys \
        else [p for p in polys if p not in baseline_polys]
    for verts_flat, *_ in new_polys:
        assert len(verts_flat) == 9   # exactly 3 verts * 3 floats -- one mesh triangle per RenderPoly
```

Adjust the assertion once you know the real fixture shape from Step 1's investigation — the "no
placeholder" rule applies to the FINAL test you commit, this sketch is deliberately marked as
needing the real class/package name filled in from the codebase, which the step above tells you
how to find.

- [ ] **Step 2: Run to verify it fails**

```bash
bin/test uedcli/tests/test_preview_native.py -k dt_mesh -v
```
Expected: FAIL — no mesh triangles are emitted yet (0 non-`-1` tex_index polys, or the actor is
silently skipped).

- [ ] **Step 3: Implement `_mesh_actor_polys` and wire it into `build_scene`**

Add to `uedcli/preview_native.py` (near `_mover_world_polys`):

```python
def _mesh_actor_polys(actor, index) -> tuple[list, dict, object]:
    """One DT_Mesh actor's frame-0 triangles (mesh-local, NOT yet world-transformed -- the caller
    does that after computing the actor's winding/degenerate check once) plus its resolved skins
    and its decoded mesh: `(triangles, skins, mesh)` where `triangles` is `frame_triangles(mesh)`'s
    own 8-tuple list, `skins` is `{material_index: (w, h, rgb)}`, and `mesh` is the decoded
    `umesh.Mesh` the caller needs for `mesh_vertex_to_world`/`mesh_actor_linear`. Returns
    `([], {}, None)` for a non-DT_Mesh actor or one
    with no resolvable Mesh (not an error -- matches `class preview`'s own "not every actor has a
    mesh" disposition, `classes.py::_run_preview`). Converts `meshfacts.MeshFactError`/
    `meshrender.PreviewError` to `NativePreviewError` at this boundary -- matching how
    `classes.py::_run_preview` converts the SAME two exceptions to `CommandError` locally, and how
    `level.py`'s `--native` call site only ever catches `NativePreviewError` (no dispatch.py change
    needed, unlike an earlier draft of this plan)."""
    from . import meshfacts, meshrender, meshworld
    from .uprops import resolve_class_defaults

    defaults = resolve_class_defaults(actor.cls, resolver=index.resolver())
    if defaults.get(("drawtype", 0)) != "DT_Mesh":
        return [], {}, None
    props = dict(actor.props)
    mesh_prop = props.get("Mesh") or defaults.get(("mesh", 0))
    ref = meshfacts.parse_mesh_ref(mesh_prop)
    if ref is None:
        raise NativePreviewError(
            f"actor {actor.name}: DrawType is DT_Mesh but Mesh ({mesh_prop!r}) is unresolvable")
    try:
        _display, mesh, pkg = meshfacts.decode_mesh(ref, class_fqcn=actor.cls,
                                                     resolver=index.resolver())
        skins = meshrender.resolve_skins(mesh, pkg, defaults, index.package_paths(),
                                         class_fqcn=actor.cls)
    except meshfacts.MeshFactError as e:
        raise NativePreviewError(str(e)) from e
    except meshrender.PreviewError as e:
        raise NativePreviewError(str(e)) from e
    return meshrender.frame_triangles(mesh), skins, mesh
```

Then in `build_scene`, after the existing mover loop (`for world_verts, actor, poly in
_mover_world_polys(...)`), add:

```python
    from .transform import DegenerateTransformError, flip_winding, reject_degenerate
    from . import meshworld

    for actor in level.actors.values():
        if actor.brush is not None:
            continue                                     # brushes/movers handled above
        tris, skins, mesh = _mesh_actor_polys(actor, index)
        if not tris:
            continue
        L = meshworld.mesh_actor_linear(mesh, actor)
        try:
            reject_degenerate(L, actor.name)
        except DegenerateTransformError as e:
            raise NativePreviewError(str(e)) from e
        flip = flip_winding(L)

        for (v0, v1, v2, uv0, uv1, uv2, material_index, poly_flags) in tris:
            if poly_flags & PF_INVISIBLE:
                continue                                  # dropped Python-side, matches add_poly
            if flip:
                v0, v2 = v2, v0
                uv0, uv2 = uv2, uv0
            w0 = meshworld.mesh_vertex_to_world(v0, mesh=mesh, actor=actor)
            w1 = meshworld.mesh_vertex_to_world(v1, mesh=mesh, actor=actor)
            w2 = meshworld.mesh_vertex_to_world(v2, mesh=mesh, actor=actor)
            skin = skins.get(material_index)
            if skin is None:
                raise NativePreviewError(
                    f"actor {actor.name}: material {material_index} has no resolvable skin")
            tw, th, rgb = skin
            # Dedup key is (mesh.name, material_index), NOT (actor.name, material_index) -- many
            # placed instances of the same decoration/crate share one texture-table slot, matching
            # `_TextureTable.index_for`'s own content-identity dedup intent for world/mover polys.
            tex_index = textures.index_for_decoded(mesh.name, material_index, tw, th, rgb)
            u0 = (uv0[0] * tw / 256.0, uv0[1] * th / 256.0)
            u1 = (uv1[0] * tw / 256.0, uv1[1] * th / 256.0)
            u2 = (uv2[0] * tw / 256.0, uv2[1] * th / 256.0)
            frame = meshworld.solve_uv_frame(w0, w1, w2, u0, u1, u2)
            if frame is None:
                continue                                  # degenerate triangle, skip (matches
                                                            # render.rs's own zero-area poly skip)
            base, axis_u, axis_v, pan = frame
            masked = bool(poly_flags & PF_MASKED)          # mesh skins carry no bMasked signal
                                                            # (resolve_skins drops it) -- a
                                                            # bMasked-but-unflagged mesh skin renders
                                                            # opaque; known gap, not fixed here, see
                                                            # spec's follow-ups
            verts_flat = [c for v in (w0, w1, w2) for c in (float(v[0]), float(v[1]), float(v[2]))]
            masked = bool(poly_flags & PF_MASKED) or textures.is_bmasked(tex_index)
            polys.append((verts_flat, list(base), list(axis_u), list(axis_v), list(pan),
                         tex_index, masked, poly_flags))
```

This calls a NEW `_TextureTable.index_for_decoded(mesh_name, material_index, w, h, rgb)` method —
`index_for` only knows how to resolve a texture REF (a name string) through the resolver, but a
mesh skin arrives already-decoded (`resolve_skins` did that). Add it alongside `index_for`:

```python
    def index_for_decoded(self, mesh_name: str, material_index: int, w: int, h: int,
                          rgb: bytes) -> int:
        """Register an already-decoded texture (a mesh skin `resolve_skins` resolved) and return
        its table index -- deduped by (mesh_name, material_index), NOT by which ACTOR triggered
        the resolve, so many placed instances of the same decoration/crate share one table entry
        instead of one each. `mask` is synthesized all-opaque (mesh skins don't carry a separate
        mask array the way surface textures do via `utexture`'s `bMasked`; PF_Masked on a mesh
        triangle still cuts index-0 via the rasterizer's own per-texel mask check, which needs
        SOME mask array -- all-opaque is the correct one since `resolve_skins`'s decode path
        doesn't report per-texel transparency)."""
        cache_key = (mesh_name, material_index)
        if cache_key in self._by_decoded:
            return self._by_decoded[cache_key]
        idx = len(self.table)
        self.table.append((w, h, rgb, b"\x01" * (w * h)))
        self.bmasked.append(False)
        self._by_decoded[cache_key] = idx
        return idx
```

Add `self._by_decoded: dict = {}` to `_TextureTable.__init__`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
bin/test uedcli/tests/test_preview_native.py -v
```
Expected: PASS, including the new `test_build_scene_includes_a_dt_mesh_actor`.

- [ ] **Step 5: Add the spec-required "unresolvable mesh ref" regression test**

The spec's Testing section requires both "an unresolvable texture ref and an unresolvable mesh ref
each abort the shot with an error naming the ref" — Task 4 covered the texture half; this closes
the mesh half, exercising `_mesh_actor_polys`'s `ref is None` branch:

```python
def test_build_scene_unresolvable_mesh_ref_raises_naming_the_actor():
    # Arrange: same DT_Mesh-class level fixture as test_build_scene_includes_a_dt_mesh_actor
    # (Step 1), but the actor's own Mesh= override points at a name that doesn't resolve to
    # anything in the resolver's search path -- construct this the same way that test's fixture
    # sets a KNOWN-GOOD Mesh, just with a garbage ref string instead.
    level, index, search_files = <same fixture shape as Step 1, actor Mesh="NoSuchPackage.Bogus">
    with pytest.raises(preview_native.NativePreviewError, match="NoSuchPackage.Bogus"):
        preview_native.build_scene(level, search_files, index)
```

Run it, confirm it PASSES already (the `ref is None`... note: `parse_mesh_ref` on a syntactically-
plausible-but-unresolvable ref may not return `None` — it may return a ref string that then fails
inside `meshfacts.decode_mesh` instead, raising `MeshFactError`, which `_mesh_actor_polys` already
converts to `NativePreviewError`. Check `meshfacts.parse_mesh_ref`'s actual contract before writing
the `pytest.raises(...)` assertion — the exact exception path (the `ref is None` branch vs. the
`except meshfacts.MeshFactError` branch) depends on what a garbage-but-well-formed ref does there,
and this test should exercise whichever path a REALISTIC "actor references a mesh that isn't on
the search path" scenario actually takes, not necessarily the syntactically-empty case).

```bash
git add uedcli/tests/test_preview_native.py
git commit -m "preview_native: regression test for an unresolvable mesh ref"
```

- [ ] **Step 6: Run the full non-integration suite once**

```bash
mkdir -p _scratch/pttmp && TMPDIR=$PWD/_scratch/pttmp UEDCLI_SKIP_NATIVE=1 bin/test \
  -p no:cacheprovider -o cache_dir=_scratch/pttmp/pc -q
```
Expected: PASS (pre-existing reds `test_doc_links`/`test_native_lit_room_ships_light_export_refs`
excepted, per `NATIVE-MATERIALIZE.md`'s testing note).

- [ ] **Step 7: Commit**

```bash
git add uedcli/preview_native.py uedcli/tests/test_preview_native.py
git commit -m "level photo --native: render DT_Mesh actors (decorations, items, weapons, characters)"
```

---

### Task 6: Visual verification against DX content

Not unit-testable in the usual sense — this is the spec's "Visual" bar: render real DX levels with
decorations/items/weapons/a character via `--native`, compare against `--game`.

- [ ] **Step 1: Find or build a DX test level with mesh actors**

Reuse the spike's own harness as a starting point — `dev/docs/spikes/
2026-09-07-mesh-origin-rotorigin-transform/harness/build_test_level.sh` already builds a small
level with `DeusEx.ComputerPublic`/`CrateUnbreakableMed` actors. Extend it (or write a sibling
script) to also place at least one weapon/item actor and one character (`Pawn`-derived) class, if a
resolvable one exists in the committed test package set — check `uedcli/tests/fixtures/` and
`uned/UED22/` for what DX classes/packages are actually available before picking one.

- [ ] **Step 2: Render both ways and compare**

```bash
bin/uedcli --project <the test project> level photo --native --out-dir _scratch/mesh-verify-native \
  --map <built .dx> <shot tokens>
bin/uedcli --project <the test project> level photo --game --out-dir _scratch/mesh-verify-game \
  --map <built .dx> <same shot tokens>
```
Visually compare the two directories' PNGs (per this session's own "quiet bash, judge from
rendered images" convention — don't dump pixel diffs to the terminal). Confirm: each mesh actor
appears, in the right place, at roughly the right scale/orientation, with a recognizable skin (not
a wrong/blank texture). This is a judgment call, not a byte-parity check (`--native` is a draft
tier).

- [ ] **Step 3: If everything looks right, retry the spike's own live-render cross-check**

The spike (`dev/docs/spikes/2026-09-07-mesh-origin-rotorigin-transform/`) left its own live-render
verification incomplete (shared-sandbox contention, not a formula problem — see its README). Now
that mesh rendering actually exists in `--native`, re-run
`harness/build_test_level.sh` once more if the sandbox isn't contended, and if it completes,
update that spike's README "Live-render verification" section from INCONCLUSIVE to CONFIRMED (or
report back honestly if it still doesn't complete — don't force it).

- [ ] **Step 4: Report findings, no commit needed for this task alone**

If Step 2 finds a real placement/skin bug, that's a new finding — root-cause and fix it (likely
back in Task 2/3/5's code), don't just note it and move on, per this project's "keep going" norm
for this kind of build-verification work.

---

## Self-Review Notes (for whoever executes this plan)

This plan went through two review passes (spec review, then a full plan review by an independent
subagent) before being handed to execution. The plan review's findings are already folded in:
`actor.cls` (not `class_name`), `uprops.resolve_class_defaults(actor.cls, resolver=index.resolver())`
directly (not `cli.resources.class_defaults`, which would have re-resolved the wrong project and
introduced a core→cli dependency this codebase doesn't otherwise have), the winding-flip/
degenerate-reject wiring the spec required and an earlier draft missed, dropping the unnecessary
`cli/dispatch.py` change in favor of local exception conversion (matching the actual precedent,
`classes.py::_run_preview`), the `PF_INVISIBLE` check, the `mesh.name`-keyed texture dedup, and the
missing "unresolvable mesh ref" regression test. Two items the review flagged were left as
documented gaps rather than fixed (both are pre-existing/inherited, not introduced by this plan,
and fixing either is real additional scope):

- `resolve_skins` doesn't carry `bMasked` for mesh skins, so `index_for_decoded` always synthesizes
  an all-opaque mask — a `bMasked` mesh skin whose triangle lacks the `PF_Masked` surface flag
  renders opaque instead of alpha-tested. Plausible on DX foliage/grate decorations. If this shows
  up as a visible bug in Task 6's visual verification, it's real work, not a false positive — file
  a board item rather than silently living with it unflagged.
- `actor_draw_scale` defaults to 1.0 when the prop is absent, without checking whether any DX class
  itself defaults `DrawScale` off 1.0 (unverified either way). If Task 6 finds a consistently
  wrong-scaled mesh class, check this first.

Per-actor `Skins[]` override and stock-Unreal/UT99 validation are deliberately NOT tasks here — see
Global Constraints. Don't add them without going back to those separate board items.
