#!/usr/bin/env python3
"""Build a uedctl T3D trunk into a `.dx` map file with NO GUI, NO X server and NO window —
by driving UnrealEd's own engine through `UCC.exe Editor.ExecCommandlet <script>` (the
`UExecCommandlet` in `Editor.dll`, which instantiates `ini:Engine.Engine.EditorEngine` and
runs a file of ordinary editor exec verbs).

This is the harness for the spike `dev/docs/spikes/headless-materialize/findings.md`.
It EMITS the exec script + the per-brush polylist files; it does not run wine itself
(run the printed command inside the editor image, or under host wine).

Why it cannot simply replay uedctl's existing materialize sequence: uedctl adds brushes with
`EDIT PASTE`, and the clipboard is DEAD in the headless commandlet (`EDIT COPY` writes nothing,
`EDIT PASTE` pastes nothing — measured, see findings.md §4). The clipboard-free equivalent that
still produces a CSG-participating brush is `BRUSH IMPORT` (builder polylist) + `BRUSH MOVETO` /
`BRUSH ROTATETO` + `BRUSH ADD`/`BRUSH SUBTRACT`.

Known gaps this harness reports rather than silently mis-building (findings.md §6):
  * brush ACTOR NAMES are assigned by the editor (`Brush0`, `Brush1`, …) — the trunk name is lost;
  * `Mover`s cannot be built this way (their keyframe properties have no console setter);
  * `PrePivot` and `MainScale`/`PostScale` have no console setter on the builder brush here
    (`BRUSH SCALE`/`SHEER` exist but their arg grammar is unverified — see findings.md §6).

Usage:
    headless_build.py --project <root> --level <name> --workdir <dir> \
                      [--out-name out.dx] [--no-light]
Writes into <dir>: build.txt (the exec script), points.t3d, <brush>.polys.t3d.
Prints the wine command to run and a report of skipped/degraded actors.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


def _uedctl_root() -> Path:
    # .../Tools/uedctl/dev/docs/spikes/headless-materialize/headless_build.py
    return Path(__file__).resolve().parents[4]


sys.path.insert(0, str(_uedctl_root()))

from uedctl import trunk                      # noqa: E402
from uedctl.emit import emit_actor, emit_map  # noqa: E402
from uedctl.materialize import levelinfo_first_order  # noqa: E402

_POLYLIST = re.compile(r"(Begin PolyList.*?End PolyList)", re.S)


def _polylist(actor) -> str:
    """The actor's own `Begin PolyList … End PolyList` block, verbatim, as `BRUSH IMPORT` wants."""
    m = _POLYLIST.search(emit_actor(actor))
    if not m:
        raise ValueError(f"actor {actor.name}: no PolyList block")
    return m.group(1) + "\n"


def _prop(actor, key):
    """An actor's raw property VALUE text by name (`Actor.props` is a list of (key, value) pairs)."""
    for k, v in (actor.props or []):
        if k == key:
            return v
    return None


def _rot(actor):
    r = _prop(actor, "Rotation")
    if not r:
        return None
    got = {k.lower(): int(v) for k, v in re.findall(r"(\w+)=(-?\d+)", r)}
    return got.get("pitch", 0), got.get("yaw", 0), got.get("roll", 0)


def _has_unsupported_scale(actor) -> bool:
    for fs in (actor.main_scale, actor.post_scale):
        sc = getattr(fs, "scale", None)
        if sc is not None and tuple(float(c) for c in sc) != (1.0, 1.0, 1.0):
            return True
        if float(getattr(fs, "sheer_rate", 0.0) or 0.0) != 0.0:
            return True
    return bool(_prop(actor, "PrePivot"))


def build(project: str, level_name: str, workdir: Path, out_name: str, light: bool) -> int:
    from uedctl import config
    root = config.walk_up_root(project) if hasattr(config, "walk_up_root") else project
    maps_dir = Path(project) / "uedctl" / "maps"
    if not (maps_dir / level_name).is_dir():          # fall back to the toml-declared maps dir
        import tomllib
        cfg = tomllib.loads((Path(project) / "uedctl.toml").read_text())
        maps_dir = Path(project) / cfg.get("maps", "maps")
    level, _ranks = trunk.read_level(maps_dir / level_name)

    classes = {n: a.cls for n, a in level.actors.items()}
    has_brush = {n: a.brush is not None for n, a in level.actors.items()}
    order = levelinfo_first_order(level.order, classes, has_brush)

    workdir.mkdir(parents=True, exist_ok=True)
    lines = ["MAP GRID X=1 Y=1 Z=1", "MAP ROTGRID PITCH=1 YAW=1 ROLL=1"]
    points, skipped, degraded = [], [], []

    for name in order:
        a = level.actors[name]
        if a.brush is None:
            points.append(a)
            continue
        short = (a.cls or "").rsplit(".", 1)[-1]
        if short != "Brush":                      # Mover & friends: no console authoring path
            skipped.append((name, f"class {a.cls} — no headless add path (see findings.md §6)"))
            continue
        if _has_unsupported_scale(a):
            degraded.append((name, "MainScale/PostScale/PrePivot dropped (no console setter)"))
        pl = workdir / f"{name}.polys.t3d"
        pl.write_text(_polylist(a))
        lines.append(rf"BRUSH IMPORT FILE=Z:\work\{pl.name}")
        r = _rot(a)
        if r:
            lines.append(f"BRUSH ROTATETO PITCH={r[0]} YAW={r[1]} ROLL={r[2]}")
        loc = a.location or (0, 0, 0)
        lines.append("BRUSH MOVETO X=%s Y=%s Z=%s" % tuple(int(c) for c in loc))
        oper = _prop(a, "CsgOper") or "CSG_Add"
        lines.append("BRUSH SUBTRACT" if "Subtract" in oper else "BRUSH ADD")
        pf = _prop(a, "PolyFlags")
        if pf and int(pf) != 0:
            lines.append(f"MAP SETBRUSH SETFLAGS={int(pf)}")
        degraded.append((name, f"editor-assigned actor name (trunk name {name!r} is lost)"))

    if points:
        (workdir / "points.t3d").write_text(emit_map(points))
        lines.insert(2, r"MAP IMPORTADD FILE=Z:\work\points.t3d")

    lines.append("MAP REBUILD")
    if light:
        lines.append("LIGHT APPLY")
    lines.append(rf"MAP SAVE FILE=Z:\work\{out_name}")
    lines.append(rf"MAP EXPORT FILE=Z:\work\{out_name}.t3d")     # completion marker + readback

    script = workdir / "build.txt"
    script.write_bytes(("\r\n".join(lines) + "\r\n").encode())   # CRLF: the engine's ini/text habit

    print(f"wrote {script}  ({len(lines)} commands, "
          f"{sum(1 for l in lines if l.startswith('BRUSH IMPORT'))} brushes, "
          f"{len(points)} point actors)")
    print(r"run:  wine UCC.exe Editor.ExecCommandlet Z:\work\build.txt")
    for n, why in skipped:
        print(f"  SKIPPED  {n}: {why}")
    for n, why in degraded:
        print(f"  degraded {n}: {why}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True, help="uedctl project root (holds uedctl.toml)")
    ap.add_argument("--level", required=True, help="level name (a dir under the project's maps dir)")
    ap.add_argument("--workdir", required=True, type=Path,
                    help="host dir mounted at /work in the editor container")
    ap.add_argument("--out-name", default="headless.dx", help="output map file name inside /work")
    ap.add_argument("--no-light", action="store_true", help="skip LIGHT APPLY (geometry only)")
    a = ap.parse_args()
    return build(a.project, a.level, a.workdir, a.out_name, not a.no_light)


if __name__ == "__main__":
    raise SystemExit(main())
