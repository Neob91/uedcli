#!/usr/bin/env python3
"""Where does the CASE of an exported actor name come from — the package, or the editor?

The completeness sweep turned up exactly one class of difference between UCC's export of a map and
UnrealEd's export of the same map: the LETTER CASE of names. On `15_Area51_Page` and
`12_Vandenberg_Cmd`, UCC wrote `Name=light1` and the editor wrote `Name=Light1`. Reading the maps'
own name tables offline explained it perfectly, 5 maps out of 5: **UCC emits the spelling the
package stores; the editor emits `Light1` whatever the package stores.**

That leaves one question, and it is not academic — it decides whether a REUSED editor can be trusted
to export the same thing a fresh one would. UE1 `FName`s are case-insensitive with a process-global
name table, and the FIRST spelling registered wins for every later lookup. So the editor's `Light1`
is either:

  (a) CONSTANT — `Light1` is registered during editor startup (the editor auto-names actors
      `<Class><N>`), so every editor, fresh or reused, exports `Light1`; or
  (b) HISTORY-DEPENDENT — it was registered by a package loaded EARLIER in that session, in which
      case a warm editor's exports drift with whatever it happened to build before, and a fresh
      editor would have exported `light1`.

Under (b) a reused editor is measurably lossier than a fresh one for names, and uedcli's compare
keys actors by VERBATIM name (only property keys and class names are casefolded — `typedprops`), so
the drift would land straight on the verify.

METHOD: a FRESH editor that has loaded nothing else, `MAP LOAD` one map whose package stores the
LOWERCASE spelling, export, and read the spelling back. Lowercase => (b). Capitalised => (a).

    name_case_probe.py <outdir> [MAP.dx]
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(_REPO))

from uedcli import container_assets, editor, xfer                        # noqa: E402
from uedcli.driver import Driver, to_z_path                              # noqa: E402
from uedcli.model import parse_t3d                                       # noqa: E402
from uedcli.native.pkg_write import parse_package                        # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_exports import ASSET_DIRS, DX                               # noqa: E402

# A map whose OWN name table stores the lowercase spelling — so the two hypotheses predict
# different, unmistakable answers.
DEFAULT_MAP = "15_Area51_Page.dx"
PROBE_NAME = "light1"

# A FRESH per-run editor id: the whole question is what an editor that has loaded nothing else does,
# so this must never reuse the sweep's container.
EDITOR_ID = "namecase-probe"


def main() -> int:
    outdir = Path(sys.argv[1])
    outdir.mkdir(parents=True, exist_ok=True)
    mapname = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_MAP

    stored = [n for n in parse_package((DX / "Maps" / mapname).read_bytes()).names
              if n.lower() == PROBE_NAME]
    print(f"{mapname}: package name table stores {stored}", flush=True)
    if stored != [PROBE_NAME]:
        raise SystemExit(f"fixture assumption broken — expected the package to store the lowercase "
                         f"{PROBE_NAME!r}, found {stored}. Pick another map.")

    state = _REPO / "_scratch" / "namecase" / "state"
    state.mkdir(parents=True, exist_ok=True)
    mounts = container_assets.resource_mounts(ASSET_DIRS)
    maps_mount = next(m.container_dir for m in mounts if Path(m.host_dir).name == "Maps")
    container = editor.ensure_editor(EDITOR_ID, state_dir=state, mounts=mounts)
    print(f"FRESH editor ready: {container}", flush=True)
    driver = Driver(container)

    marker = "/work/namecase.t3d"
    subprocess.run(["docker", "exec", container, "rm", "-f", marker],
                   capture_output=True, text=True)
    script = outdir / "namecase.cmd"
    # `MAP NEW` first for the same reason the sweep needs it: `EXEC` does not abort on a failed
    # line, so without it a failed LOAD would export whatever was resident and look like a result.
    script.write_text(f"MAP NEW\n"
                      f"MAP LOAD FILE={to_z_path(f'{maps_mount}/{mapname}')}\n"
                      f"MAP EXPORT FILE={to_z_path(marker)}\n")
    driver.exec(f"EXEC {to_z_path(xfer.cp_in(container, str(script), ext='txt'))}")

    deadline = time.time() + 600
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
        time.sleep(2.0)
    else:
        raise SystemExit("editor never produced the export")

    host = outdir / "namecase-ued.t3d"
    xfer.cp_out(container, marker, str(host))
    txt = host.read_text()
    lvl = parse_t3d(txt)
    if len(lvl.actors) <= 3:
        raise SystemExit("the editor exported an EMPTY level — MAP LOAD failed")

    spellings = sorted(set(re.findall(rf"Name=({PROBE_NAME})\b", txt, flags=re.IGNORECASE)))
    print(f"\n  actors exported: {len(lvl.actors)}", flush=True)
    print(f"  spelling(s) the FRESH editor wrote: {spellings}", flush=True)
    print("\n== VERDICT ==", flush=True)
    if spellings == [PROBE_NAME]:
        print("  (b) HISTORY-DEPENDENT — a fresh editor preserves the package's spelling, so the "
              "capitalised form seen in the sweep came from a name registered EARLIER in that "
              "session. A reused editor's exported names drift with what it built before.",
              flush=True)
    else:
        print("  (a) CONSTANT — even a fresh editor re-cases the name, so the spelling comes from "
              "the editor's own startup name table, not from session history. Reuse does not make "
              "this worse; the editor is simply never authoritative on name case.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
