#!/usr/bin/env python3
"""Does a REUSED editor re-case a later build's actor name to an earlier build's spelling?

This is the production form of the name-case finding, and it is the one that matters for the warm
materialize container. The retail-map probe (`name_case_probe.py`) established that a FRESH editor
preserves the package's own spelling of a name while the sweep's REUSED editor did not — so the
capitalisation came from something registered earlier in that session. UE1 `FName`s live in one
process-global, case-insensitive table where the first spelling registered wins every later lookup.

If that carries over to uedcli's own content, then a warm editor building level A and then level B
can write B's actors under A's spelling — and uedcli's compare keys actors by VERBATIM name (only
property keys and class names are casefolded, `normalize.compare_view`), so the post-build verify
would fail on a build that is otherwise perfectly correct. That is a false negative on the one check
whose entire job is deciding whether a build is wrong.

METHOD — three rounds in ONE editor, using only uedcli-authored content (no retail map needed):

  1. `MAP NEW`, paste an actor named `probelight1` (lowercase), export   -> baseline: what a
     never-contaminated editor writes.
  2. `MAP NEW`, paste an actor named `ProbeLight1` (capitalised), export -> registers the OTHER
     spelling in the process-global table.
  3. `MAP NEW`, paste `probelight1` again, export                       -> THE QUESTION. If round 3
     comes back `ProbeLight1`, a reused editor rewrites a later build's names to an earlier build's
     spelling, and the drift is proven with uedcli's own actors.

    name_drift_probe.py <outdir>
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(_REPO))

from uedcli import builders, editor, writes, xfer                        # noqa: E402
from uedcli.driver import Driver, to_z_path                              # noqa: E402
from uedcli.emit import emit_map                                         # noqa: E402
from uedcli.model import parse_t3d                                       # noqa: E402

EDITOR_ID = "namedrift-probe"
LOWER, UPPER = "probelight1", "ProbeLight1"


def _actor(name: str):
    """One additive cube brush under `name`. A brush (not a point actor) so the round also goes
    through the production add path — `EDIT PASTE` — exactly as a real build does."""
    return builders.make_brush_actor(name, builders.cube(256, 256, 256), (0, 0, 0), csg="add")


def _round(driver: Driver, name: str, tag: str, outdir: Path) -> list[str]:
    """MAP NEW -> paste an actor called `name` -> export. Returns the spelling(s) written back."""
    marker = f"/work/{tag}.t3d"
    subprocess.run(["docker", "exec", driver.container, "rm", "-f", marker],
                   capture_output=True, text=True)
    driver.set_clipboard(emit_map([writes._shift_for_paste(_actor(name))]))
    script = outdir / f"{tag}.cmd"
    script.write_text("MAP NEW\nMAP GRID X=1 Y=1 Z=1\nEDIT PASTE\n"
                      f"MAP EXPORT FILE={to_z_path(marker)}\n")
    driver.exec(f"EXEC {to_z_path(xfer.cp_in(driver.container, str(script), ext='txt'))}")

    deadline = time.time() + 240
    last, stable = None, 0
    while time.time() < deadline:
        st = driver.container_stat(marker)
        if st is not None and st[0] > 0:
            if st[0] == last:
                stable += 1
                if stable >= 3:
                    break
            else:
                stable = 0
            last = st[0]
        time.sleep(1.0)
    else:
        raise SystemExit(f"{tag}: export never settled")

    host = outdir / f"{tag}.t3d"
    xfer.cp_out(driver.container, marker, str(host))
    txt = host.read_text()
    if not parse_t3d(txt).actors:
        raise SystemExit(f"{tag}: exported an empty level")
    return sorted(set(re.findall(rf"Name=({LOWER})\b", txt, flags=re.IGNORECASE)))


def main() -> int:
    outdir = Path(sys.argv[1])
    outdir.mkdir(parents=True, exist_ok=True)

    state = _REPO / "_scratch" / "namedrift" / "state"
    state.mkdir(parents=True, exist_ok=True)
    container = editor.ensure_editor(EDITOR_ID, state_dir=state, mounts=None)
    print(f"FRESH editor ready: {container}", flush=True)
    driver = Driver(container)

    r1 = _round(driver, LOWER, "r1_lower_first", outdir)
    print(f"  round 1  authored {LOWER!r:<16} -> editor wrote {r1}", flush=True)
    r2 = _round(driver, UPPER, "r2_upper", outdir)
    print(f"  round 2  authored {UPPER!r:<16} -> editor wrote {r2}", flush=True)
    r3 = _round(driver, LOWER, "r3_lower_again", outdir)
    print(f"  round 3  authored {LOWER!r:<16} -> editor wrote {r3}", flush=True)

    print("\n== VERDICT ==", flush=True)
    if r1 == [LOWER] and r3 == [UPPER]:
        print(f"  DRIFT CONFIRMED. The same authored name {LOWER!r} came back as {LOWER!r} from a "
              f"clean editor and as {UPPER!r} after an earlier build had registered the other "
              f"spelling. A warm editor rewrites a later build's actor names to an earlier build's "
              f"casing; the compare keys actors by verbatim name, so this lands on the verify.",
              flush=True)
    elif r1 == r3:
        print(f"  NO DRIFT between builds: round 3 wrote {r3}, the same as round 1. Whatever "
              f"re-cased the retail-map name does not reach uedcli's own paste-authored actors.",
              flush=True)
    else:
        print(f"  INCONCLUSIVE — round 1 {r1}, round 2 {r2}, round 3 {r3}. Read the exports.",
              flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
