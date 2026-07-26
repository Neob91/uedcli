"""Model-side brush builders — the fixed parametric shapes (cube / cylinder / cone /
sheet / staircase / spiral staircase) plus the two 2D-PROFILE SWEEPS (extrude /
revolve), UnrealEd's 2D-shape-editor method: the caller draws a closed polygon and
this module sweeps it, straight (`extrude`) or around an in-plane axis (`revolve`).
The purely 2D half of that — parsing, cleanup, validity, winding, and the convex
decomposition of a cap — lives in `profile.py`.

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
from .geometry import GeometryError, validate_brush
from .model import Actor, Brush, Polygon, Vec3
# Two vertices closer than WELD collapse to one (drop zero-length ring edges). The constant lives
# in `profile.py` (which has no builders import), NOT here: this module's own names are defined
# BELOW its import block, so the reverse direction would be a load-time cycle. Re-exported for the
# existing importers (`doctor.py`).
from .profile import WELD

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


_DIR_EPS = 1e-12


def _denoise(v: Vec3) -> Vec3:
    """Snap a UNIT direction's float noise to exact 0/±1 components.

    Not cosmetic. `_tex_basis` seeds from `min(range(3), key=lambda i: abs(normal[i]))` — the world axis least aligned
    with the normal — so when two components tie, which one wins is decided by whatever sits in
    the last bits. A computed normal that lands on `-0.0` or `1e-17` where an analytic one gave
    exact `0.0` can therefore flip the seed and rotate the whole in-plane texture basis by 90°,
    which is visible in the built map as a rotated texture on that face. Snapping first makes the
    choice a function of the geometry rather than of accumulated rounding.
    """
    out = []
    for c in v:
        for target in (0.0, 1.0, -1.0):
            if abs(c - target) < _DIR_EPS:
                c = target
                break
        out.append(c)
    return (out[0], out[1], out[2])


def _tex_basis(normal: Vec3):
    """Unit in-plane (TextureU, TextureV) for a face. Zero-length texture vectors
    crash REBUILD, so seed from the world axis least aligned with the normal.

    **Ties resolve to the LOWEST axis index**, via `min`'s first-wins rule. That is not an
    accident to be tidied away: an axis-aligned normal like `(0,0,1)` ties on X and Y, so every
    axis-aligned face every builder emits depends on it, and changing it would re-project textures
    across the whole tool. What PINS it is the committed T3D goldens, which are self-blessed —
    the editor-blessed parity fixtures (`builder_parity.json`) carry only vertices and a poly
    count, no texture vectors, so they do NOT constrain this choice against the real editor. `_denoise` makes ties MORE common by design (a snapped
    component is exactly 0.0, where a residue would have broken the tie arbitrarily), which is
    the point: the basis becomes a function of the geometry rather than of rounding.
    """
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


# --- swept 2D profiles: extrude ----------------------------------------------
#
# A PROFILE is the closed 2D polygon the author draws (`--point U,V`, repeatable); a sweep turns it
# into one brush. The 2D layer (parsing, cleanup, winding, convex decomposition) is `profile.py`;
# what lives here is the 2D→3D part: the sweep frame, the swept vertices, and the per-face OUTWARD
# directions `_face` winds against.


# The right-handed sweep frame per `--axis`: `(u_world, v_world, w_world)`, where `w` is the
# `--axis` direction the sweep grows along and `(u, v)` are the profile's own 2D axes on the two
# remaining world axes, cycled so `u × v = +axis` in every case. Cycling right-handed is what lets
# ONE winding rule (a counter-clockwise profile in `(u,v)`) serve all three orientations. This
# table is the single place the mapping is written.
_SWEEP_FRAMES = {
    #        u              v              w = --axis
    "z": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),   # u→X, v→Y, sweep +Z
    "x": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),   # u→Y, v→Z, sweep +X
    "y": ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),   # u→Z, v→X, sweep +Y
}


def _uv_axes(axis: str):
    """The `(u_world, v_world, w_world)` unit triple for `--axis` (see `_SWEEP_FRAMES`)."""
    try:
        return _SWEEP_FRAMES[axis]
    except KeyError:
        raise GeometryError(f"sweep axis must be x|y|z, got {axis!r}") from None


def _sweep_point(u: float, v: float, w: float, frame) -> Vec3:
    """A point of the sweep frame in world coordinates: `u·û + v·v̂ + w·ŵ`."""
    U, V, W = frame
    return (u * U[0] + v * V[0] + w * W[0],
            u * U[1] + v * V[1] + w * W[1],
            u * U[2] + v * V[2] + w * W[2])


def extrude(points, depth: float, axis: str = "z",
            texture=None, flags: int = 0) -> Brush:
    """Sweep a closed 2D `points` profile a straight `depth` along `+axis` — ONE brush.

    `points` is a sequence of `(u, v)` pairs in the profile's own 2D coordinate system (any numeric
    type; converted to float here, since `_newell`/`_tex_basis` are float-only — nothing is lost, as
    `make_brush_actor`'s `emit.clean` re-Decimalizes). The ring is implicitly closed and may be
    wound either way: it is normalized counter-clockwise first, so the per-face outward directions
    below hold regardless of the order the author typed.

    The local vertices are the authored profile coordinates VERBATIM (no re-centering), with the
    sweep running `w ∈ [0, depth]`, so the actor's `Location` — `brush build --at` — is the world
    point that profile coordinate `(0,0)` lands on.

    Faces, `n` = the profile's vertex count after cleanup:
      - `Cap` at `w = 0`, facing `−axis`, and `Cap` at `w = depth`, facing `+axis`. Each is ONE
        face when the profile is convex and ≤16 vertices, else one face per convex piece (§
        `profile.convex_pieces`), so the total is `n + 2·pieces`.
      - `Side<k>`, one quad per profile edge `k`, spanning the full sweep. The per-edge item name
        (rather than a single `Side`) is what keeps `brush poly find --item Side0` meaningful — it
        selects "the face swept by my first profile edge".

    Unlike the parametric shapes, a swept profile's vertices come from arbitrary user input, so the
    brush is `geometry.validate_brush`-checked HERE: `brush build` itself does not validate geometry
    (that happens downstream at `actor add`), and generator output can bypass `actor add` entirely
    (`> file.t3d`, `| brush intersect`).
    """
    from . import profile as profile2d          # function-local: see the WELD note at the imports
    if not (depth > 0):
        raise GeometryError(f"extrude needs depth > 0, got {depth}")
    frame = _uv_axes(axis)
    ring = profile2d.normalize_winding([(float(u), float(v)) for u, v in points])
    pieces = profile2d.convex_pieces(ring)
    W = frame[2]
    inward_cap = (-W[0], -W[1], -W[2])
    far = float(depth)

    def at(p, w):
        return _sweep_point(p[0], p[1], w, frame)

    polys = [_face([at(p, 0.0) for p in piece], inward_cap, texture, flags, item="Cap")
             for piece in pieces]
    polys += [_face([at(p, far) for p in piece], W, texture, flags, item="Cap")
              for piece in pieces]
    n = len(ring)
    for k in range(n):
        a, b = ring[k], ring[(k + 1) % n]
        du, dv = b[0] - a[0], b[1] - a[1]
        # The outward of the quad swept by a CCW edge (du, dv) is its in-plane right normal
        # (dv, −du), mapped through the sweep frame.
        outward = _sweep_point(dv, -du, 0.0, frame)
        polys.append(_face([at(a, 0.0), at(b, 0.0), at(b, far), at(a, far)],
                           outward, texture, flags, item=f"Side{k}"))
    brush = Brush(model_name="Model", polys=polys)
    validate_brush(brush)
    return brush


def _rotate_about_v(vec, theta: float):
    """Rotate a SWEEP-FRAME vector `(x_u, x_v, x_w)` about the `v̂` axis by `theta` radians — the
    revolve's own rotation, in the frame where it is a plain 2D turn in the `(u, w)` plane. `û`
    goes to `(cos θ, 0, sin θ)`, matching the sweep map, so `ŵ` goes to `(−sin θ, 0, cos θ)`."""
    c, s = math.cos(theta), math.sin(theta)
    return (vec[0] * c - vec[2] * s, vec[1], vec[0] * s + vec[2] * c)


def revolve(points, angle_deg: float, segments: int, axis: str = "z",
            texture=None, flags: int = 0) -> Brush:
    """Sweep a closed 2D `points` profile `angle_deg` around an in-plane axis in `segments` flat
    facets — ONE brush, like UnrealEd's own 2D shape editor (never one brush per facet).

    **The revolve axis is the profile plane's own `v` axis — the line `u = 0`, through profile
    coordinate `(0,0)`.** There is no separate pivot: distance from the axis is written in the
    profile coordinates themselves, so a profile drawn at `u ∈ [64, 192]` revolves at radii 64 to
    192, and the actor's `Location` (`--at`) is the world position of the BEND CENTRE. The profile
    must lie strictly on the positive-`u` side; the sweep then grows toward `+axis`, exactly like
    `extrude`, so both verbs share one mental model. (A negative-`u` profile would bulge toward
    `−axis` under the same rotation, silently inverting that model and every outward direction
    below — mirror the profile's `u` values instead.)

    With `n` profile vertices and `s` segments: `n × s` swept quads, plus a tiled cap at each end.
    Every swept quad is planar (a straight edge swept by a rotation about a coplanar axis always
    is). At `angle_deg == 360` the sweep closes on itself: both caps are omitted and the last
    segment's far ring IS the first segment's near ring, so no vertex column is duplicated.

    **The per-face outward directions rotate with their faces — except the near cap.** `_face`
    flips any ring whose winding disagrees with the hint it is given, so a stale hint emits a
    backwards-wound face (an inverted solid: CSG crash or hall-of-mirrors, and unrecoverable in
    UnrealEd, which derives the face from the winding alone):

      - **near cap** (`θ = 0`): `−ŵ`, IDENTICAL to extrude's — the cap lies in the `(û, v̂)` plane
        and the solid grows toward `+ŵ`, so nothing has rotated yet;
      - **far cap** (`θ = angle`): `+ŵ` rotated by `angle` (at 90° that is `−û`, perpendicular to
        the extrude hint — a hint 90° off leaves the flip sign-indeterminate AND makes `_tex_basis`
        derive the texture axes from a non-face normal);
      - **side quad of edge `k` in segment `m`**: the quad's OWN normal, computed from the
        emitted ring and oriented outward using the segment's mid-angle direction. It is NOT the
        rotated 2D edge normal — see the comment at that loop for why that shortcut is inexact on
        a slanted profile edge, and why the error shows up in the texture basis rather than in
        the winding.

    `ItemName`s are `Cap` and `Side<k>`, the latter keyed to the PROFILE EDGE and therefore the
    same in every segment: `brush poly find --item Side0` selects the whole strip swept by the
    first profile edge. A single `Side` would leave a curved corridor's inner and outer walls with
    no selector at all (both read as `slant` to `--facing`).
    """
    from . import profile as profile2d          # function-local: see the WELD note at the imports
    if segments < 1:
        raise GeometryError(f"revolve needs segments >= 1, got {segments}")
    if not (0 < angle_deg <= 360.0):
        raise GeometryError(f"revolve needs 0 < angle_deg <= 360, got {angle_deg}")
    closed = abs(angle_deg - 360.0) < 1e-9
    # Checked before the per-facet rule, which a 1- or 2-segment full turn also trips — the
    # specific message wins, and this guard would otherwise be unreachable.
    if closed and segments < 3:
        raise GeometryError(f"a closed revolve needs segments >= 3, got {segments}")
    if angle_deg / segments >= 180.0:
        raise GeometryError(f"revolve needs a facet under 180 degrees, got "
                            f"{angle_deg / segments} ({angle_deg} over {segments} segments)")
    ring = profile2d.normalize_winding([(float(u), float(v)) for u, v in points])
    for i, (u, v) in enumerate(ring):
        if u <= 0:
            raise GeometryError(f"revolve needs every profile point strictly off the axis "
                                f"(u > 0), got point {i} at ({u},{v})")
    frame = _uv_axes(axis)
    total = math.radians(angle_deg)
    step = total / segments

    def world(uvw):
        return _sweep_point(uvw[0], uvw[1], uvw[2], frame)

    def at(p, theta):
        c, s = math.cos(theta), math.sin(theta)
        return world((p[0] * c, p[1], p[0] * s))

    polys = []
    if not closed:
        pieces = profile2d.convex_pieces(ring)
        # Both cap hints are denoised for the same reason the side quads are: `_rotate_about_v`
        # leaves a float residue (at 180° it returns (-1.22e-16, 0, -1)), and `_tex_basis` seeds
        # from the least-aligned world axis, so that residue alone can pick a different seed for
        # the far cap than for the near one — two parallel planes ending up with texture bases
        # 90° apart. Verified before this snap: near cap TextureU (1,0,0), far cap (0,1,0).
        near_hint = _denoise(world((0.0, 0.0, -1.0)))
        far_hint = _denoise(world(_rotate_about_v((0.0, 0.0, 1.0), total)))
        polys += [_face([at(p, 0.0) for p in piece], near_hint,
                        texture, flags, item="Cap") for piece in pieces]
        polys += [_face([at(p, total) for p in piece], far_hint,
                        texture, flags, item="Cap") for piece in pieces]
    rings = [[at(p, m * step) for p in ring]
             for m in range(segments if closed else segments + 1)]
    n = len(ring)
    for k in range(n):
        a, b = ring[k], ring[(k + 1) % n]
        du, dv = b[0] - a[0], b[1] - a[1]
        for m in range(segments):
            r0, r1 = rings[m], rings[(m + 1) % len(rings)]
            quad = [r0[k], r0[(k + 1) % n], r1[(k + 1) % n], r1[k]]
            # The hint is the quad's OWN normal, computed from the emitted ring. The obvious
            # shortcut — the 2D edge normal `(dv, −du)` turned by the facet's mid-angle — is NOT
            # the true normal: de-rotated, the quad's normal is proportional to
            # `(dv, −du·cos(Δ/2))` for a facet of angle Δ, so the two agree only when `du == 0`
            # or `dv == 0` (an axis-parallel profile edge). On any slanted edge — a tapered
            # column, a chamfered arch ring — the shortcut is off by `90° − 2·atan(√cos(Δ/2))`,
            # which is 0.56° at the default 22.5° facet, 2.27° at 45° and 9.88° at 90° (it only
            # approaches Δ/2 as Δ→180°). Small, but it does not wash out. That never
            # mis-WINDS the face (`_dot(nw, shortcut) = dv² + du²·cos(Δ/2) > 0` always, which is
            # why `doctor` and a signed-volume check both stay silent), but `_face` also feeds
            # the hint to `_tex_basis`, and the editor PRESERVES TextureU/TextureV while
            # recomputing `Normal` — so the error survives into the built map as a texture basis
            # tilted out of the face plane. The mid-angle direction is still used, but only to
            # ORIENT the computed normal outward, where its sign is all that matters.
            radial = world(_rotate_about_v((dv, -du, 0.0), (m + 0.5) * step))
            outward = _denoise(_normalize(_newell(quad)))
            if _dot(outward, radial) < 0:
                outward = _mul(outward, -1.0)
            polys.append(_face(quad, outward, texture, flags, item=f"Side{k}"))
    brush = Brush(model_name="Model", polys=polys)
    validate_brush(brush)
    return brush


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
    but the COARSE native core assumes convex brushes
    (`uedctl-native/src/csg.rs` `point_in_convex`), so `level preview --native` and
    the coarse core behind `level preview --native` mis-classifies its concave notches. Native
    materialize's DEFAULT core (`bspcsg`, the incremental bspBrushCSG port) never calls
    `point_in_convex` and is unaffected — see architecture.md."""
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
    # An INTERNAL-API guard, naming the PARAMETER in its own units. The CLI can no longer reach it:
    # `brush build spiral --angle-per-step` is checked in unreal rotation units at the dispatch
    # boundary, naming that flag and the value the user typed (decisions.md 2026-07-25 02:30 UTC,
    # D12). It stays for the direct callers D11 keeps — `tests/builder_parity_cases.py` and
    # `native/csg_golden.py` — and is exercised directly by `test_profile_generators.py`.
    if not (0 < degrees_per_step < 180):
        raise GeometryError(
            f"spiral_staircase needs 0 < degrees_per_step < 180 (degrees), got {degrees_per_step}")
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
