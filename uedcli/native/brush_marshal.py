"""Brush -> CSG `BrushTuple` marshalling for `uedcli_native.build_geometry`.

Turns a trunk brush actor into the flat tuple the Rust CSG core takes, and decides
which brushes are carved into the world BSP (`_in_world_csg`). Shared by `brushcsg`
(the `brush intersect`/`deintersect` verbs) and `preview_native` (`level photo --native`).
"""
from __future__ import annotations

from ..movers import is_mover

# ECsgOper ordinals == the Rust `build_geometry` oper codes (1=Add..4=Deintersect).
_CSG_OPER = {"CSG_Active": 0, "CSG_Add": 1, "CSG_Subtract": 2,
             "CSG_Intersect": 3, "CSG_Deintersect": 4}
_IDENTITY_ROT = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


class BuildError(Exception):
    """A native-build failure carrying the offending value (surfaces as a clean exit-2)."""


def _in_world_csg(actor, index) -> bool:
    """Does this actor's brush get carved into the world BSP (fed to the CSG core)?

    A static `Brush` actor does; a **Mover** (`Engine.Mover` / a subclass like `DeusExMover`,
    `ElevatorMover`) does NOT.  A Mover is a DYNAMIC actor (a door, elevator, lift): UnrealEd
    keeps its brush as the Mover's OWN private Model and never CSGs it into the world — so the
    Mover is still emitted as a level actor (see `_trunk_to_actorspecs`, which is independent of
    this predicate), it is only kept OUT of the world-CSG input here.  Feeding movers into world
    CSG fills their doorways/openings solid and shatters empty-space connectivity into spurious
    zones and disconnected leaf-blobs (measured on HK/WanChai-Market: excluding the 23 movers
    takes leaf-blobs 21→2 and zones 24→5, matching the editor's own build).

    Uses the shared substrate-generic `movers.is_mover` predicate (the same one doctor + dispatch
    use — no per-substrate class list).  Since 2026-07-25 that predicate is SCHEMA-AWARE — it walks
    the class hierarchy to `Engine.Mover` through the `classindex.ClassIndex` passed as `index` — so
    a Mover subclass whose class name does not end in "Mover" (`DeusEx.BreakableGlass`,
    `CaroneElevatorSet.CEDoor`) is now caught too; the old bare-name suffix test let those leak into
    world CSG (measured immaterial to HK zones/leaf-blobs, but wrong).  `index` must resolve the
    game's code `.u` packages, else `is_mover` raises rather than reporting every mover as static."""
    if actor.brush is None:
        return False
    if not actor.cls:                                    # classless brush ⇒ default Brush ⇒ world CSG
        return True
    return not is_mover(actor, index)


def _parse_vec3(raw: str | None, default=(0.0, 0.0, 0.0)) -> tuple:
    if not raw:
        return default
    from .props import _parse_struct_fields, _f
    f = _parse_struct_fields(raw)
    d = {k: (default[i] if k not in f else 0.0) for i, k in enumerate("XYZ")}
    return tuple(_f(f.get(ax, ""), d[ax]) for ax in "XYZ")


def _build_brush_input(name, actor):
    """One CSG BrushTuple for `uedcli_native.build_geometry` from a trunk brush actor.

    Applies the brush's `Rotation` FRotator as the world transform's rotation matrix `R`: the Rust
    `FPoly::transform` computes `world = Location + R·(v − PrePivot)`, so `R` is built from the URU
    Pitch/Yaw/Roll fields via `rotation.euler_to_matrix_uu` — the editor-verified UE1 convention
    (yaw = textbook Rz; pitch/roll sin-flipped; compose Rz·Ry·Rx; GMath sine table, not libm — see
    dev/docs/spikes/2026-06-19-frotator-convention.md).  A low-bit-only / absent Rotation renders
    identity (spike: GMath truncates the low 2 bits) and passes `_IDENTITY_ROT` unchanged.

    SCALE (`MainScale`/`PostScale`) — §87 §9 (`spikes/2026-07-15-native-materialize/`), the root of
    native over-solidification on real DX levels.  A scaled-up SUBTRACT brush that builds at UNIT
    size carves a tiny hole instead of the full room, so the room interior stays SOLID.  The Rust
    core (`build.rs:786`) *rejects* a non-identity `scale` tuple and only applies the `rot` 3×3 to
    the brush's local polys, so we BAKE the brush's full linear map `L = PostScale·R·MainScale`
    (`rotation.actor_linear`, double) into `rot`: `FPoly::transform` then yields `world = Location +
    L·(v − PrePivot)`, the correct scaled world winding, and the `scale` tuple stays identity so the
    reject guard never fires.

    GATED on non-identity scale (incl. sheer): an UNSCALED brush keeps the exact rotation-only path,
    byte-identical to baseline.  For a SCALED brush we DROP the authored per-poly normals (empty →
    the Rust core recomputes from the TRANSFORMED winding; the authored local normal is pre-scale)
    but KEEP the authored Origins (`FPoly::transform` maps each by `L`, exactly as the editor's
    `FPoly::Transform` maps `Base` — the surf `pBase`).  A MIRRORED brush (`det L < 0`) has each
    per-poly ring PRE-reversed (the `mirror` note below) so the post-`L` winding stays outward-CCW.
    The transform is DOUBLE precision throughout (the f32 editor-parity vertex/normal path was
    vestigial once native materialize was removed — no surviving consumer needs editor byte-parity).
    Scale lives in the typed `actor.main_scale`/`post_scale` fields (not `props`), so
    `raw.get("MainScale")` is absent and the `scale` tuple below stays identity."""
    raw = dict(actor.props)
    # `Engine.Brush.CsgOper`'s real class default is CSG_Active (0), not CSG_Add — confirmed via
    # `uedcli.classdefaults` against the real `Engine.u`. A brush actor only reaches this default
    # when it never went through a real BRUSH ADD/SUBTRACT/etc (an absent `CsgOper=` in the T3D) —
    # almost certainly a stray/mistaken level-authoring artifact (e.g. Vandenberg Gas's `Brush230`,
    # a 1-poly `NotSolid` brush carrying stray Light-actor properties). The real editor still
    # processes it, and does so exactly like CSG_Subtract (`dev/docs/native-materialize-findings.md`,
    # "Vandenberg Gas +606 node over-build", 2026-09-01 round) — reproduced faithfully per owner
    # ruling rather than silently "corrected" to CSG_Add. See `csg::CsgOper::Active`'s doc comment
    # (`uedcli-native/src/csg.rs`) for the disassembly evidence, and
    # `dev/docs/board/inbox/vandenberg-gas-csg-active-csgoper-brush-causes/overview.md` for a note
    # this authoring pattern may be worth a lint/warning in the future.
    oper_name = raw.get("CsgOper", "CSG_Active")
    oper = _CSG_OPER.get(oper_name)
    if oper is None:
        raise BuildError(f"brush {name}: unknown CsgOper {oper_name!r}")
    try:
        poly_flags = int(raw.get("PolyFlags", "0"))
    except ValueError:
        poly_flags = 0
    from .. import rotation as ROT
    from ..transform import flip_winding, reject_degenerate, DegenerateTransformError
    # A brush is "scaled" when either MainScale (local/pre-rotation) or PostScale (world/post-rotation)
    # is non-identity (incl. sheer).  Only then do we bake the full linear map + drop authored normals;
    # every unscaled brush keeps the exact prior path (rotation-only), preserving byte-parity.
    scaled = not (ROT.actor_main_scale(actor).is_identity()
                  and ROT.actor_post_scale(actor).is_identity())
    mirror = False
    tex_cov = None
    vec_xform_flat: list[float] = []                     # scaled: (L⁻¹)ᵀ VectorXform for the normal
    if scaled:
        # The vertex transform is `L = PostScale·R·MainScale`, passed as the Rust `rot`:
        # `FPoly::transform` yields `world = L·(v−PrePivot)+Loc`, and `scale` stays identity so the
        # core's reject never fires.  `L` includes sheer, so a sheared scale bakes correctly into
        # both the verts and the normal (covariant below).  The VERT map is the EDITOR-FAITHFUL f32
        # `ABrush::BuildCoords` PointXform chain (`rotation.editor_point_xform`), not the double
        # compose — the two differ by 1-ULP chain-rounding on multi-component scale/rotation
        # brushes (same live-gdb round as `editor_vector_xform`; the double `actor_linear` is kept
        # only for the analysis-side inverse/covariant helpers below).
        L = ROT.actor_linear(actor)                      # PostScale·R·MainScale (double, analysis)
        R = ROT.editor_point_xform(actor)                # f32 BuildCoords PointXform (verts)
        # A zero/degenerate scale axis makes L singular -> the covariant `(L⁻¹)ᵀ` inversion below would
        # ZeroDivisionError and reach the CLI user.  Reject cleanly, naming the brush.
        try:
            reject_degenerate(L, name)
        except DegenerateTransformError as e:
            raise BuildError(str(e)) from e
        _Linv = ROT.inverse(L)
        tex_cov = ROT.matmul(_Linv, ROT.transpose(_Linv))  # (LᵀL)⁻¹ — pre-cancels Rust's forward L
        # Covariant pre-cancel for texture axes (§92 §34): the Rust core applies the SAME forward `L` to
        # a poly's TextureU/TextureV as to its verts, but axes are COVECTORS mapping by `(L⁻¹)ᵀ`.  We
        # pass `(LᵀL)⁻¹·texUV` so the core's forward `L·((LᵀL)⁻¹·texUV) = (L⁻¹)ᵀ·texUV` — the editor's
        # covariant axis.  Gated on `scaled`: an unscaled brush (`tex_cov` None) passes axes unchanged.
        # MIRROR (`det L < 0`): the linear map inverts winding, so the L-transformed ring runs CW and
        # `calc_normal` (CCW→outward) would yield INWARD normals — a subtract builds inside-out.  The
        # Rust core assumes Orientation +1 and never re-flips, so we PRE-reverse each poly's ring below
        # (as `transform.bake` does) — after `L` the winding is outward-CCW again.
        mirror = flip_winding(L)
        # Non-mirror: pass the covariant face-normal map `(L⁻¹)ᵀ` so the Rust core recomputes each scaled
        # face's normal via `VectorXform + SafeNormalSlow` (the editor's way — a unit axis normal), NOT
        # `calc_normal` over the L-warped world winding (which yields a non-axis normal on a face made
        # asymmetric by non-uniform scale).  Gated off a mirror: there the covariant image flips
        # orientation, so the ring-reverse + `calc_normal` path stays.
        if not mirror:
            # NOT `covariant_axes(L)` (double `(L⁻¹)ᵀ`, f32-cast): the editor builds VectorXform as
            # an all-f32 `(Unit / MainScale / Rotation / PostScale).Transpose()` chain whose entries
            # differ by 1 ULP (`1.0f/0.624999f = 0x3fcccce3` vs double's `0x3fcccce2`), and that ULP
            # decides whether `SafeNormalSlow` lands the exact `±1.0` axis normal the editor stores
            # in the node plane (UNATCO Brush578 nodes 359-364, live-gdb 2026-09-02 —
            # `pass1_normal_probe_unatco.py`; `rotation.editor_vector_xform`'s own doc comment).
            NT = ROT.editor_vector_xform(actor)
            vec_xform_flat = [float(NT[r][c]) for r in range(3) for c in range(3)]
    else:
        Rm = ROT.actor_matrix(actor)                     # None == renders-as-identity (low-bit fields)
        R = _IDENTITY_ROT if Rm is None else [[float(x) for x in row] for row in Rm]
    loc = tuple(float(c) for c in actor.location) if actor.location else (0.0, 0.0, 0.0)
    prepivot = _parse_vec3(raw.get("PrePivot"))
    # Scale is baked into `R` above (scaled brushes) or genuinely identity (unscaled); MainScale is a
    # typed field, never a prop, so this always resolves to identity and the Rust reject guard passes.
    scale = _parse_vec3(raw.get("MainScale"), default=(1.0, 1.0, 1.0))

    verts_flat: list[float] = []
    poly_sizes: list[int] = []
    normals_flat: list[float] = []
    # PER-POLY authored texture axes (the T3D `TextureU=`/`TextureV=` on each Polygon), in the
    # brush's LOCAL space — `FPoly::transform` rotates them into world space alongside the verts,
    # exactly as the editor's csgRebuild does.  Without them the Rust core synthesizes a default
    # in-plane basis from the normal (`default_texture_axes`); the authored axes are the
    # world/45°-aligned vectors that dedup into the editor's smaller Vectors pool (bspAddVector).
    # Emitted one 3-tuple per poly; an absent axis (None) is passed as (0,0,0), which the Rust
    # `have_u`/`have_v` check (dot > 1e-8) treats as "no authored axis" -> default basis.
    tex_u_flat: list[float] = []
    tex_v_flat: list[float] = []
    # PER-POLY PolyFlags (the T3D `Flags=` on each poly): Portal / FakeBackdrop / Translucent /
    # Masked / TwoSided / NotSolid / Semisolid vary per surface (e.g. the moat's water sheets are
    # `Portal|FakeBackdrop|Translucent|NotSolid`, the skybox is a FakeBackdrop face) — a single
    # brush-level `poly_flags` cannot represent them, and dropping them makes the skybox render as
    # a solid wall + breaks PF_Portal zone detection.  The Rust core ORs the brush-level flags onto
    # each of these (csg.rs), so we pass the per-poly value (brush-level is 0 for authored brushes).
    poly_flags_flat: list[int] = []
    # PER-POLY authored FPoly::Base (the T3D `Origin=` on each Polygon) in the brush's LOCAL space —
    # the surface's texture ORIGIN, a stored FVector that is usually NOT one of the polygon's
    # vertices.  `FPoly::transform` rotates it into world alongside the verts, then the Rust LOOP-1
    # base-snaps it onto the face plane, exactly as the editor's csgRebuild does.  `bspAddNode` stores
    # this point as the surf `pBase`, so it is load-bearing for `Points`/`pBase` byte-parity: without
    # it the Rust core defaults `base` to `verts[0]` (a CORNER), which welds pBase onto a ring vertex
    # instead of emitting the editor's distinct orphan origin point (e.g. the World shell's x=1150
    # face has Origin (0,0,210) -> snapped (1150,0,210), a point no ring vertex touches).  Passed only
    # when EVERY poly carries an Origin (mirrors the normals gate); else empty -> Rust keeps verts[0].
    origins_flat: list[float] = []
    # PER-POLY authored texture pan (the T3D `Pan U=/V=`), two ints per poly -> the world surf's
    # `PanU`/`PanV` (see `umodel.BspSurf.pan`); dropping it slides the texture across the surface.
    # The pan is a texture-space offset, so no brush transform applies to it.  Masked into the
    # 16-bit on-disk slot here, as `unbuilt.py` does for the brush's own `Polys`: unmasked, a pan
    # past 2**31 reaches the CSG core as an out-of-range int and surfaces as an `OverflowError`.
    pans_flat: list[int] = []
    # PER-POLY authored texture IDENTITY (the T3D `Texture=` on each Polygon), as a per-call dedup
    # small int (a `None` texture gets its own id too, so two untextured faces still compare equal —
    # `bspValidateBrush`'s real `Material == Material` gate is a pointer/reference compare, and
    # `None == None` is trivially true in C++ too). Feeds `bsp_validate_brush_links`'s "same Texture"
    # gate (`bspcsg.rs`): WITHOUT this, every freshly-ingested poly's Rust `FPoly.texture` stays at
    # the `FPoly::new` default (0) for every poly of every brush, so that gate was an unconditional
    # no-op at ingestion — found live on `03_NYC_747.dx`'s `Brush473` (291 polys, no case in the
    # corpus before it happened to have two coplanar/same-facing/same-axis polys with GENUINELY
    # different textures, so the gap never surfaced). Not a package-wide texture id (irrelevant here
    # — only EQUALITY among this brush's own polys matters, never compared across brushes/calls).
    textures_flat: list[int] = []
    _tex_ids: dict[str | None, int] = {}
    have_all_origins = True
    have_all_normals = True
    def _axis(a):
        if a is None:
            return [0.0, 0.0, 0.0]                        # no authored axis -> Rust synthesizes default
        v = (float(a[0]), float(a[1]), float(a[2]))
        if tex_cov is not None:                           # scaled brush: covariant pre-cancel (§92 §34)
            v = ROT.matvec(tex_cov, v)
        return [float(v[0]), float(v[1]), float(v[2])]

    for poly in actor.brush.polys:
        poly_sizes.append(len(poly.vertices))
        poly_flags_flat.append(int(getattr(poly, "flags", 0) or 0) & 0xFFFFFFFF)
        # Reverse the ring for a mirrored (det<0) brush so the post-L world winding stays
        # outward-CCW (see the `mirror` note above); an unmirrored/unscaled brush keeps ring order.
        ring = list(reversed(poly.vertices)) if mirror else poly.vertices
        for v in ring:
            verts_flat += [float(v[0]), float(v[1]), float(v[2])]
        if poly.normal is not None:
            normals_flat += [float(poly.normal[0]), float(poly.normal[1]),
                             float(poly.normal[2])]
        else:
            have_all_normals = False
        origin = getattr(poly, "origin", None)
        if origin is not None:
            origins_flat += [float(origin[0]), float(origin[1]), float(origin[2])]
        else:
            have_all_origins = False
        tex_u_flat += _axis(getattr(poly, "texture_u", None))
        tex_v_flat += _axis(getattr(poly, "texture_v", None))
        pan = getattr(poly, "pan", None) or (0, 0)
        pans_flat += [int(pan[0]) & 0xFFFF, int(pan[1]) & 0xFFFF]
        tex_name = getattr(poly, "texture", None)
        textures_flat.append(_tex_ids.setdefault(tex_name, len(_tex_ids)))
    if scaled or not have_all_normals:
        normals_flat = []                                # scaled: authored normal is pre-scale ->
        #                                                  Rust CalcNormal from the transformed winding
    if not have_all_origins:
        origins_flat = []                                # some poly lacks an authored Origin ->
        #                                                  Rust defaults base to verts[0]
    # A SCALED brush KEEPS its authored per-poly Origin (transformed by `L` in `FPoly::transform`,
    # exactly as the editor's `FPoly::Transform` maps `Base`): the surf `pBase` the editor stores is the
    # transformed authored Origin, not a ring corner (§92 §45).
    # `tex_v_flat`, `origins_flat`, `vec_xform_flat`, `pans_flat` and `textures_flat` ride bundled in
    # one tuple (PyO3 tuple FromPyObject caps at 12).  `vec_xform_flat` is the 9-float covariant
    # face-normal map for a scaled (non-mirror) brush, or empty (unscaled/mirror -> Rust keeps the
    # winding-normal path).
    return (verts_flat, poly_sizes, normals_flat, oper, poly_flags,
            list(loc), R, list(prepivot), list(scale), poly_flags_flat,
            tex_u_flat, (tex_v_flat, origins_flat, vec_xform_flat, pans_flat, textures_flat))
