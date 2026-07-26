#!/usr/bin/env python3
"""Second TEXALIGN drive: the guard thresholds, the `TEXELS=` argument, an unknown/absent mode
token, whether the op is scoped to the SELECTION, and whether it needs a built BSP at all.

Each guard case is its OWN one-wedge level (see `fixture2.py`), and **one round produces several
exports**: the console script runs `MAP NEW → paste → REBUILD → export the control → TEXALIGN →
export the result` in a single synchronous `EXEC` file, so the control and the test come from the
identical level and one round costs one editor round-trip instead of two. That matters here: this
box has under a gigabyte free, the editor dies every couple of rounds, and every death costs a
timeout plus a ~60 s container re-spin.

Already-captured rounds are skipped, so the script is resumable after a give-up.

    probe2.py <outdir>
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
import fixture2                                                    # noqa: E402

EDITOR_ID = "texalign-probe2"
ASSETS = str(_REPO / "uned" / "DeusExAssets" / "2027" / "Textures")
STATE = _REPO / "_scratch" / "texalign" / "state2"
ROUND_TIMEOUT = 90.0             # a good round finishes in ~20 s; longer means the editor is gone

_PRELUDE = ["MAP NEW", "MAP GRID X=1 Y=1 Z=1",
            r"OBJ LOAD FILE=Z:\resources\r000\GameMisc.utx PACKAGE=GameMisc",
            "EDIT PASTE"]


def _rounds(outdir: Path):
    """[(round tag, clipboard, [(export tag, console line) …]) …].

    A `None` console line means "just export here". Applying an alignment mode twice, or applying a
    second mode on top of a first, is safe for every mode used below: `FLOOR`/`WALLDIR` are pure
    functions of the surface's plane and normal (neither of which an alignment changes) and
    `ONETILE` writes nothing — so one level can be exported after each of several `TEXALIGN`s and
    every export still means what its own line says.
    """
    out = []
    for case, (_t, _ax, _sw, mode) in fixture2.CASES.items():
        clip = emit_map([writes._shift_for_paste(a) for a in fixture2.build_actors(case)])
        (outdir / f"{case}.pasted.t3d").write_text(clip)
        out.append((case, clip, [(f"{case}-CTRL", "POLY SELECT ALL"),
                                 (f"{case}-{mode}", f"POLY TEXALIGN {mode}")]))

    argclip = emit_map([writes._shift_for_paste(a) for a in fixture2.build_actors("NZ949")])
    out.append(("args-texels", argclip, [
        ("sel-CTRL", "POLY SELECT ALL"),
        ("arg-FLOOR", "POLY TEXALIGN FLOOR"),
        ("arg-FLOOR-TEXELS64", "POLY TEXALIGN FLOOR TEXELS=64"),
        ("arg-WALLDIR", "POLY TEXALIGN WALLDIR"),
        ("arg-WALLDIR-TEXELS64", "POLY TEXALIGN WALLDIR TEXELS=64"),
        ("arg-ONETILE", "POLY TEXALIGN ONETILE"),
        ("arg-ONETILE-TEXELS64", "POLY TEXALIGN ONETILE TEXELS=64")]))
    out.append(("args-grammar", argclip, [
        ("arg-NOTOKEN", "POLY SELECT ALL\nPOLY TEXALIGN"),
        ("arg-BOGUS", "POLY TEXALIGN BOGUS")]))
    out.append(("sel", argclip, [
        ("sel-NONE", "POLY SELECT NONE\nPOLY TEXALIGN WALLDIR"),
        ("sel-ALL", "POLY SELECT ALL\nPOLY TEXALIGN WALLDIR")]))
    # no MAP REBUILD -> no Model->Surfs -> nothing for TEXALIGN to walk
    out.append(("norebuild", argclip, [
        ("norebuild-WALLDIR", "POLY SELECT ALL\nPOLY TEXALIGN WALLDIR")]))
    return out


def _fresh_editor():
    editor.stop_editor(EDITOR_ID, STATE)
    c = editor.ensure_editor(EDITOR_ID, state_dir=STATE,
                             mounts=container_assets.resource_mounts([ASSETS]))
    print(f"  [editor {c} ready]", flush=True)
    return Driver(c)


def _run(driver, tag, clipboard, steps, outdir, rebuild=True):
    driver.set_clipboard(clipboard)
    lines = list(_PRELUDE) + (["MAP REBUILD"] if rebuild else [])
    exports = []
    for export_tag, console in steps:
        if console:
            lines += console.split("\n")
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
        print(f"  {export_tag}: {dest.stat().st_size} bytes, "
              f"{len(parse_t3d(dest.read_text()).actors)} actors", flush=True)


def main():
    outdir = Path(sys.argv[1])
    outdir.mkdir(parents=True, exist_ok=True)
    STATE.mkdir(parents=True, exist_ok=True)

    driver = None
    for tag, clip, steps in _rounds(outdir):
        if all((outdir / f"{t}.t3d").exists() for t, _ in steps):
            print(f"  {tag}: already captured, skipping", flush=True)
            continue
        for attempt in range(3):
            try:
                if driver is None:
                    driver = _fresh_editor()
                _run(driver, tag, clip, steps, outdir, rebuild=(tag != "norebuild"))
                break
            except Exception as e:
                print(f"  {tag}: attempt {attempt + 1} failed ({e}); recreating the editor",
                      flush=True)
                driver = None
        else:
            print(f"  {tag}: GAVE UP after 3 attempts", flush=True)
    editor.stop_editor(EDITOR_ID, STATE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
