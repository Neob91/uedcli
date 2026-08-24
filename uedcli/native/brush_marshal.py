"""Brush -> CSG `BrushTuple` marshalling for `uedcli_native.build_geometry`.

Turns a trunk brush actor into the flat tuple the Rust CSG core takes, and decides
which brushes are carved into the world BSP (`_in_world_csg`). Shared by `brushcsg`
(the `brush intersect`/`deintersect` verbs) and `preview_native` (`level preview --native`).
"""
from __future__ import annotations

import struct

from ..movers import is_mover

# ECsgOper ordinals == the Rust `build_geometry` oper codes (1=Add..4=Deintersect).
_CSG_OPER = {"CSG_Active": 0, "CSG_Add": 1, "CSG_Subtract": 2,
             "CSG_Intersect": 3, "CSG_Deintersect": 4}
_IDENTITY_ROT = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


class BuildError(Exception):
    """A native-build failure carrying the offending value (surfaces as a clean exit-2)."""


def _f32(x: float) -> float:
    """Round to float32 — the editor's `FCoords` scale arithmetic is single-precision, so the
    covariant normal map's per-axis reciprocals must be built at f32 to match it (§92 §43)."""
    return struct.unpack("f", struct.pack("f", float(x)))[0]


def _pointxform_f32(actor):
    """The editor's `FModelCoords.PointXform` linear map, built in UnrealEd's f32 `FCoords` op-order
    `((UnitCoords·PostScale)·Rotation)·MainScale` (`ABrush::BuildCoords`, Engine.dll 0x111390; §92 §45),
    NOT `rotation.actor_linear`'s Python-DOUBLE matmul.

    Both compute the SAME map `L = diag(PostScale)·R·diag(MainScale)`; the difference is WHERE f32
    rounding lands.  The effective element is `M[i][k] = f32( f32(PostScale_i · R[i][k]) · MainScale_k )`:
    PostScale scales row `i`, `R` is the GMath rotation matrix, MainScale scales column `k`.  Two things
    the double matmul gets wrong (§92 §45 review):
      * **The dominant lever for DX content (the ONE that moves the bit): the scale INPUTS are f32-cast
        before the multiply.**  The editor stores `FVector Scale` as float32, so it multiplies by
        `f32(0.249997)` where `rotation.actor_linear` multiplies by the raw double `0.249997`.  On the
        cardinal cross-term `R[0][1] = -sin(180°) = 8.742278e-08` (§42), `f32(f32(PS)·R)` = `0x32bbbc9b`
        vs the double's `0x32bbbc9a` — 1 ULP, which a ~2000uu vertex amplifies into the node-`w` twin
        (UNATCO Brush541/Brush348).  EVERY DX rot+scale brush has MainScale=identity, so this input cast
        is the whole effect there.
      * **The intermediate f32 round after `PostScale·Rotation`, before `MainScale`** — a genuine
        SECOND rounding that bites ONLY when both PostScale and MainScale are non-unit on the SAME
        crossed off-axis (`f32(f32(PS·R)·MS)` ≠ `f32(PS·R·MS)`).  No DX brush exercises it (all have
        MS=identity), but reproducing it keeps the general case editor-faithful.
    `FCoords::operator*(FScale)` multiplies each axis per-column by Scale (0x18180);
    `FCoords::operator*(FCoords)` composes via `TransformVectorBy` (0x2dd50) with `M_Rotation = Rᵀ`, so
    the compose reproduces `diag(PS)·R` (a diagonal `M_A` makes each compose a single f32 multiply — the
    two zero terms add exactly).

    Non-sheared only (every DX MainScale/PostScale has SheerRate=0; the caller rejects sheer for every
    scaled brush).  Returns a 3×3 list of f32 floats — the `rot` matrix the Rust `FPoly::transform`
    applies as `world = L·(v−PrePivot)+Loc`."""
    from .. import rotation as ROT
    Rm = ROT.actor_matrix(actor)                         # GMath rotation 3×3 (None == identity)
    R = _IDENTITY_ROT if Rm is None else [[_f32(float(x)) for x in row] for row in Rm]
    PS = [_f32(float(c)) for c in ROT.actor_post_scale(actor).scale]
    MS = [_f32(float(c)) for c in ROT.actor_main_scale(actor).scale]
    return [[_f32(_f32(PS[i] * R[i][k]) * MS[k]) for k in range(3)] for i in range(3)]


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
    size carves a tiny hole instead of the full room, so the room interior stays SOLID and the
    editor's open void reads solid in native (`shatter_probe.py` metric `[A]` — HK 74.5%, UNATCO
    15.3%).  The Rust core (`build.rs:786`) *rejects* a non-identity `scale` tuple and only applies
    the `rot` 3×3 to the brush's local polys, so we BAKE the brush's full linear map
    `L = PostScale·R·MainScale` (`rotation.actor_linear`) into `rot`: `FPoly::transform` then yields
    `world = Location + L·(v − PrePivot)`, the correct scaled world winding, and the `scale` tuple
    stays identity so the reject guard never fires (matching its own advice, "apply scale upstream").
    Result: HK `[A]` 74.5%→8.9% (surfs 2664→4723 toward the 5224 golden), UNATCO 15.3%→1.1%.

    GATED on non-identity scale: an UNSCALED brush (which is EVERY brush on the castle — 0 scaled
    brushes) takes the exact existing rotation-only path, so its build is byte-identical to baseline
    (verified: castle 485 surfs / 1156 nodes unchanged; only the package GUID differs).  For a SCALED
    brush we additionally DROP the authored per-poly normals and Origins (empty lists → the Rust
    core recomputes each from the TRANSFORMED winding): the authored local-space normal/Origin are
    PRE-scale and no longer describe the scaled face, and the core already re-derives every final
    surf `vNormal` from its winding (`build.rs` post-`bsp_merge_coplanars` plane pass + the oracle's
    `finalize`/`calc_normal`), so a winding-derived normal is exactly right and needs no
    inverse-transpose here; the surf `pBase` falls back to the poly's `verts[0]`.  A MIRRORED brush
    (`det(L) < 0`) has its per-poly ring PRE-reversed (see the `mirror` note below) so the post-`L`
    winding stays outward-CCW.  Texture axes (`TextureU`/`TextureV`) ride the SAME forward `L`
    through `FPoly::transform` — exact only for a PURE ROTATION; the editor treats them as covectors
    (`transform.bake` uses the inverse-transpose `(L⁻¹)ᵀ`), so under ANY non-identity scale (uniform
    included) forward-`L` differs.  This changes neither solidity nor surf COUNTS (the gated metrics)
    — it can shift the `Vectors`-pool dedup, i.e. a byte-PARITY / texture-appearance concern only —
    and is boarded separately (needs live editor evidence to pin the exact convention).  Scale lives
    in the typed `actor.main_scale`/`post_scale` fields (not `props`), so `raw.get("MainScale")` is
    absent and the `scale` tuple below stays identity."""
    raw = dict(actor.props)
    oper_name = raw.get("CsgOper", "CSG_Add")
    oper = _CSG_OPER.get(oper_name)
    if oper is None:
        raise BuildError(f"brush {name}: unknown CsgOper {oper_name!r}")
    try:
        poly_flags = int(raw.get("PolyFlags", "0"))
    except ValueError:
        poly_flags = 0
    from .. import rotation as ROT
    # A brush is "scaled" when either MainScale (local/pre-rotation) or PostScale (world/post-rotation)
    # is non-identity.  Only then do we bake the full linear map + drop authored normals/Origins;
    # every unscaled brush keeps the exact prior path (rotation-only), preserving byte-parity.
    scaled = not (ROT.actor_main_scale(actor).is_identity()
                  and ROT.actor_post_scale(actor).is_identity())
    mirror = False
    # Covariant pre-cancel for texture axes on SCALED brushes (§92 §34).  The Rust core transforms a
    # poly's TextureU/TextureV by the SAME forward map it applies to verts (`FPoly::transform` ->
    # `rot_only` with `rot = L`), i.e. it emits `L·texUV`.  But texture axes are COVECTORS: the editor
    # transforms them by the inverse-transpose `(L⁻¹)ᵀ` (`transform.bake`'s `NT`), so under a
    # non-identity scale forward-`L` SQUARES the scale into the axis magnitude (e.g. UNATCO Brush420
    # PostScale.x=1.4167, authored texU.x=1.4167 -> native 1.4167²=2.0069 vs the editor's
    # 1.4167/1.4167=1.0), producing extra Vectors-pool entries that never dedup (the +146 UNATCO
    # vector over-production is entirely these scaled-brush texture axes — see §92 §34).  Since Rust
    # will re-apply `L`, we PRE-CANCEL here: pass `P·texUV` with `P = L⁻¹·(L⁻¹)ᵀ = (LᵀL)⁻¹`, so that
    # `L·(P·texUV) = (L⁻¹)ᵀ·texUV` — exactly the editor's covariant axis.  GATED on `scaled`: an
    # unscaled brush (every castle brush; `tex_cov` stays None) keeps the identity path byte-for-byte.
    # SCOPE: this closes the +146 vector-COUNT over-production (the round-tripped axis dedups into the
    # editor's pool entry, well within `bsp_add_vector`'s 0.001 tol), but `L·(LᵀL)⁻¹·v` is NOT
    # bit-identical to the editor's direct `(L⁻¹)ᵀ·v` (sub-tol FP drift from the L round-trip) — full
    # axis-VALUE byte-parity is a separate concern (would need Rust to apply the covariant map directly).
    from ..transform import det3
    tex_cov = None
    vec_xform_flat: list[float] = []                     # scaled: (L⁻¹)ᵀ VectorXform for the normal
    if scaled:
        L = ROT.actor_linear(actor)                      # PostScale·R·MainScale (double; det/inverse/mirror)
        # §92 §45: build the vertex transform `R` (the editor's PointXform) in UnrealEd's f32 `FCoords`
        # op-order, NOT the double `L` above — the editor multiplies by the f32-cast `FVector Scale`
        # (and rounds per FCoords op), where the double matmul multiplies by the raw double scale; that
        # 1-ULP gap on the cardinal cross-term is the rot+scale node-`w` VERTEX twin (§92 §44/§45).  `L`
        # stays double for the covariant/mirror/det math below (tolerance-level; the normal is renormalized).
        R = _pointxform_f32(actor)
        # SHEER guard for EVERY scaled brush (mirror or not): `_pointxform_f32` (the vertex map) AND the
        # covariant `(L⁻¹)ᵀ` normal map below are built from the DIAGONAL scale only, so a non-zero
        # SheerRate would shear NEITHER the verts nor the normal — a silent mis-build.  Every DX
        # MainScale/PostScale has SheerRate=0 (transform.py), so reject cleanly (repo rule: no silent
        # wrong result).  Hoisted here to also cover the MIRROR case: pre-§45 only the non-mirror branch
        # rejected sheer (the mirror branch baked sheer into the double-`L` verts), but now BOTH branches
        # take the diagonal `_pointxform_f32` for `R`, so both must reject (§92 §45 review C3).
        if (float(ROT.actor_main_scale(actor).sheer_rate) != 0.0
                or float(ROT.actor_post_scale(actor).sheer_rate) != 0.0):
            raise BuildError(
                f"Brush {name}: sheared scale (non-zero SheerRate) is unsupported — the f32 PointXform "
                f"and covariant normal map are both built from the diagonal scale only")
        # A zero/degenerate scale axis makes L singular -> `ROT.inverse` would ZeroDivisionError and
        # reach the CLI user (repo rule: no bare traceback, name the offending value).  Reject cleanly.
        if abs(det3(L)) < 1e-12:
            raise BuildError(
                f"Brush {name}: non-invertible scale (zero or degenerate MainScale/PostScale axis, "
                f"det(L)={det3(L):.3g}) — cannot compute covariant texture axes")
        _Linv = ROT.inverse(L)
        tex_cov = ROT.matmul(_Linv, ROT.transpose(_Linv))  # (LᵀL)⁻¹ — pre-cancels Rust's forward L
        # MIRROR (odd number of negative scale axes → det(L) < 0): the linear map inverts winding
        # orientation, so the L-transformed vertex ring runs CW and `calc_normal` (CCW→outward) would
        # yield INWARD normals — a subtract would build inside-out.  The Rust core assumes Orientation
        # +1 (`bspcsg.rs:1589` "NO LOOP-1 reverse") and never re-flips, so we PRE-reverse each poly's
        # ring here (exactly as the model-side `transform.bake` does on `det3(L) < 0`) — after L the
        # winding is outward-CCW again and the recomputed normal is correct.  The OLD code rejected all
        # scaled brushes; this keeps a mirrored brush a correct build instead of a silent mis-build.
        mirror = det3(L) < 0.0
        # §92 §43: the editor computes each SCALED face's normal via `ABrush::BuildCoords`' VectorXform
        # `(L⁻¹)ᵀ` + `SafeNormalSlow` (covariant), NOT `calc_normal` over the L-warped world winding —
        # which yields `0.99999994` (1 ULP under unit) on a face made asymmetric by non-uniform scale
        # (Brush578's ±x/±y → the N=30 committed twins).  Pass `(L⁻¹)ᵀ` so the Rust core recomputes the
        # face normal the editor's way.
        #
        # `L = PostScale·R·MainScale = diag(PS)·R·diag(MS)`, so the covariant map is
        #   `(L⁻¹)ᵀ = diag(1/PS)·(R⁻¹)ᵀ·diag(1/MS) = diag(1/PS)·R·diag(1/MS)`  (R orthonormal).
        # We build it from CLEAN per-axis f32 reciprocals `1/PS`, `1/MS` (the editor's
        # `FCoords::operator/(FScale)` divides each axis by the scale — one `divss` per component) times
        # the SAME GMath `R` — NOT `ROT.transpose(ROT.inverse(L))`, whose adjugate/determinant mixes the
        # axes so `1/1.625` comes back 1 ULP off and `SafeNormalSlow` renormalizes an axis normal to
        # `0.99999994` (re-introducing the very twin).  GATED off a MIRROR (det<0): there the covariant
        # image flips orientation, so the ring-reverse + `calc_normal` path above stays (no DX
        # mirror-scaled brush exists — verified — so this is a safety gate, not an exercised branch).
        if not mirror:
            # (Sheer is already rejected above for every scaled brush.)  Build the covariant normal map
            # `(L⁻¹)ᵀ = diag(1/PS)·R·diag(1/MS)` from CLEAN per-axis f32 reciprocals.
            def _recip_diag(fs):
                s = fs.scale
                return [[(_f32(1.0 / _f32(float(s[j]))) if i == j else 0.0) for j in range(3)]
                        for i in range(3)]
            Rm = ROT.actor_matrix(actor)                 # GMath R (None == identity)
            R_only = _IDENTITY_ROT if Rm is None else [[float(x) for x in row] for row in Rm]
            _vx = ROT.matmul(_recip_diag(ROT.actor_post_scale(actor)),
                             ROT.matmul(R_only, _recip_diag(ROT.actor_main_scale(actor))))
            vec_xform_flat = [float(_vx[r][c]) for r in range(3) for c in range(3)]
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
    if scaled or not have_all_normals:
        normals_flat = []                                # scaled: authored normal is pre-scale ->
        #                                                  Rust CalcNormal from the transformed winding
    if not have_all_origins:
        origins_flat = []                                # some poly lacks an authored Origin ->
        #                                                  Rust defaults base to verts[0]
    # §92 §45: a SCALED brush KEEPS its authored per-poly Origin (transformed by `L` in `FPoly::transform`,
    # exactly as the editor's `FPoly::Transform` maps `Base`).  Native used to drop it (base := verts[0]),
    # but the surf `pBase` the editor stores is the TRANSFORMED authored Origin, not a ring corner — and
    # because a scaled face's node normal carries tiny non-axis components (covariant map), `w = Normal·Base`
    # differs by ~1 ULP between the two base points.  Passing the authored Origin closed all 8 UNATCO N=105
    # scaled-brush vertex/`w` twins (Brush48/236/359/750).  (Unscaled brushes already keep their Origin.)
    # `tex_v_flat`, `origins_flat` and `vec_xform_flat` ride bundled in a triple (PyO3 tuple
    # FromPyObject caps at 12).  `vec_xform_flat` is 9 floats (the covariant face-normal map for a
    # scaled brush, §92 §43) or empty (unscaled -> Rust keeps the winding-normal path).
    return (verts_flat, poly_sizes, normals_flat, oper, poly_flags,
            list(loc), R, list(prepivot), list(scale), poly_flags_flat,
            tex_u_flat, (tex_v_flat, origins_flat, vec_xform_flat))
