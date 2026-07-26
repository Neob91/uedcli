#!/usr/bin/env python3
"""Emit the exec-script VARIANT MATRIX this spike used to find a headless brush-entry path
(`findings.md` §5) and to pin the headless failure modes (§4).

Each variant is a file of ordinary UnrealEd console verbs, run by
`wine UCC.exe Editor.ExecCommandlet <file>` — the `UExecCommandlet` in `Editor.dll`, which
instantiates `ini:Engine.Engine.EditorEngine` and executes the file line by line with no GUI,
no window and no X server. The question each variant answers is in its comment; the measured
answer is in `findings.md`.

This script only WRITES the scripts + the two T3D inputs it needs. Run them yourself, e.g.:

    python3 probe_variants.py /path/to/workdir
    cd <editor image or a wine substrate dir>
    for v in A B C D E F G H J K; do wine UCC.exe Editor.ExecCommandlet 'Z:\\work\\'$v.txt; done

`workdir` must be visible to the engine as `Z:\\work` (bind-mount it at /work in the editor
image, or edit Z_WORK below to the absolute Z: path of your own directory).
"""
from __future__ import annotations

import sys
from pathlib import Path

Z_WORK = r"Z:\work"          # where the engine sees `workdir`

# A 512-cube subtract brush, in the two shapes the two import verbs want:
#   ROOM_MAP  — a level T3D (`Begin Map`…`End Map`), what `MAP IMPORT`/`MAP IMPORTADD` take.
#   CUBE_POLY — a bare `Begin PolyList`…`End PolyList`, what `BRUSH IMPORT` takes.
# Generate both from uedctl so they stay in step with the emitter:
#   uedctl brush build cube --width 512 --breadth 512 --height 512 --at 0,0,0 --csg subtract
_GEN = ("uedctl --project <root> brush build cube --width 512 --breadth 512 --height 512 "
        "--at 0,0,0 --csg subtract")


def _inputs(work: Path) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
    from uedctl.builders import cube, make_brush_actor    # noqa: E402
    from uedctl.emit import emit_actor, emit_map          # noqa: E402
    import re                                             # noqa: E402
    a = make_brush_actor(name="Cube", brush=cube(512, 512, 512),
                         location=(0, 0, 0), csg="subtract")
    work.joinpath("room_map.t3d").write_text(emit_map([a]))
    m = re.search(r"(Begin PolyList.*?End PolyList)", emit_actor(a), re.S)
    work.joinpath("cube_polys.t3d").write_text(m.group(1) + "\n")


# (name, question, commands) — every one ends by saving, so "did it work" is read off the
# saved package's BSP node count (0 nodes = the world was never carved).
VARIANTS = [
    ("A", "does MAP IMPORTADD + MAP REBUILD carve the world?", [
        r"MAP IMPORTADD FILE={W}\room_map.t3d", "MAP REBUILD", r"MAP SAVE FILE={W}\A.dx"]),
    ("B", "does the full-replace MAP IMPORT carve it?", [
        r"MAP IMPORT FILE={W}\room_map.t3d", "MAP REBUILD", r"MAP SAVE FILE={W}\B.dx"]),
    ("C", "does BRUSH IMPORT + BRUSH SUBTRACT carve it? (the clipboard-free add path)", [
        r"BRUSH IMPORT FILE={W}\cube_polys.t3d", "BRUSH MOVETO X=0 Y=0 Z=0", "BRUSH SUBTRACT",
        "MAP REBUILD", r"MAP SAVE FILE={W}\C.dx"]),
    ("D", "does ACTOR APPLYTRANSFORM repair an IMPORTADD brush?", [
        r"MAP IMPORTADD FILE={W}\room_map.t3d", "ACTOR SELECT ALL", "ACTOR APPLYTRANSFORM",
        "MAP REBUILD", r"MAP SAVE FILE={W}\D.dx"]),
    ("E", "does a save + MAP LOAD round-trip repair it?", [
        r"MAP IMPORTADD FILE={W}\room_map.t3d", r"MAP SAVE FILE={W}\E_tmp.dx",
        r"MAP LOAD FILE={W}\E_tmp.dx", "MAP REBUILD", r"MAP SAVE FILE={W}\E.dx"]),
    ("F", "does MAP SETBRUSH repair it?", [
        r"MAP IMPORTADD FILE={W}\room_map.t3d", "ACTOR SELECT ALL", "MAP SETBRUSH CSGOPER=2",
        "MAP REBUILD", r"MAP SAVE FILE={W}\F.dx"]),
    ("G", "does LEVEL FIX repair it?", [
        r"MAP IMPORTADD FILE={W}\room_map.t3d", "LEVEL FIX", "MAP REBUILD",
        r"MAP SAVE FILE={W}\G.dx"]),
    ("H", "does EDIT CUT + EDIT PASTE repair it? (i.e. is the clipboard alive headless?)", [
        r"MAP IMPORTADD FILE={W}\room_map.t3d", "ACTOR SELECT ALL", "EDIT CUT", "EDIT PASTE",
        "MAP REBUILD", r"MAP SAVE FILE={W}\H.dx", r"MAP EXPORT FILE={W}\H.t3d"]),
    ("J", "do LIGHT APPLY and PATHS BUILD run headless at all?", [
        r"BRUSH IMPORT FILE={W}\cube_polys.t3d", "BRUSH MOVETO X=0 Y=0 Z=0", "BRUSH SUBTRACT",
        "MAP REBUILD", "LIGHT APPLY", "PATHS BUILD", r"MAP EXPORT FILE={W}\J.t3d",
        r"MAP SAVE FILE={W}\J.dx"]),
    ("K", "does EDIT COPY put anything on the clipboard? (paste into a fresh level)", [
        r"MAP IMPORTADD FILE={W}\room_map.t3d", "ACTOR SELECT ALL", "EDIT COPY", "MAP NEW",
        "EDIT PASTE", "MAP REBUILD", r"MAP SAVE FILE={W}\K.dx", r"MAP EXPORT FILE={W}\K.t3d"]),
]


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    work = Path(sys.argv[1])
    work.mkdir(parents=True, exist_ok=True)
    try:
        _inputs(work)
    except Exception as e:                       # uedctl not importable from here → say how
        print(f"could not generate the T3D inputs ({e}); make them by hand with:\n  {_GEN}")
    for name, question, cmds in VARIANTS:
        body = ["MAP GRID X=1 Y=1 Z=1"] + [c.format(W=Z_WORK) for c in cmds]
        # CRLF: every text file this engine reads is CRLF in its own substrate.
        work.joinpath(f"{name}.txt").write_bytes(("\r\n".join(body) + "\r\n").encode())
        print(f"{name}.txt  — {question}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
