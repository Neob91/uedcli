#!/usr/bin/env python3
"""Drive one ephemeral UnrealEd container through every `POLY TEXALIGN` mode and capture a
`MAP EXPORT` per mode.

Each round is ONE `EXEC <file>` console script (batched, rides through the GC dialog — see
dev/docs/unrealed/commands.md "`EXEC <file>`"), whose LAST line is the `MAP EXPORT` that doubles as
the completion marker; the host polls for that file rather than sleeping (driving is
fire-and-forget).

    probe.py <outdir> [MODE ...]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO))

from uedcli import container_assets, editor, writes, xfer          # noqa: E402
from uedcli.driver import Driver, to_z_path                        # noqa: E402
from uedcli.emit import emit_map
from uedcli.model import parse_t3d                                 # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture                                                     # noqa: E402

EDITOR_ID = "texalign-probe"
ASSETS = str(_REPO / "uned" / "DeusExAssets" / "2027" / "Textures")

# `TEXALIGN <token>` — every token the exec parser accepts (Editor.dll 0x68984..0x68aff).
MODES = ["NONE", "DEFAULT", "FLOOR", "WALLDIR", "WALLX", "WALLY", "WALLPAN", "WALLCOLUMN",
         "ONETILE", "CLAMP"]


def _round(driver: Driver, mode: str, clipboard: str, outdir: Path, tag: str | None = None) -> Path:
    """One MAP NEW -> paste -> REBUILD -> select-all -> TEXALIGN <mode> -> MAP EXPORT round."""
    tag = tag or mode
    driver.set_clipboard(clipboard)
    exp = xfer.work_path("t3d")
    lines = [
        "MAP NEW",
        "MAP GRID X=1 Y=1 Z=1",
        r"OBJ LOAD FILE=Z:\resources\r000\GameMisc.utx PACKAGE=GameMisc",
        "EDIT PASTE",
        "MAP REBUILD",
        "POLY SELECT ALL",
    ]
    if mode != "NONE":                       # NONE = the control round: no alignment at all
        lines.append(f"POLY TEXALIGN {mode}")
    lines.append(f"MAP EXPORT FILE={to_z_path(exp)}")
    script = "\n".join(lines) + "\n"

    host_script = outdir / f"{tag}.cmd"
    host_script.write_text(script)
    cpath = xfer.cp_in(driver.container, str(host_script), ext="txt")
    driver.exec(f"EXEC {to_z_path(cpath)}")

    deadline = time.time() + 180
    last = None
    stable = 0
    while time.time() < deadline:
        st = driver.container_stat(exp)
        if st is not None and st[0] > 0:
            if st[0] == last:
                stable += 1
                if stable >= 2:
                    break
            else:
                stable = 0
            last = st[0]
        time.sleep(1.0)
    else:
        raise SystemExit(f"{tag}: MAP EXPORT never appeared (editor wedged?)")

    out = outdir / f"{tag}.t3d"
    xfer.cp_out(driver.container, exp, str(out))
    n = len(parse_t3d(out.read_text()).actors)
    print(f"  {tag}: {out} ({out.stat().st_size} bytes, {n} actors)", flush=True)
    return out


def main() -> int:
    outdir = Path(sys.argv[1])
    outdir.mkdir(parents=True, exist_ok=True)
    modes = sys.argv[2:] or MODES

    actors = fixture.build_actors()
    clipboard = emit_map([writes._shift_for_paste(a) for a in actors])
    (outdir / "pasted.t3d").write_text(clipboard)

    state = _REPO / "_scratch" / "texalign" / "state"
    state.mkdir(parents=True, exist_ok=True)
    mounts = container_assets.resource_mounts([ASSETS])
    container = editor.ensure_editor(EDITOR_ID, state_dir=state, mounts=mounts)
    print(f"editor ready: {container}", flush=True)
    driver = Driver(container)
    for mode in modes:
        _round(driver, mode, clipboard, outdir)
    # determinism control: re-run the first mode and compare
    if len(modes) > 1:
        again = _round(driver, modes[0], clipboard, outdir, tag=modes[0] + "_again")
        same = again.read_text() == (outdir / f"{modes[0]}.t3d").read_text()
        print(f"determinism re-run of {modes[0]}: {'IDENTICAL' if same else 'DIFFERS'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
