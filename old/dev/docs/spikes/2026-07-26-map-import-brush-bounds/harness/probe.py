#!/usr/bin/env python3
"""Does `MAP IMPORT` give a brush the `Bound` that CSG needs — or does it drop it like
`MAP IMPORTADD` does?

BACKGROUND (why this is worth a live probe). uedcli introduces point actors with `MAP IMPORTADD`
but brushes with `EDIT PASTE`, because of the finding in `dev/docs/unrealed/quirks.md` "How brushes
enter the level": a brush that enters via `MAP IMPORTADD` never gets its `Bound` computed, CSG
therefore skips it entirely, and `MAP REBUILD` produces a world model with ZERO nodes — a map that
still saves, still parses, and still draws its wireframe in the editor, but whose world is solid, so
the real game dies at `Failed to spawn player actor`. That was proven live 2026-06-28.

Every one of those probes used `MAP IMPORTADD` (the ADD-to-current-level form). Nobody has driven
`MAP IMPORT` — the REPLACE-the-whole-level form. Both are believed to run the same `ULevelFactory`,
which is the thing that skips the bound computation, so the expectation is that `MAP IMPORT` has the
same defect. But that is an inference, and the answer changes a design: a working `MAP IMPORT` would
let the whole materialize drive be one file-based console script (no host clipboard round-trip), and
would delete both the +32uu paste-drift compensation and the point-actors-before-brushes ordering
constraint that `materialize.levelinfo_first_order` exists solely to satisfy.

METHOD. One editor container, three rounds over the SAME two-brush fixture (a subtractive room with
an additive pillar in it). Each round starts from `MAP NEW`, introduces the actors by one verb,
rebuilds, saves, and exports:

    paste       MAP NEW -> EDIT PASTE            the production path      -> expect nodes > 0
    importadd   MAP NEW -> MAP IMPORTADD FILE=   the known-bad control    -> expect nodes == 0
    import      MAP NEW -> MAP IMPORT FILE=      THE QUESTION

Rounds are driven as ONE `EXEC <file>` console script each (`dev/docs/unrealed/commands.md`
"`EXEC <file>`"), whose LAST line is a `MAP EXPORT` doubling as the completion marker the host polls
for — driving is fire-and-forget, so a marker is the only honest completion signal, and a script
rides through the GC "Cleaning up..." dialog that would stall the same commands typed one at a time.

The verdict is read offline by `bspnodes.py` (BSP node count in the saved `.dx`). The export is
captured too, because a second question rides along: does the verb PRESERVE ACTOR NAMES? uedcli's
model is name-keyed, so a verb that renames brushes the way `BRUSH ADD` does (to `Brush1..BrushN`)
is unusable regardless of what it does to CSG.

    probe.py <outdir> [ROUND ...]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(_REPO))

from uedcli import builders, container_assets, editor, writes, xfer      # noqa: E402
from uedcli.driver import Driver, to_z_path                              # noqa: E402
from uedcli.emit import emit_map                                         # noqa: E402
from uedcli.model import parse_t3d                                       # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bspnodes import count as count_nodes                                # noqa: E402

EDITOR_ID = "mapimport-probe"
ROUNDS = ["paste", "importadd", "import"]


def build_actors():
    """A subtractive room with an additive pillar inside it.

    Two brushes, not one, so the round also shows whether ADD and SUBTRACT fare differently under
    the same verb. Untextured: CSG does not need a texture and leaving textures out means the probe
    needs no content package mounted, so it cannot fail for an unrelated missing-asset reason.
    """
    room = builders.cube(1024, 1024, 512)
    pillar = builders.cube(128, 128, 512)
    return [
        builders.make_brush_actor("ProbeRoom", room, (0, 0, 0), csg="subtract"),
        builders.make_brush_actor("ProbePillar", pillar, (256, 0, 0), csg="add"),
    ]


def _run_round(driver: Driver, name: str, actors, outdir: Path) -> dict:
    """Drive one round; return its measurements."""
    dx = f"/work/{name}.dx"
    marker = f"/work/{name}-done.t3d"
    lines = ["MAP GRID X=1 Y=1 Z=1", "MAP NEW"]

    if name == "paste":
        # Production shape: the clipboard is loaded HOST-side (a `docker exec` running xclip),
        # then a single console `EDIT PASTE` consumes it. That is why a clipboard-based add path
        # is still compatible with a batched script — the clipboard is already in place when the
        # script runs. Actors are pre-shifted -32 to cancel the documented paste drift.
        driver.set_clipboard(emit_map([writes._shift_for_paste(a) for a in actors]))
        lines.append("EDIT PASTE")
    else:
        payload = xfer.cp_in(driver.container,
                             str(_write(outdir / f"{name}-payload.t3d", emit_map(actors))),
                             ext="t3d")
        verb = "MAP IMPORTADD" if name == "importadd" else "MAP IMPORT"
        lines.append(f"{verb} FILE={to_z_path(payload)}")

    lines += ["MAP REBUILD",
              f"MAP SAVE FILE={to_z_path(dx)}",
              f"MAP EXPORT FILE={to_z_path(marker)}"]

    script = _write(outdir / f"{name}.cmd", "\n".join(lines) + "\n")
    cpath = xfer.cp_in(driver.container, str(script), ext="txt")
    driver.exec(f"EXEC {to_z_path(cpath)}")

    _await_stable(driver, marker, what=f"{name}: MAP EXPORT marker")
    _await_stable(driver, dx, what=f"{name}: MAP SAVE output")

    host_dx = outdir / f"{name}.dx"
    host_t3d = outdir / f"{name}.t3d"
    xfer.cp_out(driver.container, dx, str(host_dx))
    xfer.cp_out(driver.container, marker, str(host_t3d))

    nodes, surfs = count_nodes(str(host_dx))
    lvl = parse_t3d(host_t3d.read_text())
    return {"round": name, "nodes": nodes, "surfs": surfs,
            "dx_bytes": host_dx.stat().st_size,
            "actors": sorted(lvl.actors), "n_actors": len(lvl.actors)}


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _await_stable(driver: Driver, container_path: str, *, what: str,
                  timeout: float = 240.0) -> None:
    """Block until `container_path` reaches a stable non-zero size, or fail NAMED.

    Bounded, never open-ended: the editor wedges silently, so an unbounded wait would hang the
    probe forever rather than reporting (`dev/docs/rules/background-work.md`).
    """
    deadline = time.time() + timeout
    last, stable = None, 0
    while time.time() < deadline:
        st = driver.container_stat(container_path)
        if st is not None and st[0] > 0:
            if st[0] == last:
                stable += 1
                if stable >= 3:
                    return
            else:
                stable = 0
            last = st[0]
        time.sleep(1.0)
    raise SystemExit(f"{what}: never appeared at {container_path} within {timeout:.0f}s "
                     f"(editor wedged, or the verb did nothing)")


def main() -> int:
    outdir = Path(sys.argv[1])
    outdir.mkdir(parents=True, exist_ok=True)
    rounds = sys.argv[2:] or ROUNDS

    actors = build_actors()
    _write(outdir / "fixture.t3d", emit_map(actors))

    state = _REPO / "_scratch" / "mapimport" / "state"
    state.mkdir(parents=True, exist_ok=True)
    # No `/resources` mounts: the fixture is untextured, so no content package is needed and the
    # probe cannot fail for a missing-asset reason unrelated to the question.
    container = editor.ensure_editor(EDITOR_ID, state_dir=state, mounts=None)
    print(f"editor ready: {container}", flush=True)
    driver = Driver(container)

    results = []
    for name in rounds:
        print(f"--- round {name}", flush=True)
        r = _run_round(driver, name, actors, outdir)
        results.append(r)
        print(f"  nodes={r['nodes']} surfs={r['surfs']} dx={r['dx_bytes']}B "
              f"actors={r['n_actors']} {r['actors']}", flush=True)

    print("\n== VERDICT ==", flush=True)
    for r in results:
        verdict = "CSG PARTICIPATED" if r["nodes"] > 0 else "SOLID — brush skipped by CSG"
        print(f"  {r['round']:<10} nodes={r['nodes']:<6} {verdict}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
