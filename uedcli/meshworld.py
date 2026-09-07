"""Mesh actor world-space vertex placement: `world = Location + PrePivot +
R * Ro * diag(Scale * DrawScale) * (v - Origin)` — verified ✅ source against `UMesh::GetFrame`,
`dev/docs/unrealed/mesh-transform.md` (full derivation: `dev/docs/spikes/
2026-09-07-mesh-origin-rotorigin-transform/`). NOT the brush/CSG convention (`architecture.md`
"D8": `Location + R*(v-PrePivot)`, PrePivot INSIDE the rotation) -- a different call site, a
different PrePivot convention, for the same actor field.

A LEAF: stdlib + `uedcli.rotation` only (mirrors `texframe.py`'s own leaf rationale)."""
from __future__ import annotations

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


def mesh_scale(mesh) -> tuple[float, float, float]:
    """The mesh's own `Scale` as a multiplier, with an ALL-ZERO `Scale` read as unset -> identity.
    Some stock meshes bake `Scale=(0,0,0)` (e.g. `DeusExCharacters.SpiderBot2`); taken literally it
    collapses the placement map to the zero matrix, which `reject_degenerate` then refuses, aborting
    a whole photo over one decoration. Same guard the thumbnail renderer already applies
    (`meshrender.render_class`)."""
    return mesh.scale if any(mesh.scale) else (1.0, 1.0, 1.0)


def mesh_vertex_to_world(v, *, mesh, actor) -> tuple[float, float, float]:
    """One mesh-local vertex `v` (raw `FMeshVert`, mesh-local units) -> world space, per the
    formula above."""
    origin = mesh.origin
    scale = mesh_scale(mesh)
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
    sx, sy, sz = (float(c) * draw_scale for c in mesh_scale(mesh))
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


def mesh_actor_translation(actor) -> tuple[float, float, float]:
    """Location + PrePivot as one combined UNROTATED world-space offset (see module doc) -- the
    translation half of the placement formula, paired with `mesh_actor_linear`'s linear half.
    Compute once per actor, same reasoning as `mesh_actor_linear`."""
    loc = tuple(float(c) for c in (actor.location or (0, 0, 0)))
    pp = actor_prepivot(actor)
    return (loc[0] + float(pp[0]), loc[1] + float(pp[1]), loc[2] + float(pp[2]))


def apply_mesh_linear(v, *, mesh_origin, L, translation) -> tuple[float, float, float]:
    """Fast per-vertex apply once `L` (`mesh_actor_linear`) and `translation`
    (`mesh_actor_translation`) are precomputed: `translation + L·(v - mesh_origin)`. For a caller
    processing many vertices per actor this is ~100x faster than `mesh_vertex_to_world`, which
    recomputes the rotation matrices from scratch every call. `mesh_vertex_to_world` stays as the
    simple, independently-verified per-call reference (used by its own tests and any one-off
    caller) -- this is an equivalent fast path for a hot loop, not a replacement."""
    w = (float(v[0]) - float(mesh_origin[0]),
         float(v[1]) - float(mesh_origin[1]),
         float(v[2]) - float(mesh_origin[2]))
    w = matvec(L, w)
    return (translation[0] + w[0], translation[1] + w[1], translation[2] + w[2])


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
    the derivation. Returns `None` for a degenerate (zero-area) triangle.

    Math: choose `base = v0`, `pan = uv0`. Let `e1 = v1-v0`, `e2 = v2-v0` (in-plane edges) and
    `d1 = uv1-uv0`, `d2 = uv2-uv0` (their target UV deltas, per U and V independently). For each of
    U and V, solve the 2×2 system `[[e1.e1, e1.e2], [e1.e2, e2.e2]] · [alpha, beta] = [d, d2]`
    (the Gram matrix of the two edges) via Cramer's rule, giving `axis = alpha*e1 + beta*e2`. The
    determinant `e1.e1*e2.e2 - (e1.e2)^2` is (twice the triangle's area)² — zero exactly when the
    triangle is degenerate, which is the `None` return trigger. `render.rs` computes UV as
    `dot(p - uv_base, axis) + pan` for any world point `p`; by construction this exactly reproduces
    `uv0`/`uv1`/`uv2` at `v0`/`v1`/`v2`, and (since `p`'s in-plane component is what's tested
    against) everywhere else on the triangle's plane too."""
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
