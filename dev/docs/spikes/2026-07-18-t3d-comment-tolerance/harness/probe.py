#!/usr/bin/env python3
"""Empirical probe: how does UnrealEd's MAP IMPORTADD T3D parser handle comments and unknown
properties inside/around an actor block?

For each test case we spin (or reuse) an ephemeral UED22 editor, `MAP NEW`, write a one-actor
`Begin Map … End Map` T3D containing the variant, `MAP IMPORTADD` it, then `MAP EXPORT` and inspect:
  - did the actor import at all?           (actor-present in the export)
  - was the carrier stripped or preserved? (comment/unknown-prop present in the export)
  - did the editor error / crash / wedge?  (a DriverError from wine_ctl's per-command liveness gate)
  - what did Editor.log say?               (tail after the import)

A crashing case is isolated: on a DriverError we tear the editor down and boot a fresh one for the
next case, so one wedge never poisons the rest. Run with the dev venv:
    .venv/bin/python dev/docs/spikes/2026-07-18-t3d-comment-tolerance/harness/probe.py
Results print as JSON to stdout; raw exports land under the scratch OUT dir.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

# make `import uedctl.*` work when run straight from the repo
HERE = Path(__file__).resolve()
# harness/ → spike/ → spikes/ → dev/ → docs/ → uedctl(tool root, holds the `uedctl` package)
TOOL_ROOT = HERE.parents[5]            # …/Tools/uedctl
sys.path.insert(0, str(TOOL_ROOT))

from uedctl import editor as ued_editor   # noqa: E402
from uedctl import xfer                    # noqa: E402
from uedctl.driver import Driver, DriverError, to_z_path  # noqa: E402

EDITOR_LOG = "/opt/UED22/Editor.log"
LONG_PATH = "castle.tower.roof.window.frame.hinge.upperleft.rivet.detail0123456789"  # >64 chars

# Each case: a full Begin Map … End Map body. All use a Light (point actor → IMPORTADD path),
# always resolvable (Engine.Light) with no package mounts.
def _block(inner: str) -> str:
    return f"Begin Map\n{inner}\nEnd Map\n"

CASES: dict[str, str] = {
    # control — must import cleanly; the reference the others are judged against
    "control": _block(
        "Begin Actor Class=Light Name=ProbeLight0\n"
        "    Location=(X=0.000000,Y=0.000000,Z=64.000000)\n"
        "End Actor"),
    # a // line-comment BETWEEN properties inside the actor block
    "line_comment_inside": _block(
        "Begin Actor Class=Light Name=ProbeLight0\n"
        "    Location=(X=0.000000,Y=0.000000,Z=64.000000)\n"
        "    // uedctl-folder: castle.tower.roof\n"
        "    LightBrightness=32\n"
        "End Actor"),
    # a /* block comment */ inside the actor block
    "block_comment_inside": _block(
        "Begin Actor Class=Light Name=ProbeLight0\n"
        "    Location=(X=0.000000,Y=0.000000,Z=64.000000)\n"
        "    /* uedctl-folder: castle.tower.roof */\n"
        "    LightBrightness=32\n"
        "End Actor"),
    # a ; semicolon-comment inside (ini-style; some Unreal text readers honor it)
    "semicolon_comment_inside": _block(
        "Begin Actor Class=Light Name=ProbeLight0\n"
        "    Location=(X=0.000000,Y=0.000000,Z=64.000000)\n"
        "    ; uedctl-folder: castle.tower.roof\n"
        "    LightBrightness=32\n"
        "End Actor"),
    # an UNKNOWN string property (no such UProperty on Light) — long value, no FName length limit
    "unknown_prop": _block(
        "Begin Actor Class=Light Name=ProbeLight0\n"
        "    Location=(X=0.000000,Y=0.000000,Z=64.000000)\n"
        f'    UedctlFolder="{LONG_PATH}"\n'
        "    LightBrightness=32\n"
        "End Actor"),
    # a stray // line BEFORE the actor block (inside Begin Map, between blocks)
    "stray_line_before_actor": _block(
        "    // uedctl-folder: castle.tower.roof\n"
        "Begin Actor Class=Light Name=ProbeLight0\n"
        "    Location=(X=0.000000,Y=0.000000,Z=64.000000)\n"
        "End Actor"),
}


def boot(state_dir: Path) -> tuple[str, str]:
    eid = "t3dcmt-" + uuid.uuid4().hex[:12]
    container = ued_editor.ensure_editor(eid, state_dir=state_dir, mounts=None, ready_timeout=120.0)
    return eid, container


def run_case(drv: Driver, name: str, t3d: str, out_dir: Path) -> dict:
    res: dict = {"case": name}
    # write the variant, cp into the container
    host_in = out_dir / f"{name}.in.t3d"
    host_in.write_text(t3d)
    cpath = xfer.cp_in(drv.container, str(host_in), ext="t3d")
    # fresh level, then import
    try:
        drv.map_new()
        drv.exec(f"MAP IMPORTADD FILE={to_z_path(cpath)}")
    except DriverError as e:
        res["import"] = "DRIVER_ERROR"
        res["error"] = str(e)[:400]
        return res
    res["import"] = "ok"
    # export + read back
    exp = xfer.work_path("t3d")
    try:
        drv.exec(f"MAP EXPORT FILE={to_z_path(exp)}")
        host_out = out_dir / f"{name}.out.t3d"
        xfer.cp_out(drv.container, exp, str(host_out))
        text = host_out.read_text(errors="replace")
    except DriverError as e:
        res["export"] = "DRIVER_ERROR"
        res["error"] = str(e)[:400]
        return res
    res["actor_present"] = "ProbeLight0" in text
    res["carrier_present"] = any(
        m in text for m in ("uedctl-folder", "UedctlFolder", LONG_PATH))
    res["export_len"] = len(text)
    # log tail
    try:
        log = drv.dexec_bash(f"tail -c 3000 {EDITOR_LOG} 2>/dev/null || true")
        interesting = [ln for ln in log.splitlines()
                       if any(k in ln for k in ("Error", "error", "Warning", "warning",
                                                "Failed", "Unknown", "comment", "Comment",
                                                "Bad", "syntax"))]
        res["log_tail"] = interesting[-8:]
    except DriverError:
        res["log_tail"] = ["<log read failed>"]
    xfer.remove(drv.container, cpath, exp)
    return res


def main() -> None:
    out_dir = Path(os.environ.get("PROBE_OUT", tempfile.mkdtemp(prefix="t3dcmt-")))
    out_dir.mkdir(parents=True, exist_ok=True)
    state_dir = out_dir / "state"
    state_dir.mkdir(exist_ok=True)
    results: list[dict] = []
    eid, container = boot(state_dir)
    drv = Driver(container)
    try:
        for name, t3d in CASES.items():
            r = run_case(drv, name, t3d, out_dir)
            results.append(r)
            print(f"[{name}] {json.dumps(r)}", file=sys.stderr, flush=True)
            # a crash poisons the editor — reboot fresh for the next case
            if r.get("import") == "DRIVER_ERROR" or r.get("export") == "DRIVER_ERROR":
                ued_editor.stop_editor(eid, state_dir)
                eid, container = boot(state_dir)
                drv = Driver(container)
    finally:
        ued_editor.stop_editor(eid, state_dir)
    print(json.dumps({"out_dir": str(out_dir), "results": results}, indent=2))


if __name__ == "__main__":
    main()
