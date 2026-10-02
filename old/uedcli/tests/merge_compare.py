"""Face-set comparison for `brush intersect`/`deintersect` — shared by the offline and live tests.

The fidelity bar is **T3D face-set parity with UnrealEd's own `BRUSH FROM INTERSECTION`/
`DEINTERSECTION`** — not byte-identity: the operation's output is a builder polylist, not an
on-disk `UModel`, so there is nothing to byte-diff.

Two things this has to normalize away, or a correct result would read as a mismatch:

* **WORLD position, not raw vertices.**  The editor's export is `Location=0` + world-space
  vertices; the native verb's default `--origin center` emits rebased vertices plus a `Location`.
  Both sides are therefore reduced to WORLD space before diffing.  (The native side here is taken
  pre-`recenter`, which is exactly what `--origin keep` emits.)
* **Editor-internal PolyFlags.**  A real editor export carries scratch bits the CSG descent sets —
  `PF_EdProcessed` (`0x40000000`) shows up on every exported face.  Both sides are masked with
  `brushcsg.POLY_FLAG_MASK`, the same mask that keeps those bits out of the trunk.

Faces are compared as a SET (a multiset of canonical signatures), not as an ordered list: the ring
is rotated to start at its smallest vertex so a different-but-equivalent winding start does not
register as a difference.  Orientation IS significant — the ring is never reversed — because a
flipped normal is a real defect (it is what distinguishes a deintersect plug from its cavity).
"""
from __future__ import annotations

from pathlib import Path

from uedcli import brushcsg
from uedcli.model import parse_t3d
from uedcli.tests import intersect_cases

FIXTURES = Path(__file__).parent / "fixtures" / "intersect"

# f32 CSG output is exact on these axis-aligned cases, but quantize anyway so a 1-ULP difference in
# a rotated case cannot flip a correct result to a failure.  1e-3 uu is far below anything visible
# (the editor's own grid is 1 uu) and far above f32 noise at these magnitudes.
QUANT = 1000.0


def _q(v) -> tuple:
    return tuple(round(float(c) * QUANT) / QUANT for c in v)


def _canonical_ring(verts) -> tuple:
    """Rotate the ring to start at its smallest vertex, preserving winding direction."""
    ring = [_q(v) for v in verts]
    if not ring:
        return ()
    i = min(range(len(ring)), key=lambda k: ring[k])
    return tuple(ring[i:] + ring[:i])


def _signature(poly, *, location=(0, 0, 0)) -> tuple:
    """A face's identity for the diff: world ring + normal + texture mapping + masked flags."""
    off = [float(c) for c in location]
    world = [tuple(float(v[k]) + off[k] for k in range(3)) for v in poly.vertices]
    origin = poly.origin
    return (
        _canonical_ring(world),
        _q(poly.normal or (0, 0, 0)),
        _q(tuple(float(origin[k]) + off[k] for k in range(3))) if origin else None,
        _q(poly.texture_u or (0, 0, 0)),
        _q(poly.texture_v or (0, 0, 0)),
        int(poly.flags or 0) & brushcsg.POLY_FLAG_MASK,
        poly.texture,
        tuple(poly.pan) if poly.pan else None,
    )


def native_faces(case_id: str):
    """The native merge for a case, as world-space signatures (the `--origin keep` form)."""
    case = intersect_cases.CASES[case_id]
    actors = intersect_cases.build_actors(case_id)
    pairs = brushcsg.merge(actors, deintersect=case["verb"] == "deintersect")
    return [_signature(p) for p, _src in pairs]


def oracle_faces(t3d: str):
    """The editor golden's faces as world-space signatures."""
    level = parse_t3d(t3d)
    actor = next(iter(level.actors.values()))
    loc = actor.location or (0, 0, 0)
    return [_signature(p, location=loc) for p in actor.brush.polys]


def native_links(case_id: str) -> list[int]:
    """The native result's per-face `iLink` (the surf-share representative), in RESULT ORDER.

    Read straight off the FFI tuple rather than the emitted T3D, because uedcli's `Polygon` model
    has never carried `Link` — see `oracle_links`.
    """
    import uedcli_native
    from uedcli.native.brush_marshal import _build_brush_input

    case = intersect_cases.CASES[case_id]
    actors = intersect_cases.build_actors(case_id)
    world, builder = brushcsg.build_scaffolding(
        actors, deintersect=case["verb"] == "deintersect")
    faces = uedcli_native.intersect_brushset(
        [_build_brush_input(a.name, a) for a in world],
        _build_brush_input(builder.name, builder))
    return [f[6] for f in faces]                       # tuple slot 6 = i_link


def oracle_links(t3d: str) -> list[int]:
    """The editor golden's `Link=` values in file order.

    Parsed from the raw text: `Polygon.Link` is not part of uedcli's model (nothing in the tool
    emits or stores it), so `parse_t3d` would drop it. The values still pin the finalize renumber
    (`bspcsg::renumber_result_ilinks`) against the editor, which a face-SET comparison cannot see.
    """
    import re

    return [int(m) for m in re.findall(r"Begin Polygon[^\n]*\bLink=(\d+)", t3d)]


def load_golden_text(case_id: str) -> str:
    path = FIXTURES / f"{case_id}.t3d"
    if not path.exists():
        raise FileNotFoundError(
            f"missing golden {path} — regenerate with `UEDCLI_REGEN_GOLDENS=1 bin/test "
            f"uedcli/tests/test_integration_intersect_oracle.py -m integration`")
    return path.read_text()


def load_golden(case_id: str):
    return oracle_faces(load_golden_text(case_id))


def assert_same_faces(got, want, *, what: str) -> None:
    from collections import Counter

    cg, cw = Counter(got), Counter(want)
    if cg == cw:
        return
    missing = list((cw - cg).elements())
    extra = list((cg - cw).elements())
    lines = [f"{what}: face sets differ ({len(got)} native vs {len(want)} golden polys)"]
    for tag, faces in (("MISSING (golden has, native does not)", missing),
                       ("EXTRA (native has, golden does not)", extra)):
        if faces:
            lines.append(f"  {tag}:")
            for f in faces[:8]:
                lines.append(f"    ring={f[0]} normal={f[1]} flags={f[5]:#x} tex={f[6]}")
            if len(faces) > 8:
                lines.append(f"    … and {len(faces) - 8} more")
    raise AssertionError("\n".join(lines))
