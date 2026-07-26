"""Shared registry + capture machinery for the builder world-geometry parity suite.

Two tests consume this:
  - test_builder_parity.py        — OFFLINE, default suite. Asserts each builder's
    world vertices still match the committed golden fixture (regression guard on
    builders.py geometry; no editor needed).
  - test_builder_parity_capture.py — `@pytest.mark.integration`, gated. Drives the
    live editor, asserts the editor's reconstructed world geometry matches the
    builder AND the fixture, and is the re-bless path for the fixture.

WHAT THIS PROVES (be honest):
  uedcli's brush builders are Python REPLICAS of UnrealEd's `BrushBuilders`, which
  are GUI-dialog-only (`WDlgBrushBuilder::OnBuild`) and NOT console-invocable — so
  the editor can NOT be asked to "build a cylinder" and there is no way to compare
  our builder ALGORITHM against UED's. What IS capturable, and what this suite
  guards, is that the geometry we EMIT for each builder round-trips through the real
  editor's importer + CSG with identical world vertices — i.e. emit/winding/world-
  transform faithfulness per shape (the "winding is load-bearing" claim in
  builders.py), frozen as a golden so CI catches builders.py regressions offline.

CAPTURE METHOD (the rotate-integration DEINTERSECTION readout, generalized):
  paste each builder brush as a CSG_Subtract (pre-shifted -32uu to cancel EDIT
  PASTE drift) -> MAP REBUILD (engine carves the world cavity) -> import a large
  enclosing CSG_Add box -> BRUSH FROM DEINTERSECTION (cavity -> active brush) ->
  BRUSH EXPORT = the cavity's world vertices. See
  dev/docs/spikes/2026-06-19-builder-world-geometry-parity.md.

NOT in the LIVE capture suite (and why):
  - sheet(): TwoSided|NotSolid, zero-volume — never carves CSG, so DEINTERSECTION
    cannot reconstruct it. Covered by its offline structural test in test_builders.
  - staircase(): now ONE non-convex brush (a combined cavity the editor can't
    reconstruct — it invents interior vertices at the notches). `stair_*` keeps its
    OFFLINE value golden (blessed from the builder, since axis-aligned integer coords
    reconstruct identically) but is dropped from the live suite — see OFFLINE_ONLY.
  - spiral_staircase: now a central column + rotated wedge (pie-slice) treads. The
    wedge coords are NOT axis-aligned integers, so the DEINTERSECTION capture invents
    vertices on them (same regime as the non-convex staircase). `spiral_*` keeps its
    OFFLINE value golden (blessed from the builder) and is dropped from the LIVE suite
    — see OFFLINE_ONLY (decisions.md 2026-07-22).
"""
from __future__ import annotations

import copy
import json
import re
import subprocess
import uuid
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

from uedcli.builders import (cube, cylinder, cone, staircase, spiral_staircase,
                             make_brush_actor)
from uedcli.emit import emit_map
from uedcli.model import Brush
from uedcli.rotation import world_vertices

FIXTURE = Path(__file__).parent / "fixtures" / "builder_parity.json"
CONTAINER = "dx-lum-uned"
PASTE_DRIFT = 32                       # EDIT PASTE adds +32uu on all axes (quirks.md)
PARITY_TOL = 1e-4                      # editor float32 vert storage + 6-dp emit floor
TEX = "DefaultTexture"
D = Decimal

# name -> zero-arg factory returning a Brush (single cavity) or list[Brush] (per-slab).
#
# What the vertex-SET comparison can and cannot catch (be precise — both reviewers
# flagged the earlier overclaim here):
#   - It catches any bug that MOVES a corner: wrong dimensions, a sign error in the
#     ring/offset math, a mis-placed step. The genuinely asymmetric `stair_*` cases
#     are the ones that catch a coordinate MIRROR (x->-x), since a centred cube /
#     cylinder / cone has a vertex set that is invariant under reflection (and under
#     any rigid transform of it), so a mirror bug in those families is invisible to a
#     set match — no case can fix that, it is intrinsic to comparing unlabelled sets.
#   - It does NOT see WINDING: the vertex set is winding-invariant. A flipped face is
#     caught only on the LIVE path, where an inverted solid makes the editor's CSG
#     reject/mis-carve it (count/err blow up) — never by the offline set match.
# The offline poly-count check (test_builder_parity) adds a cheap structural guard on
# top of the set: it catches a dropped/duplicated face that moves no unique corner.
CASES: dict[str, Callable[[], Brush | list[Brush]]] = {
    "cube_symmetric": lambda: cube(256, 256, 256, texture=TEX),
    "cube_asymmetric": lambda: cube(384, 128, 64, texture=TEX),
    "cube_thin_odd": lambda: cube(130, 70, 50, texture=TEX),
    "cyl_tri": lambda: cylinder(128, 96, sides=3, texture=TEX),
    "cyl_square": lambda: cylinder(128, 96, sides=4, texture=TEX),
    "cyl_pent": lambda: cylinder(160, 80, sides=5, texture=TEX),
    "cyl_hex_offset": lambda: cylinder(100, 80, sides=6, angle_offset=30, texture=TEX),
    "cyl_oct": lambda: cylinder(128, 96, sides=8, texture=TEX),
    "cyl_16": lambda: cylinder(200, 120, sides=16, texture=TEX),
    "cone_tri": lambda: cone(160, 96, sides=3, texture=TEX),
    "cone_square": lambda: cone(160, 96, sides=4, texture=TEX),
    "cone_pent_odd": lambda: cone(120, 72, sides=5, texture=TEX),
    "cone_hex": lambda: cone(160, 96, sides=6, texture=TEX),
    "cone_oct": lambda: cone(200, 110, sides=8, texture=TEX),
    "cone_hex_offset": lambda: cone(160, 96, sides=6, angle_offset=25, texture=TEX),
    "stair_1": lambda: staircase(1, 64, 32, 128, texture=TEX),
    "stair_2": lambda: staircase(2, 96, 48, 160, texture=TEX),
    "stair_4": lambda: staircase(4, 64, 32, 128, texture=TEX),
    "stair_8": lambda: staircase(8, 48, 24, 96, texture=TEX),
    "spiral_3": lambda: spiral_staircase(3, 64, 96, 32, degrees_per_step=30, texture=TEX),
    "spiral_4": lambda: spiral_staircase(4, 48, 112, 28, degrees_per_step=45, texture=TEX),
}

# Cases blessed OFFLINE (no live editor capture). Two families land here:
#   - stair_* — the single non-convex staircase brush: a combined non-convex cavity makes the
#     editor invent interior vertices at the notches, so `capture_world_verts` cannot reconstruct
#     it. Its axis-aligned integer coords reconstruct identically to the builder (same basis as
#     `cube_*`), so the offline VALUE golden is legitimate. (Spec 2026-07-21; decisions.md 12:06 UTC.)
#   - spiral_* — the column + rotated wedge treads: the wedge coords are NOT axis-aligned integers,
#     so the DEINTERSECTION capture invents vertices on them the same way. (decisions.md 2026-07-22.)
# For both, the offline golden is the builder's own world-vertex set — a winding-blind change-detector
# — and the case is dropped from the LIVE capture suite. A non-convex/rotated capture mode is separate
# work; the re-bless path refuses to bless on builder/editor disagreement, which is why these are
# builder-sourced rather than editor-captured.
OFFLINE_ONLY = {"stair_1", "stair_2", "stair_4", "stair_8", "spiral_3", "spiral_4"}


def _as_brushes(result) -> list:
    return result if isinstance(result, list) else [result]


def builder_world_verts(result) -> list[tuple[float, float, float]]:
    """The world vertices the builder CLAIMS (Location origin, no Rotation): the union
    over its brush(es), via the same `world_vertices` the live capture is compared to."""
    verts = set()
    for i, brush in enumerate(_as_brushes(result)):
        actor = make_brush_actor(f"BPV{i}", brush, location=(D(0), D(0), D(0)))
        verts |= {tuple(round(c, 6) for c in w) for w in world_vertices(actor)}
    return sorted(verts)


def builder_poly_count(result) -> int:
    """Total emitted faces across the builder's brush(es) — a structural guard on top
    of the vertex set: a dropped/duplicated face that moves no unique corner changes
    this but not the set."""
    return sum(len(brush.polys) for brush in _as_brushes(result))


def worst_err(predicted, observed) -> float:
    """Worst over observed corners of its nearest-predicted max-norm distance. `inf`
    if either side is empty (a vacuous match must never read as parity)."""
    if not observed or not predicted:
        return float("inf")
    return max(min(max(abs(p[i] - o[i]) for i in range(3)) for p in predicted) for o in observed)


# --- live capture (integration / regenerate only) ----------------------------


def _cpath(tag: str) -> str:
    return f"/work/bpcap_{tag}_{uuid.uuid4().hex}.t3d"


def _write_container_file(path: str, content: str) -> None:
    subprocess.run(["docker", "exec", "-i", CONTAINER, "tee", path],
                   input=content, text=True, capture_output=True, check=True)


def _read_container_file(path: str) -> str:
    return subprocess.run(["docker", "exec", CONTAINER, "cat", path],
                          text=True, capture_output=True, check=True).stdout


def _parse_world_verts(t3d: str) -> list[tuple[float, float, float]]:
    seen = set()
    for line in t3d.splitlines():
        m = re.match(r"\s*Vertex\s+([-+0-9.]+),([-+0-9.]+),([-+0-9.]+)", line)
        if m:
            seen.add(tuple(round(float(x), 6) for x in m.groups()))
    return sorted(seen)


def _capture_one_cavity(driver, brush, name: str) -> list[tuple[float, float, float]]:
    """World vertices of ONE convex/non-convex brush carved into a fresh world."""
    actor = make_brush_actor(name, brush, location=(D(0), D(0), D(0)), csg="subtract")
    pv = [c for w in world_vertices(actor) for c in w]
    side = int(max(abs(c) for c in pv)) * 2 + 512 if pv else 768   # enclose w/ margin

    shifted = copy.deepcopy(actor)
    shifted.location = (D(-PASTE_DRIFT), D(-PASTE_DRIFT), D(-PASTE_DRIFT))
    enclosure = make_brush_actor(name + "Encl", cube(side, side, side, texture=TEX),
                                 location=(D(0), D(0), D(0)), csg="add")
    bpath, dpath = _cpath(name + "_b"), _cpath(name + "_d")
    _write_container_file(bpath, emit_map([enclosure]))

    driver.map_new()
    driver.set_grid(1, 1, 1)
    driver.set_clipboard(emit_map([shifted]))
    driver.edit_paste()
    driver.rebuild()
    driver.brush_import(bpath)
    driver.exec("BRUSH FROM DEINTERSECTION")
    driver.brush_export(dpath)
    return _parse_world_verts(_read_container_file(dpath))


def capture_world_verts(driver, name: str) -> list[tuple[float, float, float]]:
    """Editor-reconstructed world vertices for a case. A LIST builder is captured
    per-brush and unioned — a combined cavity would invent interior vertices at brush
    overlaps (spike-verified). (No LIVE case is a list builder today: `spiral_*` is
    OFFLINE_ONLY; this path stays for any future convex-list case.)"""
    verts = set()
    for i, brush in enumerate(_as_brushes(CASES[name]())):
        verts |= set(_capture_one_cavity(driver, brush, f"{name}_{i}"))
    return sorted(verts)


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text())


def regenerate(driver) -> dict:
    """Re-bless every case against the live editor and write the golden fixture. REFUSES
    to write a case whose live capture disagrees with the builder (wrong count or
    >PARITY_TOL, either direction): blessing a broken builder would poison the golden so
    the offline guard passes against it forever. A successful run is itself a full live
    parity check of every case."""
    cases = {}
    for name in CASES:
        result = CASES[name]()
        expected = builder_world_verts(result)
        if name in OFFLINE_ONLY:
            # No editor: the golden IS the builder's world-vertex set (see OFFLINE_ONLY).
            cases[name] = {"verts": [list(v) for v in expected], "polys": builder_poly_count(result)}
            print(f"{name:22s} verts={len(expected):3d} polys={cases[name]['polys']:3d} OFFLINE")
            continue
        editor = capture_world_verts(driver, name)
        err = max(worst_err(expected, editor), worst_err(editor, expected))
        if len(editor) != len(expected) or err > PARITY_TOL:
            raise AssertionError(
                f"{name}: live editor disagrees with builder (editor {len(editor)} verts, "
                f"builder {len(expected)}, worst {err:.6f}uu > {PARITY_TOL}uu) — refusing to bless")
        cases[name] = {"verts": [list(v) for v in editor], "polys": builder_poly_count(result)}
        print(f"{name:22s} verts={len(editor):3d} polys={cases[name]['polys']:3d} err={err:.6f} OK")
    fixture = {
        "_meta": {
            "substrate": CONTAINER,
            "method": "EDIT PASTE CSG_Subtract (-32uu) -> REBUILD -> enclosing CSG_Add "
                      "-> BRUSH FROM DEINTERSECTION -> BRUSH EXPORT; stair_* and spiral_* "
                      "blessed OFFLINE from the builder (non-convex / rotated wedges, not "
                      "editor-captured).",
            "parity_tol_uu": PARITY_TOL,
            "note": "`verts` are the EDITOR's world-corner reconstruction (captured against "
                    "the stripped-EditPackages UED22 substrate) EXCEPT the OFFLINE_ONLY `stair_*` "
                    "and `spiral_*` cases, whose `verts` come from the builder itself; `polys` is the builder's "
                    "emitted face count. Re-bless via "
                    "`python -m uedcli.tests.builder_parity_cases`.",
        },
        "cases": cases,
    }
    FIXTURE.write_text(json.dumps(fixture, indent=2) + "\n")
    return fixture


if __name__ == "__main__":
    from uedcli.driver import Driver

    regenerate(Driver(container=CONTAINER))
