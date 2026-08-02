"""`level doctor` — static, OFFLINE BSP/geometry issue detector.

Predicts UnrealEd CSG/BSP problems from the AUTHORED level model — no editor, no build. The
thresholds are the engine's own, reverse-engineered in
`dev/docs/spikes/2026-06-24-bsp-csg-hole-mechanism-from-binary.md` and
`...-bsp-collision-solidity-movers-from-binary.md`.

STATIC scope (rationale/MIGRATION.md, 2026-06-24 08:50): high-recall on the *single-brush-decidable* hole
causes — degenerate faces the engine drops at `FPoly::Finalize`, open/non-manifold solids
(`bspValidateBrush`'s "linked X of Y"), solidity misuse (the semisolid+portal strip), and gross
CSG-order mistakes. It does NOT enumerate build-emergent holes (slivers,
T-junction cracks, phantom collision nodes) — those need the build; that is the Phase-2 offline
BSP engine (rationale/MIGRATION.md, 2026-06-24 09:07, spec §7). The report footer says so.

Thresholds here are doctor-owned and engine-faithful; `geometry.py` (the hot write-path validator)
is deliberately NOT changed — it keeps its conservative tolerances. Only `geometry`'s stateless
vector helpers are reused.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass

from . import trunk
from .builders import PF_NOTSOLID, PF_SEMISOLID, WELD
from .geometry import _cross, _dot, _norm, _sub
from .model import Actor, Level, Vec3
from .movers import is_mover
from .vertex import weld_vertices

PF_PORTAL = 0x04000000

# Engine-faithful thresholds, kept DISTINCT (render spike §4b — they're mechanistically different,
# only coincidentally close). geometry.py's own COINCIDE_TOL/PLANAR_TOL are NOT touched.
COINCIDE_LEN = 1e-4          # FVector::NormalizeSlow size² < 1e-8 ⇒ length < 1e-4 ⇒ "same point"
COLINEAR_NORMAL_EPS = 9.999999e-05   # RemoveColinears side-plane-normal component compare (literal)
ZERO_NORMAL_SQ = 1e-8        # CalcNormal: summed fan-normal (=2·area·n̂) size² < 1e-8 ⇒ zero-area
PLANAR_TOL = 0.5             # advisory: a face this far off its own plane splits unpredictably

# Line-key quantum for the T-junction-aware watertight check. Tied to builders.WELD (the vertex
# weld grid, 1e-3 uu): welded corner coords already sit on that grid, so axis-aligned edges key
# EXACTLY; the quantum only matters for slanted/rotated edges, where an edge nearer than half the
# quantum to a supporting line groups onto it. A canonical quantized key (not fuzzy pairwise
# collinearity) keeps grouping a clean, transitive dict lookup. Pinned in test_doctor.py.
WATERTIGHT_LINE_EPS = WELD


class Severity(enum.Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


_RANK = {Severity.INFO: 0, Severity.WARN: 1, Severity.ERROR: 2}


@dataclass(frozen=True, kw_only=True)
class Finding:
    severity: Severity
    category: str          # degenerate|watertight|convex|planar|solidity|csg_order|scale
    brush: str
    message: str           # what's wrong, naming the offending value
    symptom: str           # the engine behaviour it causes (engine log string where applicable)
    fix: str               # the repair (see leveldesign/csg-and-bsp.md)
    poly: int | None = None
    item: str | None = None
    coord: tuple[float, float, float] | None = None


CATEGORIES = ("degenerate", "watertight", "convex", "planar", "solidity",
              "csg_order", "scale")


# --- model accessors -----------------------------------------------------------------------------
# Solidity can live in EITHER place: whole-brush solidity is an actor-level `PolyFlags` STRING prop
# (make_brush_actor / `--solidity`), but a sheet built by `brush build sheet` carries its
# PF_NotSolid/PF_TwoSided/PF_Portal ONLY on the per-poly flags (actor-level PolyFlags stays 0). The
# engine sees the union, so we must too — else a nonsolid/zone-portal sheet looks like a solid that
# must be watertight and trips phantom "open edge" errors (inbox 2026-07-17, board bug 1).

def _brush_polyflags(actor: Actor) -> int:
    """Effective PolyFlags the engine sees for solidity: the actor-level `PolyFlags` prop OR'd with
    every poly's own flags. Reading only the actor-level prop misses the per-poly-flagged sheets."""
    pf = 0
    for k, v in actor.props:
        if k == "PolyFlags":
            try:
                pf = int(v)
            except ValueError:
                pf = 0
            break
    if actor.brush is not None:
        for poly in actor.brush.polys:
            try:
                pf |= int(poly.flags or 0)
            except (TypeError, ValueError):
                pass
    return pf


def _csg_oper(actor: Actor) -> str:
    for k, v in actor.props:
        if k == "CsgOper":
            return v
    return "CSG_Add"


def _has_nonidentity_scale(actor: Actor) -> bool:
    # MainScale/PostScale live in the typed fields once parsed; fall back to a props scan for a
    # hand-built Actor that never went through model.parse (some unit tests).
    for fs in (getattr(actor, "main_scale", None), getattr(actor, "post_scale", None)):
        if fs is not None and not fs.is_identity():
            return True
    for k, v in actor.props:
        if k in ("MainScale", "PostScale") and "Scale=(" in v and "X=1.000000,Y=1.000000,Z=1.000000" not in v:
            return True
    return False


def _is_closed_solid_brush(actor: Actor, index) -> bool:
    """Watertightness applies to brushes meant to be closed solids: world solid/semisolid brushes
    and Mover brushes. Nonsolid (PF_NotSolid) and portal (PF_Portal) brushes — sheets, zone
    portals, volume markers — are intentionally open 2-sided surfaces, so skip them. The flags are
    read effectively (actor-level OR per-poly) so a `brush build sheet` portal, whose flags live
    only on its polys, is recognised too. `index` is the `classindex.ClassIndex` the shared
    schema-aware `movers.is_mover` gate resolves the class hierarchy against."""
    if actor.brush is None:
        return False
    cls = (actor.cls or "").rsplit(".", 1)[-1]
    if _brush_polyflags(actor) & (PF_NOTSOLID | PF_PORTAL):
        return False
    return cls == "Brush" or is_mover(actor, index)


# --- geometry helpers (float; reuse geometry.py's vector ops) ------------------------------------

def _fan_normal(verts: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    """Summed triangle-fan normal from v0 — matches the engine's CalcNormal (its magnitude is
    2·area, so size² < ZERO_NORMAL_SQ is the engine's zero-area test)."""
    if len(verts) < 3:
        return (0.0, 0.0, 0.0)
    base = verts[0]
    n = (0.0, 0.0, 0.0)
    for i in range(2, len(verts)):
        c = _cross(_sub(verts[i - 1], base), _sub(verts[i], base))
        n = (n[0] + c[0], n[1] + c[1], n[2] + c[2])
    return n


def _cleanup_count(verts: list[tuple[float, float, float]]) -> int:
    """Engine cleanup (Fix + RemoveColinears) vertex count: drop consecutive coincident vertices
    (< COINCIDE_LEN apart), then drop colinear vertices (a vertex whose two incident edges are
    parallel — its side-plane normal vanishes). Returns the surviving vertex count."""
    pts = list(verts)
    # pass 1: coincident
    out: list[tuple[float, float, float]] = []
    for p in pts:
        if out and _norm(_sub(p, out[-1])) < COINCIDE_LEN:
            continue
        out.append(p)
    if len(out) > 1 and _norm(_sub(out[0], out[-1])) < COINCIDE_LEN:
        out.pop()
    # pass 2: colinear (edge i-1→i parallel to i→i+1 ⇒ cross ~0)
    n = len(out)
    if n < 3:
        return n
    keep = []
    for i in range(n):
        a, b, c = out[(i - 1) % n], out[i], out[(i + 1) % n]
        cr = _cross(_sub(b, a), _sub(c, b))
        la, lc = _norm(_sub(b, a)), _norm(_sub(c, b))
        if la and lc and _norm(cr) / (la * lc) < COLINEAR_NORMAL_EPS:
            continue            # b is colinear → engine removes it
        keep.append(b)
    return len(keep)


def _is_convex(verts: list[tuple[float, float, float]], normal) -> bool:
    """All turns wind the same way around the face normal (colinear turns ignored)."""
    n = len(verts)
    signs = []
    for i in range(n):
        a, b, c = verts[(i - 1) % n], verts[i], verts[(i + 1) % n]
        s = _dot(_cross(_sub(b, a), _sub(c, b)), normal)
        if abs(s) > 1e-6:
            signs.append(s > 0)
    return len(set(signs)) <= 1


def _aabb(verts: list[tuple[float, float, float]]):
    xs = [p[0] for p in verts]; ys = [p[1] for p in verts]; zs = [p[2] for p in verts]
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def _aabb_overlap(a, b) -> bool:
    return (a[0] <= b[3] and b[0] <= a[3] and a[1] <= b[4] and b[1] <= a[4]
            and a[2] <= b[5] and b[2] <= a[5])


def _aabb_contains(outer, inner) -> bool:
    return (outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] <= inner[2]
            and outer[3] >= inner[3] and outer[4] >= inner[4] and outer[5] >= inner[5])


# --- checks ---------------------------------------------------------------------------------------

def check_degenerate(actor: Actor) -> list[Finding]:
    out: list[Finding] = []
    for pi, poly in enumerate(actor.brush.polys):
        verts = [(float(v[0]), float(v[1]), float(v[2])) for v in poly.vertices]
        cen = _centroid(verts)
        if _cleanup_count(verts) < 3:
            out.append(Finding(
                severity=Severity.ERROR, category="degenerate", brush=actor.name, poly=pi,
                item=poly.item, coord=cen,
                message=f"poly {pi} collapses below 3 vertices after the engine's coincident/"
                        f"colinear cleanup ({len(verts)} authored)",
                symptom="FPoly::Finalize: Not enough vertices — the face is dropped (hole/HOM, "
                        "and fall-through where it was a floor)",
                fix="rebuild the face with 3+ non-coincident, non-colinear vertices"))
            continue
        n = _fan_normal(verts)
        if _dot(n, n) < ZERO_NORMAL_SQ:
            out.append(Finding(
                severity=Severity.ERROR, category="degenerate", brush=actor.name, poly=pi,
                item=poly.item, coord=cen,
                message=f"poly {pi} has ~zero area (|2·area|²={_dot(n, n):.2e} < {ZERO_NORMAL_SQ:.0e})",
                symptom="FPoly::CalcNormal: Zero-area polygon — the face is dropped",
                fix="give the face real area or remove it"))
            continue
        nlen = _norm(n)
        off = max((abs(_dot(_sub(v, verts[0]), n)) / nlen for v in verts), default=0.0)
        if off > PLANAR_TOL:
            out.append(Finding(
                severity=Severity.WARN, category="planar", brush=actor.name, poly=pi,
                item=poly.item, coord=cen,
                message=f"poly {pi} is non-planar: a vertex is {off:.3f}uu off its own plane",
                symptom="CSG splits a non-planar face unpredictably → cracks/holes",
                fix="snap the face's vertices back onto one plane (Transform Permanently after edits)"))
        if not _is_convex(verts, n):
            out.append(Finding(
                severity=Severity.ERROR, category="convex", brush=actor.name, poly=pi,
                item=poly.item, coord=cen,
                message=f"poly {pi} is non-convex",
                symptom="CSG assumes convex faces — a concave face splits/builds wrong → hole or crash",
                fix="split the concave face into convex faces"))
    return out


def _line_key(a: tuple[float, float, float], b: tuple[float, float, float],
              ) -> tuple[tuple[int, ...], tuple[float, float, float], tuple[float, float, float]]:
    """Canonical, quantized key for the infinite line through directed edge a→b, plus the
    (unquantized) canonical direction and closest-point-to-origin for reuse. Two edges share a
    key iff they are collinear AND spatially coincident (any overlap/offset) within
    WATERTIGHT_LINE_EPS. Direction is sign-canonicalized (flipped so its first non-zero component
    is positive) so a→b and b→a key identically; the line's closest point to the origin is
    `a − (a·d̂)d̂` (which satisfies c·d̂ = 0, so a line param `t = p·d̂` maps back as `c + t·d̂`).
    Both are quantized onto the WATERTIGHT_LINE_EPS grid, giving a clean transitive dict key
    (not fuzzy pairwise collinearity)."""
    d = _sub(b, a)
    n = _norm(d)
    assert n > 0, f"_line_key: degenerate zero-length edge {a} == {b}"  # caller skips welded dups
    dhat = (d[0] / n, d[1] / n, d[2] / n)
    for comp in dhat:
        if abs(comp) > 1e-9:
            if comp < 0:
                dhat = (-dhat[0], -dhat[1], -dhat[2])
            break
    ad = _dot(a, dhat)
    c = (a[0] - ad * dhat[0], a[1] - ad * dhat[1], a[2] - ad * dhat[2])

    def q(x: float) -> int:
        return round(x / WATERTIGHT_LINE_EPS)
    key = (q(dhat[0]), q(dhat[1]), q(dhat[2]), q(c[0]), q(c[1]), q(c[2]))
    return key, dhat, c


def _watertight_line_findings(brush_name: str, dhat: tuple[float, float, float],
                              c: tuple[float, float, float],
                              edges: list[tuple[float, float, int]]) -> list[Finding]:
    """Directed-interval parity along ONE supporting line. `edges` is a list of
    (lo, hi, sign): the edge's [min,max] line-param span and its direction sign (+1 with d̂,
    −1 against). Split at every distinct breakpoint into atomic sub-intervals; for each, count
    forward `f` / backward `b` and classify in a FIXED precedence (branches are not mutually
    exclusive — order matters): (1) empty → ignore; (2) f+b>2 → non-manifold; (3) f+b==2 same
    direction → back-wound; (4) f==1,b==1 → healthy (a T-junction is still 1/1 per sub-interval);
    (5) otherwise (net imbalance) → open edge. Checking non-manifold and same-direction BEFORE
    the net-flow catch keeps a back-wound 2/0 out of the open-edge branch."""
    breakpoints: list[float] = []
    for t in sorted(t for lo, hi, _ in edges for t in (lo, hi)):
        if not breakpoints or t - breakpoints[-1] > WATERTIGHT_LINE_EPS:
            breakpoints.append(t)
    out: list[Finding] = []
    for i in range(len(breakpoints) - 1):
        s0, s1 = breakpoints[i], breakpoints[i + 1]
        mid = (s0 + s1) / 2.0
        f = sum(1 for lo, hi, sign in edges if lo < mid < hi and sign > 0)
        b = sum(1 for lo, hi, sign in edges if lo < mid < hi and sign < 0)
        if f == 0 and b == 0:
            continue
        p0 = tuple(c[j] + s0 * dhat[j] for j in range(3))
        p1 = tuple(c[j] + s1 * dhat[j] for j in range(3))
        coord = tuple(c[j] + mid * dhat[j] for j in range(3))
        if f + b > 2:
            out.append(Finding(
                severity=Severity.ERROR, category="watertight", brush=brush_name, coord=coord,
                message=f"edge {_c(p0)}–{_c(p1)} is shared by {f + b} faces (non-manifold)",
                symptom="self-intersecting/non-manifold solid → unpredictable CSG, holes",
                fix="rebuild the brush so each edge joins exactly two faces"))
        elif f + b == 2 and (f == 2 or b == 2):
            out.append(Finding(
                severity=Severity.ERROR, category="watertight", brush=brush_name, coord=coord,
                message=f"edge {_c(p0)}–{_c(p1)} is traversed the same direction by both faces "
                        f"(a face is wound backwards)",
                symptom="inverted face → inverted solid → CSG crash / HOM",
                fix="flip the reversed face's winding (it must be CCW seen from outside)"))
        elif f == 1 and b == 1:
            continue
        else:
            out.append(Finding(
                severity=Severity.ERROR, category="watertight", brush=brush_name, coord=coord,
                message=f"edge {_c(p0)}–{_c(p1)} is used by only one face (open edge)",
                symptom="not watertight (bspValidateBrush: linked < total) → leak/HOM, fall-through",
                fix="add the missing face, or fix the brush so every edge is shared by two faces"))
    return out


def check_watertight(actor: Actor, index) -> list[Finding]:
    """A closed solid is watertight iff every point of every edge line is covered by exactly one
    forward and one backward half-edge. Keying each undirected edge by its exact welded corner
    PAIR (the old approach) false-flags T-junctions: a long edge P→Q shares no key with the
    collinear chain P→M→Q, so all three read as "open". Instead group directed edges by their
    SUPPORTING LINE and check directed-interval parity along it, so a T-junction (P→Q forward,
    P→M + M→Q backward) is 1/1 on every sub-interval — while a genuine hole collinear with a
    healthy seam is still flagged on its uncovered sub-segment. See direction/generators.md (2026-07-21).

    LIMITATION (accepted): parity counts direction, not adjacency, so a real hole whose missing
    half-edge is coincidentally cancelled by an UNRELATED opposing edge on the same collinear
    sub-segment reads 1/1 and is masked — pathological non-adjacent collinear geometry, unreachable
    by realistic brushes; real build-emergent T-junction-crack detection is deferred to the Phase-2
    offline BSP. Also: breakpoints within WATERTIGHT_LINE_EPS merge, so a sub-weld line-param feature
    is invisible (already welded away in practice)."""
    if not _is_closed_solid_brush(actor, index):
        return []
    # corner identity = welded cleaned coord (NOT raw float verts — fractional brushes are CSG-native)
    corner_of: dict[tuple[int, int], Vec3] = {}
    for w in weld_vertices(actor.brush):
        for ref in w.refs:
            corner_of[ref] = w.coord
    lines: dict[tuple, dict] = {}
    for pi, poly in enumerate(actor.brush.polys):
        nv = len(poly.vertices)
        if nv < 3:
            continue
        for vi in range(nv):
            ca, cb = corner_of[(pi, vi)], corner_of[(pi, (vi + 1) % nv)]
            if ca == cb:                       # welded coincident pair → zero-length; skip
                continue
            a = tuple(float(x) for x in ca)
            b = tuple(float(x) for x in cb)
            key, dhat, c = _line_key(a, b)
            grp = lines.setdefault(key, {"dhat": dhat, "c": c, "edges": []})
            dh = grp["dhat"]                   # first edge's dhat; consistent per line group
            ta, tb = _dot(a, dh), _dot(b, dh)
            grp["edges"].append((min(ta, tb), max(ta, tb), 1 if tb > ta else -1))
    out: list[Finding] = []
    for grp in lines.values():
        out += _watertight_line_findings(actor.name, grp["dhat"], grp["c"], grp["edges"])
    return out


def check_solidity(actor: Actor) -> list[Finding]:
    out: list[Finding] = []
    pf = _brush_polyflags(actor)
    if (pf & PF_SEMISOLID) and (pf & PF_PORTAL):
        out.append(Finding(
            severity=Severity.ERROR, category="solidity", brush=actor.name,
            message="brush is both Semisolid and Portal",
            symptom="csgRebuild strips Semisolid and forces NotSolid on portals — the brush will "
                    "silently not collide",
            fix="make the wall a separate SOLID brush; a portal sheet can't provide collision"))
    return out


def check_scale(actor: Actor) -> list[Finding]:
    if _has_nonidentity_scale(actor):
        return [Finding(
            severity=Severity.INFO, category="scale", brush=actor.name,
            message="brush has a non-identity MainScale/PostScale",
            symptom="scale IS applied model-side now (bounds/preview/findings honour it); a "
                    "non-identity PostScale still distorts under `actor rotate` (inherent UE1)",
            fix="`brush apply-transform` bakes the scale into the vertices (resets the fields)")]
    return []


def check_csg_order(level: Level) -> list[Finding]:
    """Cross-brush CSG-order mistakes. Broad-phase: sort world AABBs on X and sweep."""
    from .rotation import world_vertices
    order_index = {name: i for i, name in enumerate(level.order)}
    brushes = []
    for name, a in level.actors.items():
        if a.brush is None:
            continue
        wv = world_vertices(a)
        if not wv:
            continue
        brushes.append((order_index.get(name, 1 << 30), name, a, _aabb(wv)))
    out: list[Finding] = []
    by_x = sorted(range(len(brushes)), key=lambda i: brushes[i][3][0])
    overlaps_any = [False] * len(brushes)
    for ii in range(len(by_x)):
        i = by_x[ii]
        oi, ni, ai, bi = brushes[i]
        for jj in range(ii + 1, len(by_x)):
            j = by_x[jj]
            oj, nj, aj, bj = brushes[j]
            if bj[0] > bi[3]:        # sweep: no further AABB can overlap on X
                break
            if not _aabb_overlap(bi, bj):
                continue
            overlaps_any[i] = overlaps_any[j] = True
            (eo, en, _, eb), (lo, ln, _, lb) = ((oi, ni, ai, bi), (oj, nj, aj, bj)) \
                if oi < oj else ((oj, nj, aj, bj), (oi, ni, ai, bi))
            # earlier ADD fully inside later SUBTRACT → erased
            if _csg_oper(level.actors[en]) == "CSG_Add" \
                    and _csg_oper(level.actors[ln]) == "CSG_Subtract" \
                    and _aabb_contains(lb, eb):
                out.append(Finding(
                    severity=Severity.WARN, category="csg_order", brush=en,
                    message=f"additive brush {en!r} is inside later subtractive brush {ln!r}",
                    symptom="the add is carved away by the later subtract (last op wins) → it "
                            "vanishes from the build",
                    fix=f"send {en!r} To Last (or {ln!r} To First) so the add survives"))
    for i, (oi, ni, ai, bi) in enumerate(brushes):
        if _csg_oper(level.actors[ni]) == "CSG_Subtract" and not overlaps_any[i]:
            out.append(Finding(
                severity=Severity.INFO, category="csg_order", brush=ni,
                message=f"subtractive brush {ni!r} overlaps no other brush",
                symptom="a subtract that carves nothing — usually a misplaced or stray brush",
                fix="move it where it should carve, or delete it"))
    return out


def check_duplicate_order(ranks: dict[str, str]) -> list[Finding]:
    """Actors sharing an order_value: CSG precedence among them falls to the name tiebreak, not
    author intent (git-native model, spec §5). One WARN finding per shared-value group. Takes the
    trunk `order_value` sidecar map (not a `Level`, which doesn't carry it) — composed into the
    doctor report at the dispatch seam, NOT part of `run_doctor(level)`."""
    out: list[Finding] = []
    for value, names in trunk.duplicate_ranks(ranks):
        detail = (f"share order_value {value!r}" if value
                  else "have no order_value (empty sidecar)")
        out.append(Finding(
            severity=Severity.WARN, category="csg_order", brush=names[0],
            message=f"actors {', '.join(names)} {detail}",
            symptom="their CSG precedence is decided by the actor-name tiebreak, not author intent",
            fix="give them distinct order_values (reorder) so the intended CSG order is explicit"))
    return out


# --- driver ---------------------------------------------------------------------------------------

def sort_findings(findings: list[Finding]) -> list[Finding]:
    """Stable report order: severity desc, then brush, then poly. Shared by `run_doctor` and the
    dispatch seam that appends `check_duplicate_order` (so a brush with both a geometry finding and a
    dup-order finding groups under ONE `brush:` block, not two)."""
    findings.sort(key=lambda f: (-_RANK[f.severity], f.brush, f.poly if f.poly is not None else -1))
    return findings


def run_doctor(level: Level, index) -> list[Finding]:
    """Every static check over `level`. `index` is a `classindex.ClassIndex` (the game's `.u` class
    hierarchy): the watertight check must know which brushes are Movers, and mover-ness is decided
    schema-aware by `movers.is_mover`, so `level doctor` REQUIRES a class resolver — an absent games
    config is a clean exit 2 at the dispatch seam, never a degraded report (direction/conventions.md 2026-07-25
    10:18 UTC)."""
    findings: list[Finding] = []
    for a in level.actors.values():
        if a.brush is None:
            continue
        findings += check_degenerate(a)
        findings += check_watertight(a, index)
        findings += check_solidity(a)
        findings += check_scale(a)
    findings += check_csg_order(level)
    return sort_findings(findings)


def worst(findings: list[Finding]) -> Severity | None:
    return max((f.severity for f in findings), key=lambda s: _RANK[s], default=None)


_FOOTER = (
    "Static analysis: high-recall on per-brush hole causes (degenerate faces, open solids, "
    "solidity misuse, gross CSG order). It does NOT find build-emergent holes (slivers, "
    "T-junction cracks, phantom collision nodes) — those need the offline BSP build (Phase 2). "
    "A clean run is not a built-hole-free guarantee."
)


def format_report(findings: list[Finding], level_name: str | None) -> str:
    name = level_name or "(unnamed level)"
    if not findings:
        return f"{name}: no issues found.\n\n{_FOOTER}"
    counts = {s: sum(1 for f in findings if f.severity is s) for s in Severity}
    head = (f"{name}: {len(findings)} finding(s) — "
            f"{counts[Severity.ERROR]} error, {counts[Severity.WARN]} warn, "
            f"{counts[Severity.INFO]} info")
    lines = [head, ""]
    cur = None
    for f in findings:
        if f.brush != cur:
            cur = f.brush
            lines.append(f"{f.brush}:")
        loc = f" @{_c(f.coord)}" if f.coord else ""
        pol = f" poly {f.poly}" if f.poly is not None else ""
        lines.append(f"  [{f.severity.value.upper():5}] {f.category}{pol}{loc}: {f.message}")
        lines.append(f"          → {f.symptom}")
        lines.append(f"          fix: {f.fix}")
    lines += ["", _FOOTER]
    return "\n".join(lines)


def _centroid(verts):
    n = len(verts)
    if not n:
        return None
    return tuple(sum(p[i] for p in verts) / n for i in range(3))


def _c(coord) -> str:
    if coord is None:
        return "-"
    def f(x):
        x = float(x)
        return str(int(round(x))) if abs(x - round(x)) < 1e-6 else f"{x:.3f}"
    return f"({f(coord[0])},{f(coord[1])},{f(coord[2])})"
