"""Model-side parametric brush builders — cube / cylinder / cone / sheet /
staircase / spiral staircase.

UnrealEd's native BrushBuilders are GUI-dialog-driven (`WDlgBrushBuilder::OnBuild`
→ builder `Build()`) and NOT console-invocable (`SET <BuilderClass>` only sets the
class defaults; the dialog is the build trigger — see dev/docs/spikes/2026-06-17-capability-gaps.md). So
we replicate them in Python: each builder returns a `Brush` (a PolyList) with
CCW-from-outside winding and non-degenerate texture vectors, which the caller adds
via the EDIT PASTE path (`writes.add_actor`) like any other brush — no GUI.

Winding is load-bearing: UnrealEd's importer IGNORES the emitted `Normal` and
derives each face from its vertex winding, so every face must wind CCW seen from
OUTSIDE or CSG inverts/crashes on REBUILD (see dev/unrealed/quirks). Rather than
hand-wind each face, `_face` takes the face's vertex ring plus a rough OUTWARD
direction and flips the ring if its winding-derived (Newell) normal disagrees — so
the ring may be supplied in either order.

The linear `staircase` is ONE non-convex brush (the UED `LinearStairBuilder`
stepped-wedge outer hull: Base + back + per-step Step/Rise + tiled convex Side
strips) — its per-step boundaries are watertight T-junctions that `level doctor`'s
T-junction-aware `check_watertight` accepts (decisions.md 2026-07-21 12:06 UTC). The
`spiral_staircase` is a LIST of convex brushes — a central column plus one wedge
(pie-slice) tread per step, ascending monotonically around the column
(decisions.md 2026-07-22); each brush is a clean convex solid and separate step
brushes are standard for CSG.

Coordinates are the brush's own local vertex space, centered on the origin; the
actor `Location` places it in the world.
"""
from __future__ import annotations

import copy
import math

from .emit import clean
from .geometry import GeometryError
from .model import Actor, Brush, Polygon, Vec3

# Two vertices closer than WELD collapse to one (drop zero-length ring edges).
WELD = 1e-3

# Surface/brush PolyFlags by value (named at the CLI; see dev/unrealed/quirks).
PF_NOTSOLID = 0x00000008
PF_SEMISOLID = 0x00000020
PF_TWOSIDED = 0x00000100

# Brush solidity → the actor's PolyFlags (whole-brush). "solid" carries no flag.
SOLIDITY_FLAGS = {"solid": 0, "semisolid": PF_SEMISOLID, "nonsolid": PF_NOTSOLID}
CSG_OPER = {"add": "CSG_Add", "subtract": "CSG_Subtract"}


def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def _mul(a, s): return (a[0] * s, a[1] * s, a[2] * s)
def _dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])
def _len(a): return math.sqrt(_dot(a, a))


def _normalize(a: Vec3) -> Vec3:
    n = _len(a)
    if n < 1e-9:
        raise GeometryError("builder: zero-length direction vector")
    return (a[0] / n, a[1] / n, a[2] / n)


def _centroid(ring) -> Vec3:
    n = len(ring)
    return (sum(p[0] for p in ring) / n,
            sum(p[1] for p in ring) / n,
            sum(p[2] for p in ring) / n)


def _newell(ring) -> Vec3:
    """Newell's method: a robust face normal from the vertex winding (the same
    quantity UnrealEd derives the face from). Points CCW-from-the-named-side."""
    nx = ny = nz = 0.0
    m = len(ring)
    for i in range(m):
        a, b = ring[i], ring[(i + 1) % m]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    return (nx, ny, nz)


def _dedup_ring(ring):
    """Drop consecutive (and wrap-around) near-duplicate vertices."""
    out = []
    for v in ring:
        if not out or _len(_sub(v, out[-1])) > WELD:
            out.append(v)
    if len(out) > 1 and _len(_sub(out[0], out[-1])) <= WELD:
        out.pop()
    return out


def _tex_basis(normal: Vec3):
    """Unit in-plane (TextureU, TextureV) for a face. Zero-length texture vectors
    crash REBUILD, so seed from the world axis least aligned with the normal."""
    ax = min(range(3), key=lambda i: abs(normal[i]))
    seed = [0.0, 0.0, 0.0]
    seed[ax] = 1.0
    seed = (seed[0], seed[1], seed[2])
    u = _normalize(_sub(seed, _mul(normal, _dot(seed, normal))))
    v = _cross(normal, u)
    return u, v


def _face(ring, outward: Vec3, texture=None, flags: int = 0,
          item: str | None = None) -> Polygon:
    """Build a Polygon from a boundary vertex ring + a rough OUTWARD direction.

    The ring may be wound either way: if its winding-derived (Newell) normal
    disagrees with `outward`, the ring is reversed so the emitted winding faces
    out. `outward` need only have the correct sign on the true normal (used to
    pick the flip and the texture basis), so an approximate radial direction is
    fine for slanted faces (cones). `item` is the polygon's ItemName (UED's
    semantic face label, e.g. Step/Rise/Side) for surface selection-by-item."""
    ring = _dedup_ring(ring)
    if len(ring) < 3:
        raise GeometryError("builder: face has < 3 distinct vertices")
    nw = _newell(ring)
    if _len(nw) < 1e-9:
        raise GeometryError("builder: degenerate (zero-area) face")
    out = _normalize(outward)
    if _dot(nw, out) < 0:
        ring = list(reversed(ring))
    u, v = _tex_basis(out)
    p = Polygon(flags=flags, texture=texture)
    p.item = item
    p.origin = _centroid(ring)
    p.normal = out                 # advisory; the editor recomputes from winding
    p.texture_u = u
    p.texture_v = v
    # pan stays at Polygon's own default (None) -- a freshly built face is never panned;
    # an explicit (0, 0) here would always emit `Pan U=0 V=0`, which the editor's own re-export
    # omits as the implicit zero default, breaking canonical-hash equality on first materialize
    # (2026-06-21, same family of fix as normalize.py's zero-Location handling).
    p.vertices = ring
    return p


def translate_brush(brush: Brush, dx: float, dy: float, dz: float) -> Brush:
    nb = copy.deepcopy(brush)
    for p in nb.polys:
        p.vertices = [(x + dx, y + dy, z + dz) for x, y, z in p.vertices]
        if p.origin is not None:
            ox, oy, oz = p.origin
            p.origin = (ox + dx, oy + dy, oz + dz)
    return nb


def _rotate_z(brush: Brush, degrees: float) -> Brush:
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))

    def R(v):
        if v is None:
            return None
        x, y, z = v
        return (x * c - y * s, x * s + y * c, z)

    nb = copy.deepcopy(brush)
    for p in nb.polys:
        p.vertices = [R(v) for v in p.vertices]
        p.origin = R(p.origin)
        p.normal = R(p.normal)
        p.texture_u = R(p.texture_u)
        p.texture_v = R(p.texture_v)
    return nb


# --- convex primitives -------------------------------------------------------


def cube(width: float, breadth: float, height: float,
         texture=None, flags: int = 0) -> Brush:
    """An axis-aligned box: `width` (X) × `breadth` (Y) × `height` (Z), centered
    on the origin."""
    hx, hy, hz = width / 2.0, breadth / 2.0, height / 2.0

    def C(sx, sy, sz):
        return (sx * hx, sy * hy, sz * hz)

    faces = [
        ([C(1, -1, -1), C(1, 1, -1), C(1, 1, 1), C(1, -1, 1)], (1, 0, 0)),     # +X
        ([C(-1, 1, -1), C(-1, -1, -1), C(-1, -1, 1), C(-1, 1, 1)], (-1, 0, 0)),  # -X
        ([C(1, 1, -1), C(-1, 1, -1), C(-1, 1, 1), C(1, 1, 1)], (0, 1, 0)),     # +Y
        ([C(-1, -1, -1), C(1, -1, -1), C(1, -1, 1), C(-1, -1, 1)], (0, -1, 0)),  # -Y
        ([C(-1, -1, 1), C(1, -1, 1), C(1, 1, 1), C(-1, 1, 1)], (0, 0, 1)),     # +Z
        ([C(-1, 1, -1), C(1, 1, -1), C(1, -1, -1), C(-1, -1, -1)], (0, 0, -1)),  # -Z
    ]
    return Brush(model_name="Model",
                 polys=[_face(r, o, texture, flags, item="OUTSIDE") for r, o in faces])


def cylinder(height: float, radius: float, sides: int = 8,
             texture=None, flags: int = 0, angle_offset: float = 0.0) -> Brush:
    """An `sides`-gon prism of `height` (Z) and circumscribed `radius`, centered
    on the origin. `angle_offset` (deg) rotates the cross-section (e.g. to put a
    flat face on an axis)."""
    if sides < 3:
        raise GeometryError("cylinder needs >= 3 sides")
    hz = height / 2.0
    off = math.radians(angle_offset)
    ring = [(radius * math.cos(off + 2 * math.pi * i / sides),
             radius * math.sin(off + 2 * math.pi * i / sides)) for i in range(sides)]
    top = [(x, y, hz) for x, y in ring]
    bot = [(x, y, -hz) for x, y in ring]
    polys = []
    for i in range(sides):
        j = (i + 1) % sides
        quad = [bot[i], bot[j], top[j], top[i]]
        outward = ((ring[i][0] + ring[j][0]) / 2, (ring[i][1] + ring[j][1]) / 2, 0.0)
        polys.append(_face(quad, outward, texture, flags, item="Side"))
    polys.append(_face(top, (0, 0, 1), texture, flags, item="Cap"))
    polys.append(_face(bot, (0, 0, -1), texture, flags, item="Cap"))
    return Brush(model_name="Model", polys=polys)


def cone(height: float, radius: float, sides: int = 8,
         texture=None, flags: int = 0, angle_offset: float = 0.0) -> Brush:
    """An `sides`-faced cone: base ring of `radius` at the bottom, apex at the
    top, total `height` (Z), centered on the origin."""
    if sides < 3:
        raise GeometryError("cone needs >= 3 sides")
    hz = height / 2.0
    off = math.radians(angle_offset)
    base = [(radius * math.cos(off + 2 * math.pi * i / sides),
             radius * math.sin(off + 2 * math.pi * i / sides), -hz) for i in range(sides)]
    apex = (0.0, 0.0, hz)
    polys = []
    for i in range(sides):
        j = (i + 1) % sides
        tri = [base[i], base[j], apex]
        outward = ((base[i][0] + base[j][0]) / 2, (base[i][1] + base[j][1]) / 2, 0.0)
        polys.append(_face(tri, outward, texture, flags, item="Side"))
    polys.append(_face(base, (0, 0, -1), texture, flags, item="Base"))
    return Brush(model_name="Model", polys=polys)


def sheet(width: float, height: float, plane: str = "xz",
          texture=None, flags: int | None = None,
          extra_flags: list[str] | None = None) -> Brush:
    """A flat, two-sided, non-solid rectangle (a fence / masked panel) in the
    given world `plane` (xy|xz|yz), centered on the origin. Defaults to
    TwoSided|NotSolid PolyFlags so it renders from both sides and never carves CSG.
    `extra_flags` (PF_NAMES flag names) are OR-ed onto the face's PolyFlags at build
    time — e.g. ['portal', 'translucent'] for a zone portal — via the same
    name→bit mapping `brush poly set --add-flag` uses (`surface.encode_flags`)."""
    if flags is None:
        flags = PF_TWOSIDED | PF_NOTSOLID
    if extra_flags:
        from .surface import encode_flags
        flags |= encode_flags(extra_flags)
    hw, hh = width / 2.0, height / 2.0
    if plane == "xy":
        ring = [(-hw, -hh, 0), (hw, -hh, 0), (hw, hh, 0), (-hw, hh, 0)]
        outward = (0, 0, 1)
    elif plane == "xz":
        ring = [(-hw, 0, -hh), (hw, 0, -hh), (hw, 0, hh), (-hw, 0, hh)]
        outward = (0, 1, 0)
    elif plane == "yz":
        ring = [(0, -hw, -hh), (0, hw, -hh), (0, hw, hh), (0, -hw, hh)]
        outward = (1, 0, 0)
    else:
        raise GeometryError(f"sheet plane must be xy|xz|yz, got {plane!r}")
    return Brush(model_name="Model",
                 polys=[_face(ring, outward, texture, flags, item="Sheet")])


# --- staircases: linear = ONE non-convex brush; spiral = convex column + wedge treads ---


def staircase(steps: int, depth: float, rise: float, breadth: float,
              texture=None, flags: int = 0) -> Brush:
    """A linear staircase as ONE non-convex `Brush` ascending in +X — the UED
    `LinearStairBuilder` stepped-wedge outer hull. It is the CSG union of the filled
    step columns (column `k` fills `X∈[k*depth,(k+1)*depth]`, `Y∈[0,breadth]`,
    `Z∈[0,(k+1)*rise]`), emitted as a single brush carrying ONLY the outer faces.

    Faces (all via `_face`, CCW-from-outside), face count `2 + 4*steps`:
      - `Base` (-Z): the floor quad `X∈[0, steps*depth] × Y∈[0, breadth]` at z=0.
      - `back` (+X): the full-height rear quad at x=steps*depth, `Z∈[0, steps*rise]`.
      - per step `k` (0..steps-1): a `Step` tread (+Z at z=(k+1)*rise, over
        `X∈[k*depth,(k+1)*depth]`) and a `Rise` riser (-X at x=k*depth,
        `Z∈[k*rise,(k+1)*rise]`). The first tread sits one `rise` above the floor.
      - `Side` (±Y): the stepped silhouette on each side, TILED into per-step convex
        quads — one rectangle per step column, `X∈[k*depth,(k+1)*depth] × Z∈[0,(k+1)*rise]`
        — NOT one non-convex polygon (a non-convex FPoly is a real CSG defect that
        `check_convex` rightly rejects, so the FACES stay convex while the BRUSH is
        non-convex).

    The solid spans `X∈[0, steps*depth]`, `Y∈[0, breadth]`, `Z∈[0, steps*rise]` —
    entirely at/above the floor, front-bottom corner (min X/Y/Z) at the local origin,
    so `--at` places that corner. The per-step Side/tread/riser/base boundaries meet
    as watertight T-junctions (a shorter Side strip's edge collinear with the longer
    neighbour's / the base's long edge opposed by the chain of strip-bottom edges);
    `level doctor`'s T-junction-aware `check_watertight` reports zero findings on them.
    Matches UED's own `LinearStairBuilder` face taxonomy (`2 + 4n`; Base/back/Step/
    Rise/tiled-Side) — decisions.md 2026-07-21 12:06 UTC.

    NATIVE-CSG CAVEAT: this non-convex brush is built correctly by UnrealEd (the
    default `level materialize`) and the real engine (the default `--game` preview),
    but the experimental native CSG core assumes convex brushes
    (`uedctl-native/src/csg.rs` `point_in_convex`), so the native paths (`--native`,
    native materialize) mis-classify its concave notches — see architecture.md."""
    if steps < 1:
        raise GeometryError("staircase needs >= 1 step")
    W, H, B = steps * depth, steps * rise, breadth
    polys = [
        _face([(0, 0, 0), (W, 0, 0), (W, B, 0), (0, B, 0)], (0, 0, -1),
              texture, flags, item="Base"),
        _face([(W, 0, 0), (W, B, 0), (W, B, H), (W, 0, H)], (1, 0, 0),
              texture, flags, item="back"),
    ]
    for k in range(steps):                       # profile faces: tread (+Z) + riser (-X) per step
        x0, x1, z_top = k * depth, (k + 1) * depth, (k + 1) * rise
        polys.append(_face([(x0, 0, z_top), (x1, 0, z_top),
                            (x1, B, z_top), (x0, B, z_top)], (0, 0, 1),
                           texture, flags, item="Step"))
        polys.append(_face([(x0, 0, k * rise), (x0, B, k * rise),
                            (x0, B, z_top), (x0, 0, z_top)], (-1, 0, 0),
                           texture, flags, item="Rise"))
    for k in range(steps):                        # tiled convex Side strips (±Y) per step column
        x0, x1, z_top = k * depth, (k + 1) * depth, (k + 1) * rise
        polys.append(_face([(x0, 0, 0), (x1, 0, 0), (x1, 0, z_top), (x0, 0, z_top)],
                           (0, -1, 0), texture, flags, item="Side"))
        polys.append(_face([(x0, B, 0), (x1, B, 0), (x1, B, z_top), (x0, B, z_top)],
                           (0, 1, 0), texture, flags, item="Side"))
    return Brush(model_name="Model", polys=polys)


# Facets on the central spiral column (a plain N-gon prism); fixed so the golden
# and offline tests are deterministic. 16 reads as round without over-tessellating.
SPIRAL_COLUMN_SIDES = 16


def spiral_staircase(steps: int, inner_radius: float, step_width: float, rise: float,
                     degrees_per_step: float = 30.0,
                     texture=None, flags: int = 0) -> list[Brush]:
    """A real spiral staircase: a central column plus one WEDGE (pie-slice) tread per
    step, ascending monotonically around the column. Returns `steps + 1` brushes —
    `[column, wedge_0, wedge_1, ...]`.

    - **Central column** (`brushes[0]`): a `SPIRAL_COLUMN_SIDES`-gon prism of radius
      `inner_radius` spanning the stair's full height, base at z=0, top at
      `steps*rise` (so it fills the axis all the way up).
    - **Wedge tread `k`** (`brushes[1+k]`): a convex 6-face prism whose footprint is a
      trapezoidal pie-slice — radially `inner_radius` → `inner_radius + step_width`,
      angular span `degrees_per_step` with STRAIGHT chords on the inner/outer edges
      (a convex trapezoid, not an arc) — extruded `rise` thick over
      `z ∈ [k*rise, (k+1)*rise]` and rotated `k*degrees_per_step` about the Z axis
      (the world origin / column axis). Faces: top + bottom trapezoid, inner + outer
      chord, two radial sides.

    Consecutive treads climb by exactly one `rise` (tread top `k` at `(k+1)*rise`), so
    the tops ascend strictly monotonically — a single helix, not the old slab
    mirrored-V. Everything lives in ONE local frame (column axis at the XY origin,
    base at z=0); every emitted actor shares the same `Location`, so `--at` anchors
    the base of the column axis (the bottom of the stair, on the central axis).

    Each wedge's convexity comes from `degrees_per_step < 180` (a wider slice would make
    the trapezoid non-convex) and `_face`'s Newell winding flip, NOT from `validate_brush`
    — which only rejects coincident/degenerate/non-planar faces, never non-convexity or
    inward winding. Rotation about Z is orientation-preserving and keeps each face planar
    (the trapezoids stay at constant z; the four vertical faces stay planar 2-point
    extrusions), so the flip already applied before rotation still holds after it."""
    if steps < 1:
        raise GeometryError("spiral staircase needs >= 1 step")
    if not (0 < degrees_per_step < 180):
        raise GeometryError(
            f"spiral staircase needs 0 < degrees_per_step < 180, got {degrees_per_step}")
    if inner_radius <= 0:
        raise GeometryError(
            f"spiral staircase needs inner_radius > 0, got {inner_radius}")
    total_z = steps * rise
    outer_radius = inner_radius + step_width
    step_angle = math.radians(degrees_per_step)
    half_angle = step_angle / 2.0

    column = cylinder(total_z, inner_radius, sides=SPIRAL_COLUMN_SIDES,
                      texture=texture, flags=flags)
    column = translate_brush(column, 0.0, 0.0, total_z / 2.0)  # base at z=0, not centered
    brushes = [column]

    cos_step, sin_step = math.cos(step_angle), math.sin(step_angle)

    def _with_z(corner, z):
        return (corner[0], corner[1], z)

    for k in range(steps):
        z0, z1 = k * rise, (k + 1) * rise
        p0 = (inner_radius, 0.0)                              # inner-near (angle 0)
        p1 = (outer_radius, 0.0)                              # outer-near (angle 0)
        p2 = (outer_radius * cos_step, outer_radius * sin_step)  # outer-far (angle step)
        p3 = (inner_radius * cos_step, inner_radius * sin_step)  # inner-far (angle step)
        polys = [
            _face([_with_z(p0, z0), _with_z(p1, z0), _with_z(p2, z0), _with_z(p3, z0)],
                  (0, 0, -1), texture, flags, item="Base"),
            _face([_with_z(p0, z1), _with_z(p1, z1), _with_z(p2, z1), _with_z(p3, z1)],
                  (0, 0, 1), texture, flags, item="Step"),
            _face([_with_z(p1, z0), _with_z(p2, z0), _with_z(p2, z1), _with_z(p1, z1)],
                  (math.cos(half_angle), math.sin(half_angle), 0.0), texture, flags, item="Outer"),
            _face([_with_z(p3, z0), _with_z(p0, z0), _with_z(p0, z1), _with_z(p3, z1)],
                  (-math.cos(half_angle), -math.sin(half_angle), 0.0), texture, flags, item="Inner"),
            _face([_with_z(p0, z0), _with_z(p1, z0), _with_z(p1, z1), _with_z(p0, z1)],
                  (0, -1, 0), texture, flags, item="Side"),
            _face([_with_z(p2, z0), _with_z(p3, z0), _with_z(p3, z1), _with_z(p2, z1)],
                  (-math.sin(step_angle), math.cos(step_angle), 0.0), texture, flags, item="Side"),
        ]
        wedge = Brush(model_name="Model", polys=polys)
        brushes.append(_rotate_z(wedge, k * degrees_per_step))
    return brushes


# --- actor wrapping ----------------------------------------------------------


def make_brush_actor(name: str, brush: Brush, location: Vec3 = (0.0, 0.0, 0.0),
                     csg: str = "add", group: str | None = None,
                     poly_flags: int = 0, mover_class: str | None = None) -> Actor:
    """Wrap a builder `Brush` into a CSG brush Actor ready for `writes.add_actor`.

    Sets `CsgOper` (add/subtract), an actor-level `PolyFlags` for solidity, an
    optional `Group`, the `Location`, and a `Brush=Model'MyLevel.<model>'` ref
    pointing at a per-actor-unique brush model name. (emit_actor re-emits that ref
    AFTER the inline brush block, which is what makes the brush selectable.)

    With `mover_class` set, the actor is a Mover instead: `cls` is the given FQCN and
    NO `CsgOper` is emitted (a mover does not participate in world CSG — spike 2026-06-25),
    base pose only (keyframes are added via `mover key`)."""
    b = copy.deepcopy(brush)
    b.model_name = f"Model_{name}"
    # Builders compute in float; finalize to the Decimal grid model here (the single
    # wrapper every `brush <shape>` verb passes through) so the actor handed off carries
    # exact Decimal vertices/Location like a parsed level — clean preserves fractions.
    for p in b.polys:
        p.vertices = [(clean(x), clean(y), clean(z)) for x, y, z in p.vertices]
    props: list[tuple[str, str]] = []
    if mover_class is None:
        props.append(("CsgOper", CSG_OPER[csg]))
    if poly_flags:
        props.append(("PolyFlags", str(poly_flags)))
    if group:
        props.append(("Group", group))
    props.append(("Brush", f"Model'MyLevel.{b.model_name}'"))
    # cls is already-qualified (Engine.Brush, never ambiguous on this substrate) — store the
    # same form `qualify_level_classes` would derive for an imported bare "Brush", so a
    # freshly-created actor's canonical T3D already matches what its first materialize+re-export
    # produces (2026-06-21 — see dev/docs/specs/2026-06-21-uedctl-class-qualification-design.md).
    cls = mover_class if mover_class is not None else "Engine.Brush"
    # Identity MainScale/PostScale as TYPED fields (emit_actor re-emits `(SheerAxis=SHEER_ZX)` for
    # each, matching the editor's identity-shear default) — not props strings, or emit would drop
    # them (it emits scale solely from the typed field; spec §10).
    from .transform import IDENTITY as _SCALE_IDENTITY
    return Actor(name=name, cls=cls, props=props,
                 location=(clean(location[0]), clean(location[1]), clean(location[2])),
                 brush=b, main_scale=_SCALE_IDENTITY, post_scale=_SCALE_IDENTITY)
