#!/usr/bin/env python3
"""Third TEXALIGN drive: does each mode ZERO the surface `Pan`, or leave it alone?

The main fixture cannot answer that — every one of its 44 faces already carried `Pan = (0,0)`, so
"sets it to zero" and "leaves it alone" produce identical exports. This drive authors a NON-ZERO pan
(`Pan U=7 V=13`) on every face first, so the two are distinguishable.

Ordering matters: a mode that zeroes the pan destroys the signal for everything after it in the same
level. So the three PRESERVING candidates share one level (they cannot destroy it), and each ZEROING
candidate gets its own `MAP NEW` → paste → `MAP REBUILD` sequence — several such sequences per
`EXEC` script, since the script runs synchronously and rides through the GC dialog.

    probe3.py <outdir>
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO))

from uedcli import container_assets, editor, writes, xfer          # noqa: E402
from uedcli.driver import Driver, to_z_path                        # noqa: E402
from uedcli.emit import emit_map                                   # noqa: E402
from uedcli.model import parse_t3d                                 # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture                                                     # noqa: E402

EDITOR_ID = "texalign-probe3"
ASSETS = str(_REPO / "uned" / "DeusExAssets" / "2027" / "Textures")
STATE = _REPO / "_scratch" / "texalign" / "state3"
PAN = (7, 13)                    # the authored non-zero pan, on every face
ROUND_TIMEOUT = 120.0

_SEQ = ["MAP NEW", "MAP GRID X=1 Y=1 Z=1",
        r"OBJ LOAD FILE=Z:\resources\r000\GameMisc.utx PACKAGE=GameMisc",
        "EDIT PASTE", "MAP REBUILD", "POLY SELECT ALL"]

# Round -> [(export tag, mode or None)]. `fresh=True` re-pastes a clean level before EACH mode.
ROUNDS = {
    # the three candidates that should PRESERVE a pan — safe to chain on one level
    "preserve": (False, [("pan-CTRL", None), ("pan-WALLCOLUMN", "WALLCOLUMN"),
                         ("pan-ONETILE", "ONETILE"), ("pan-WALLPAN", "WALLPAN")]),
    "zero-a": (True, [("pan-FLOOR", "FLOOR"), ("pan-WALLDIR", "WALLDIR"),
                      ("pan-DEFAULT", "DEFAULT")]),
    "zero-b": (True, [("pan-WALLX", "WALLX"), ("pan-WALLY", "WALLY"),
                      ("pan-CLAMP", "CLAMP")]),
}


def _clipboard():
    actors = fixture.build_actors()
    for a in actors:
        for p in a.brush.polys:
            p.pan = PAN
    return emit_map([writes._shift_for_paste(a) for a in actors])


def _fresh_editor():
    editor.stop_editor(EDITOR_ID, STATE)
    c = editor.ensure_editor(EDITOR_ID, state_dir=STATE,
                             mounts=container_assets.resource_mounts([ASSETS]))
    print(f"  [editor {c} ready]", flush=True)
    return Driver(c)


def _run(driver, tag, clipboard, fresh, steps, outdir):
    driver.set_clipboard(clipboard)
    lines, exports = [], []
    if not fresh:
        lines += _SEQ
    for export_tag, mode in steps:
        if fresh:
            lines += _SEQ
        if mode:
            lines.append(f"POLY TEXALIGN {mode}")
        path = xfer.work_path("t3d")
        lines.append(f"MAP EXPORT FILE={to_z_path(path)}")
        exports.append((export_tag, path))
    host = outdir / f"{tag}.cmd"
    host.write_text("\n".join(lines) + "\n")
    driver.exec(f"EXEC {to_z_path(xfer.cp_in(driver.container, str(host), ext='txt'))}")

    last = exports[-1][1]
    deadline, size, stable = time.time() + ROUND_TIMEOUT, None, 0
    while time.time() < deadline:
        st = driver.container_stat(last)
        if st and st[0] > 0:
            stable = stable + 1 if st[0] == size else 0
            size = st[0]
            if stable >= 2:
                break
        time.sleep(1.0)
    else:
        raise TimeoutError(f"{tag}: the final MAP EXPORT never appeared")
    for export_tag, path in exports:
        dest = outdir / f"{export_tag}.t3d"
        xfer.cp_out(driver.container, path, str(dest))
        print(f"  {export_tag}: {len(parse_t3d(dest.read_text()).actors)} actors", flush=True)


def main():
    outdir = Path(sys.argv[1])
    outdir.mkdir(parents=True, exist_ok=True)
    STATE.mkdir(parents=True, exist_ok=True)
    clip = _clipboard()
    (outdir / "pasted.t3d").write_text(clip)

    driver = None
    for tag, (fresh, steps) in ROUNDS.items():
        if all((outdir / f"{t}.t3d").exists() for t, _ in steps):
            print(f"  {tag}: already captured, skipping", flush=True)
            continue
        for attempt in range(4):
            try:
                if driver is None:
                    driver = _fresh_editor()
                _run(driver, tag, clip, fresh, steps, outdir)
                break
            except Exception as e:
                print(f"  {tag}: attempt {attempt + 1} failed ({e}); recreating the editor",
                      flush=True)
                driver = None
        else:
            print(f"  {tag}: GAVE UP", flush=True)
    editor.stop_editor(EDITOR_ID, STATE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
