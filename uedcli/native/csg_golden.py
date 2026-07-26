"""Editor-golden differential capture for the native CSG/BSP port.

Freezes what UnrealEd's `MAP REBUILD` actually builds for a small discriminating
CSG corpus, so the Rust CSG port (see
`dev/docs/spikes/2026-07-15-native-materialize/sections/10-bsp-csg-build.md`) can be
validated OFFLINE against real editor output.

The golden per case is the built `UModel` **surf set** — for each surf: its plane
normal + signed offset (`normal · base_point`, so winding/facing is encoded) and the
cleaned vertex-coord set of the node poly(s) that reference it — plus node/leaf/surf
(and pool) counts.

Capture path (integration; needs a live editor):
  * mint an EPHEMERAL editor (`editor.ensure_editor` with a fresh uuid7); NEVER touch
    the standing `dx-lum-uned` container,
  * author each brush as a CSG actor T3D (`builders.make_brush_actor` + `emit.emit_map`),
  * `MAP NEW` → `MAP GRID 1,1,1` → clipboard + `EDIT PASTE` (brushes MUST enter via
    EDIT PASTE — an IMPORTADD brush is skipped by CSG entirely, unrealed/quirks.md;
    pre-shift every actor -32uu to cancel the +32uu EDIT PASTE drift) → `MAP REBUILD`,
  * `MAP SAVE` the .dx, copy the bytes to the host, parse the largest Model export
    (`native.pkg_write.parse_package` + `native.umodel.parse_model_body`),
  * extract the surf set + counts.

`regenerate()` drives the whole corpus over ONE ephemeral editor (each case built
>=2x and asserted coord-stable before freezing) and writes one JSON fixture per case
under `tests/fixtures/csg_golden/`. `compare()` is the offline comparator the Rust
port's output is checked against.
"""
from __future__ import annotations

import copy
import json
import subprocess
import uuid
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from ..builders import (PF_NOTSOLID, PF_SEMISOLID, cube, cylinder,
                        make_brush_actor)
from ..emit import emit_map
from ..model import Actor
from . import pkg_write, umodel

# --- constants ---------------------------------------------------------------

PASTE_DRIFT = 32                       # EDIT PASTE adds +32uu on all axes (quirks.md)
PF_PORTAL = 0x04000000                 # actor-level Portal flag (spec §5)

# Rounding for the frozen fixture keys. THRESH_POINTS_ARE_SAME=0.002 /
# THRESH_NORMALS_ARE_SAME=2e-5 (spec §2) are the editor's own coincidence thresholds;
# we round finer than that so the freeze is exact but the comparator tolerances (below)
# absorb float32 noise.
_NORMAL_DP = 6
_OFFSET_DP = 3
_VERT_DP = 3

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "csg_golden"
D = Decimal


# --- corpus ------------------------------------------------------------------
# Each entry: name -> zero-arg factory returning the list of CSG brush actors in
# ACTOR ORDER (== CSG precedence: a later op wins). No texture is bound (geometry-
# only capture), so no OBJ LOAD / content package is needed.

def _subtract(name, brush, loc=(0, 0, 0), **kw):
    return make_brush_actor(name, brush, location=(D(loc[0]), D(loc[1]), D(loc[2])),
                            csg="subtract", **kw)


def _add(name, brush, loc=(0, 0, 0), **kw):
    return make_brush_actor(name, brush, location=(D(loc[0]), D(loc[1]), D(loc[2])),
                            csg="add", **kw)


def _case_single_subtract():
    # (a) one subtracted box carved into the solid world -> a single empty room.
    return [_subtract("RoomA", cube(512, 512, 256))]


def _case_offgrid_wedge():
    # (b) a subtracted box PLUS a subtracted off-grid brush (a triangular prism with
    # irrational, non-integer-plane vertices) poking through the -X wall -> off-grid
    # split points / cracks. The prism straddles x=-256 (the room's -X wall).
    return [
        _subtract("RoomB", cube(512, 512, 256)),
        _subtract("Wedge", cylinder(300, 96, sides=3, angle_offset=15), loc=(-256, 0, 0)),
    ]


def _case_add_in_subtract():
    # (c) the 11-vs-10 add-in-subtract case: subtract a big box, then CSG_Add a smaller
    # solid box floating inside it (a pillar).
    return [
        _subtract("RoomC", cube(512, 512, 256)),
        _add("Pillar", cube(128, 128, 128)),
    ]


def _case_abutting_subtracts():
    # (d) two abutting subtracts sharing a face (the annihilation 11-vs-10 case, spec
    # §6.5): two 256^3 rooms meeting at the x=0 plane. The shared wall faces annihilate.
    return [
        _subtract("RoomD1", cube(256, 256, 256), loc=(-128, 0, 0)),
        _subtract("RoomD2", cube(256, 256, 256), loc=(128, 0, 0)),
    ]


def _case_semisolid_detail():
    # (e) a semisolid detail Add brush (processed in PASS B) inside a carved room.
    return [
        _subtract("RoomE", cube(512, 512, 256)),
        _add("Detail", cube(128, 128, 128), poly_flags=PF_SEMISOLID),
    ]


def _case_portal():
    # (f) a portal brush: a thin Add box spanning the room at z=0 -> a zone portal.
    return [
        _subtract("RoomF", cube(512, 512, 256)),
        _add("Portal", cube(512, 512, 8), poly_flags=PF_PORTAL),
    ]


CORPUS = {
    "a_single_subtract": _case_single_subtract,
    "b_offgrid_wedge": _case_offgrid_wedge,
    "c_add_in_subtract": _case_add_in_subtract,
    "d_abutting_subtracts": _case_abutting_subtracts,
    "e_semisolid_detail": _case_semisolid_detail,
    "f_portal": _case_portal,
}


# --- .dx / UModel parsing ----------------------------------------------------

def _find_model_export(buf: bytes) -> tuple[int, int]:
    """(serial_offset, serial_size) of the LARGEST `Model`-class/name export — the level
    BSP model. Raises if none is present."""
    pp = pkg_write.parse_package(buf)
    best = None
    for i, e in enumerate(pp.exports):
        cls = pp.class_of_export(i)
        nm = pp.names[e["nm"]] if 0 <= e["nm"] < len(pp.names) else ""
        if (cls == "Model" or nm == "Model") and e["ssize"] > 0:
            if best is None or e["ssize"] > best[1]:
                best = (e["soff"], e["ssize"])
    if best is None:
        raise ValueError("no Model export found in the saved .dx")
    return best


def _extract_surfs(model: umodel.Model) -> list[dict]:
    """Per-surf plane (normal + signed offset) and the union of node-poly vertex coords
    that reference it, canonicalized + sorted for a deterministic freeze."""
    surf_polys: dict[int, list[list]] = defaultdict(list)
    for node in model.nodes:
        poly = []
        for j in range(node.num_vertices):
            vi = model.verts[node.i_vert_pool + j].i_vertex
            poly.append(model.points[vi])
        surf_polys[node.i_surf].append(poly)

    surfs = []
    for si, surf in enumerate(model.surfs):
        normal = model.vectors[surf.v_normal] if 0 <= surf.v_normal < len(model.vectors) else (0.0, 0.0, 0.0)
        base = model.points[surf.p_base] if 0 <= surf.p_base < len(model.points) else (0.0, 0.0, 0.0)
        offset = normal[0] * base[0] + normal[1] * base[1] + normal[2] * base[2]
        coords = set()
        for poly in surf_polys.get(si, []):
            for v in poly:
                coords.add(tuple(round(c, _VERT_DP) for c in v))
        surfs.append({
            "normal": [round(c, _NORMAL_DP) for c in normal],
            "offset": round(offset, _OFFSET_DP),
            "poly_flags": surf.poly_flags,
            "n_nodes": len(surf_polys.get(si, [])),
            "verts": sorted([list(c) for c in coords]),
        })
    # Canonical order so two captures / a native run compare position-independently.
    surfs.sort(key=lambda s: (s["normal"], s["offset"], s["verts"]))
    return surfs


def golden_from_dx(dx_bytes: bytes, case: str) -> dict:
    """Parse a saved .dx's level Model into a golden dict."""
    off, size = _find_model_export(dx_bytes)
    model = umodel.parse_model_body(dx_bytes, off, size)
    return {
        "case": case,
        "counts": {
            "vectors": len(model.vectors),
            "points": len(model.points),
            "nodes": len(model.nodes),
            "surfs": len(model.surfs),
            "verts": len(model.verts),
            "leaves": len(model.leaves),
            "zones": len(model.zones),
            "num_shared_sides": model.num_shared_sides,
        },
        "surfs": _extract_surfs(model),
    }


# --- editor driving ----------------------------------------------------------

def _dexec_write(container: str, path: str, content: str) -> None:
    subprocess.run(["docker", "exec", "-i", container, "tee", path],
                   input=content, text=True, capture_output=True, check=True)


def _cp_out(container: str, cpath: str, host_path: Path) -> None:
    subprocess.run(["docker", "cp", f"{container}:{cpath}", str(host_path)],
                   capture_output=True, text=True, check=True)


def _preshift(actors: list[Actor]) -> list[Actor]:
    """Copy each actor with its Location pre-subtracted by 32uu on all axes, to cancel
    the +32uu EDIT PASTE drift (quirks.md)."""
    out = []
    for a in actors:
        b = copy.deepcopy(a)
        lx, ly, lz = (a.location or (D(0), D(0), D(0)))
        b.location = (lx - PASTE_DRIFT, ly - PASTE_DRIFT, lz - PASTE_DRIFT)
        out.append(b)
    return out


def capture_case(driver, brush_actors: list[Actor], *, case: str = "case",
                 work_dir: str = "/work") -> dict:
    """Build one CSG case in the (already-running) editor `driver` drives and return its
    golden dict. `brush_actors` are the CSG brush Actors in actor order (CSG precedence).

    Drives: MAP NEW -> GRID 1,1,1 -> clipboard(emit_map, pre-shifted -32) -> EDIT PASTE
    -> MAP REBUILD -> MAP SAVE -> read the .dx back and parse. Dismisses the GC/blocking
    dialog defensively around the GC-triggering verbs."""
    container = driver.container
    tag = uuid.uuid4().hex[:12]
    cdx = f"{work_dir}/csg_{case}_{tag}.dx"

    driver.dismiss_blocking_dialog()
    driver.map_new()
    driver.dismiss_blocking_dialog()
    driver.set_grid(1, 1, 1)
    driver.set_clipboard(emit_map(_preshift(brush_actors)))
    driver.edit_paste()
    driver.dismiss_blocking_dialog()
    driver.rebuild()
    driver.dismiss_blocking_dialog()
    driver.map_save(cdx)
    driver.dismiss_blocking_dialog()

    host_dx = FIXTURE_DIR.parent.parent.parent / ".uedcli" / "tmp" / f"csg_{case}_{tag}.dx"
    host_dx.parent.mkdir(parents=True, exist_ok=True)
    try:
        _cp_out(container, cdx, host_dx)
        golden = golden_from_dx(host_dx.read_bytes(), case)
    finally:
        host_dx.unlink(missing_ok=True)
    return golden


# --- comparator --------------------------------------------------------------

def _normals_close(a, b, thresh: float) -> bool:
    return all(abs(a[i] - b[i]) <= thresh for i in range(3))


def _vertsets_close(a, b, thresh: float) -> bool:
    if len(a) != len(b):
        return False
    remaining = list(b)
    for va in a:
        hit = None
        for i, vb in enumerate(remaining):
            if all(abs(va[k] - vb[k]) <= thresh for k in range(3)):
                hit = i
                break
        if hit is None:
            return False
        remaining.pop(hit)
    return True


def _surf_close(a: dict, b: dict, thresh_normals: float, thresh_points: float) -> bool:
    # Offset tolerance scales a touch with distance for slanted planes (float32 base·normal).
    off_tol = max(thresh_points, 0.05)
    return (_normals_close(a["normal"], b["normal"], thresh_normals)
            and abs(a["offset"] - b["offset"]) <= off_tol
            and _vertsets_close(a["verts"], b["verts"], thresh_points))


def compare(native_golden: dict, frozen_golden: dict,
            thresh_normals: float = 2e-5, thresh_points: float = 0.002) -> tuple[bool, str]:
    """Compare a native-produced golden against a frozen editor golden. Returns
    `(ok, diff_text)`. Matches surfs by nearest oriented plane + vertex set within the
    editor's own coincidence thresholds; counts (nodes/leaves/surfs) must be exact."""
    diffs: list[str] = []
    for k in ("nodes", "leaves", "surfs"):
        nv = native_golden.get("counts", {}).get(k)
        fv = frozen_golden.get("counts", {}).get(k)
        if nv != fv:
            diffs.append(f"count {k}: native={nv} frozen={fv}")

    unmatched = list(frozen_golden.get("surfs", []))
    for ns in native_golden.get("surfs", []):
        hit = None
        for i, fs in enumerate(unmatched):
            if _surf_close(ns, fs, thresh_normals, thresh_points):
                hit = i
                break
        if hit is None:
            diffs.append(f"native surf unmatched: n={ns['normal']} off={ns['offset']} "
                         f"nv={len(ns['verts'])} flags={ns['poly_flags']:#x}")
        else:
            unmatched.pop(hit)
    for fs in unmatched:
        diffs.append(f"frozen surf unmatched: n={fs['normal']} off={fs['offset']} "
                     f"nv={len(fs['verts'])} flags={fs['poly_flags']:#x}")

    return (not diffs, "\n".join(diffs) if diffs else "identical")


# --- fixtures ----------------------------------------------------------------

def fixture_path(case: str) -> Path:
    return FIXTURE_DIR / f"{case}.json"


def load_fixture(case: str) -> dict:
    return json.loads(fixture_path(case).read_text())


def _write_fixture(case: str, golden: dict) -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    payload = dict(golden)
    payload["_meta"] = {
        "source": "UnrealEd MAP REBUILD (Balance=50 PortalBias=70 Optimization=OPTIMAL)",
        "capture": "native.csg_golden.regenerate — ephemeral editor, EDIT PASTE CSG "
                   "(-32uu) -> MAP REBUILD -> MAP SAVE; parsed via native.umodel.",
        "thresh_normals": 2e-5,
        "thresh_points": 0.002,
    }
    fixture_path(case).write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")


def regenerate(editor_id: str | None = None, *, cases: list[str] | None = None,
               repeats: int = 3, verbose: bool = True) -> dict[str, dict]:
    """Spin ONE ephemeral editor, capture each corpus case `repeats` times, assert the
    surf set is coord-stable across repeats, and write a frozen fixture per case. Returns
    `{case: golden}` for the cases that captured stably. NEVER touches the standing
    `dx-lum-uned` container — mints its own uuid7 editor and tears it down in `finally`.
    """
    from ..driver import Driver
    from .. import editor as editor_mod

    editor_id = editor_id or str(uuid.uuid4())
    names = cases or list(CORPUS)
    results: dict[str, dict] = {}

    container = editor_mod.ensure_editor(editor_id)
    try:
        driver = Driver(container=container)
        for name in names:
            actors = CORPUS[name]()
            captures = []
            error = None
            for r in range(repeats):
                try:
                    captures.append(capture_case(driver, actors, case=name))
                except Exception as exc:  # noqa: BLE001 — record + continue to next case
                    error = f"{type(exc).__name__}: {exc}"
                    break
            if error is not None:
                if verbose:
                    print(f"[{name}] CAPTURE FAILED: {error}", flush=True)
                results[name] = {"error": error}
                continue
            # Stability: every repeat must agree with the first within editor thresholds.
            stable = True
            for c in captures[1:]:
                ok, diff = compare(c, captures[0])
                if not ok:
                    stable = False
                    if verbose:
                        print(f"[{name}] UNSTABLE across repeats:\n{diff}", flush=True)
                    break
            golden = captures[0]
            golden["_stable"] = stable
            golden["_repeats"] = len(captures)
            if stable:
                _write_fixture(name, golden)
            results[name] = golden
            if verbose:
                c = golden["counts"]
                print(f"[{name}] surfs={c['surfs']} nodes={c['nodes']} leaves={c['leaves']} "
                      f"verts={c['verts']} zones={c['zones']} stable={stable}", flush=True)
    finally:
        editor_mod.stop_editor(editor_id)
    return results


if __name__ == "__main__":
    import sys
    sel = sys.argv[1:] or None
    regenerate(cases=sel)
