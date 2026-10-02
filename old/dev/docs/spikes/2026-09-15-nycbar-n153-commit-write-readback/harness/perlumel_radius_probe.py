#!/usr/bin/env python3
r"""Round 9 (2026-09-15), second probe: round 9's FIRST probe (`commit_write_readback_probe.py`)
falsified the "commit gets dropped" theory -- Light5 IS committed into `CandidateLights[iSurf]` for
world surf 67/95/97 (`before=0, after=1` at the write site), AND `illuminateSurf`'s own read gate sees
that nonzero count (`count=1` for all three, at the exact same `this`/base pointer as the write) -- so
the per-light raytrace LOOP does start running for Light5 on all three surfaces. The exclusion is
therefore INSIDE that per-light loop, after the count check, before the raytrace call -- new territory
no prior round of this item reached (they all focused on `GetVisibleSurfs`/`OccludeBsp`, upstream of
the commit).

**Static finding**: `illuminateSurf`'s per-light loop (RVA `0x100a5920`-`0x100a5a7f`, nested lumel
U/V loops) computes, per LUMEL (not per surf): the lumel's projected WORLD position
(`[ebp-0x7c]/-0x78/-0x74`, via texture-axis dot products) and the squared distance from that position
to the CURRENT LIGHT's `Location` (`esi+0xd0/0xd4/0xd8`). At RVA `0x100a5971`
(`comiss xmm1,xmm0` -- xmm1 = the light's `WorldLightRadius^2`, cached once per light at
`[ebp-0x20]`; xmm0 = the just-computed per-lumel distSq), `jbe 0x100a5a1a` (RVA `0x100a5974`) skips
the raytrace call (`0x100a5a04`, matching round 3/4's own documented address exactly) for THIS LUMEL
if `radius^2 <= distSq` (light farther than radius from this specific lumel's world position).

This is a DIFFERENT, finer-grained radius test than the one round 6/8 already ruled out (that one
tested the SURF's PLANE distance once per surf, in the GATHER phase, before the commit -- 145-161uu,
well inside Light5's 325uu radius). This one tests the true 3D distance from the light to each
individual LUMEL's world position, inside `illuminateSurf`, per lumel -- unexplored territory. If it
rejects on literally EVERY lumel of surf 67/95/97 for Light5, that fully explains round 3's
"shadow-ray call site never fires even once" finding without needing any new/wrong gate -- it would
just mean these particular lumels are genuinely farther than 325uu from Light5's position (unlike the
surf's overall plane distance), and native's own per-lumel radius model needs checking against this.

Breakpoint at RVA `0x100a5971` (`comiss xmm1,xmm0`, before it executes -- both operands already
computed): reads `iSurf` (derived from `[ebp-0x28]` [SurfPtr] and `*([ebp-0x48])+0x98` [Model's
Surfs.Data base], the same identity used throughout this item), the light pointer (`esi`), the
lumel's projected world position (`[ebp-0x7c]/-0x78/-0x74`), `radius^2` (`$xmm1`) and `distSq`
(`$xmm0`) directly off the FPU registers.

Usage: perlumel_radius_probe.py --trunk <subset-trunk-dir> [--out log]
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OLD_HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
OLD_ORACLE = OLD_HARNESS / "editor-tree-oracle"
LADDER = ROOT / "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness"
UNBUILT = ROOT / "dev/docs/spikes/2026-09-02-unbuilt-structure-parity/harness"
HERE = Path(__file__).resolve().parent
for p in (ROOT, OLD_HARNESS, OLD_ORACLE, LADDER, UNBUILT):
    sys.path.insert(0, str(p))

import editor_tree_oracle as O  # noqa: E402
from uedcli import config, trunk  # noqa: E402
from uedcli.apply import _level_referenced_packages  # noqa: E402
from uedcli.container_assets import resource_mounts  # noqa: E402
from uedcli.driver import Driver, to_z_path  # noqa: E402
from uedcli.emit import emit_map  # noqa: E402
from uedcli.materialize import levelinfo_first_order  # noqa: E402
from uedcli.packages import editor_search_dirs, ensure_load  # noqa: E402
from build_ued_import_built_golden import _dummy_builder_actor  # noqa: E402
from build_ued_import_golden import _quote_str_props  # noqa: E402
from build_ued_golden import _scratch_project  # noqa: E402

CONTAINER = "uned-n153-perlumel-rad4"

RADIUS_TEST = 0x100A5971  # `comiss xmm1,xmm0` -- xmm1=WorldLightRadius^2, xmm0=per-lumel distSq
# `[ebp-0x24]` is a per-SURF (not per-light) pointer computed once at illuminateSurf's own prologue
# (`Model+0x98` -> a wrapper whose `+0xa8` field, indexed by `iLightMap*5*8`, gives this address) --
# almost certainly `&Model.LightMap[iLightMap]`, the FLightMapIndex record itself. The nested lumel
# loop containing RADIUS_TEST is bounded by `[that+0x1c]`/`[that+0x20]` (probably UClamp/VClamp, the
# lumel grid's texel dimensions). Zero hits at RADIUS_TEST for isurf 67/95/97 in the first run of this
# probe raised the question of whether this loop runs AT ALL for these records -- this breakpoint
# reads the loop's own bounds directly, right before the outer bound test.
LOOP_BOUND_TEST = 0x100A58D4  # `cmp ebx,[ecx+0x20]` -- ecx = &Model.LightMap[iLightMap], just loaded
# The actual per-lumel shadow-ray call round 3/4 already documented (`illuminate_ray_probe.py`,
# confirmed here by static disasm at RVA 0x100a5a04: `call [eax+0x58]`, right after the radius-cull
# accept path falls through with no further conditional gate). Round 3 found ZERO hits here for
# Light5/surf 67/95/97; this run's RADIUS_TEST results show SOME lumels on these very surfaces DO
# pass the radius cull (reject=0) for Light5 -- so this breakpoint re-checks, live, whether the call
# really never fires for those specific accepting lumels, or whether round 3's probe missed them.
RAYTRACE_CALL = 0x100A5A04
RAYTRACE_RET = 0x100A5A07  # right after `call [eax+0x58]` returns -- eax = LineCheck result

GDB_TEMPLATE = r"""
set pagination off
set confirm off
set height 0
set width 0
attach __PID__
handle SIGSEGV nostop noprint pass
handle SIGUSR1 nostop noprint pass
handle SIGUSR2 nostop noprint pass
handle SIGPIPE nostop noprint pass

set $rthits = 0
set $last_hot = 0

break *__RAYTRACE_CALL__
commands
silent
set $rthits = $rthits + 1
set $light3 = *(unsigned int*)($ebp-0x1c)
set $lx3 = *(float*)($light3+0xd0)
set $lux = *(float*)($ebp-0x7c)
if $lx3 > -2945 && $lx3 < -2943 && $lux <= -3080
set $last_hot = 1
printf "RT hit=%d light=%#x lumel=%.9g,%.9g,%.9g\n", $rthits, $light3, $lux, *(float*)($ebp-0x78), *(float*)($ebp-0x74)
else
set $last_hot = 0
end
continue
end

break *__RAYTRACE_RET__
commands
silent
if $last_hot == 1
printf "RTRET hit=%d eax=%d\n", $rthits, $eax
end
continue
end

printf "ORACLE_ATTACHED\n"
continue
"""


def main() -> int:
    trunk_dir = None
    out = HERE.parent / "logs" / "perlumel-radius-n153.log"
    for i, a in enumerate(sys.argv):
        if a == "--trunk":
            trunk_dir = Path(sys.argv[i + 1]).resolve()
        if a == "--out":
            out = Path(sys.argv[i + 1]).resolve()
    if trunk_dir is None:
        print(__doc__)
        return 2

    user_config = config.load_user_config()
    project = _scratch_project(trunk_dir, "deusex")
    search_dirs = config.composed_search_dirs(project, user_config)
    mounts = resource_mounts(search_dirs)
    host_search_dirs = editor_search_dirs(search_dirs)

    lvl, _ = trunk.read_level(trunk_dir)
    classes = {n: lvl.actors[n].cls for n in lvl.order}
    has_brush = {n: lvl.actors[n].brush is not None for n in lvl.order}
    imp_order = levelinfo_first_order(lvl.order, classes, has_brush)
    _quote_str_props(lvl, imp_order, project, user_config)
    actors = [lvl.actors[n] for n in imp_order]
    actors.insert(1, _dummy_builder_actor())
    ref_pkgs = _level_referenced_packages(
        type("L", (), {"actors": {n: lvl.actors[n] for n in imp_order}})())

    O._ensure_dbg_image()
    state_dir = config.state_dir(project.root, create=True)
    O.stop_dbg_editor(CONTAINER, state_dir)
    print(f"[perlumel] {trunk_dir.name}; starting {CONTAINER}", flush=True)
    try:
        O.start_dbg_editor(CONTAINER, mounts, state_dir)
    except subprocess.CalledProcessError as ex:
        # This host intermittently has `docker compose run -d` report exit 1 even though the
        # container starts and boots fine (confirmed repeatedly: `docker logs` shows a clean
        # "editor main frame" boot regardless). Tolerate it here; fail for real below if the
        # container truly isn't up.
        print(f"[perlumel] start_dbg_editor reported {ex} -- checking if the container is up anyway",
              flush=True)
        up = "false"
        for _ in range(10):
            up = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER],
                                capture_output=True, text=True).stdout.strip()
            if up == "true":
                break
            time.sleep(1.0)
        if up != "true":
            raise
        print("[perlumel] container is running despite the reported error; continuing", flush=True)
    try:
        drv = Driver(container=CONTAINER)
        t3d_path = drv.write_work_file(emit_map(actors), ext="t3d")
        pid = O._editor_pid(CONTAINER)
        script = GDB_TEMPLATE.replace("__PID__", str(pid)).replace(
            "__RAYTRACE_CALL__", hex(RAYTRACE_CALL)).replace(
            "__RAYTRACE_RET__", hex(RAYTRACE_RET))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/perlumel.gdb"],
                       input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/perlumel.gdb > /tmp/perlumel.log 2>&1"], check=True)
        for _ in range(240):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/perlumel.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            dbg = subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/perlumel.log"],
                                 capture_output=True, text=True).stdout
            print(f"[perlumel] gdb log so far:\n{dbg}", flush=True)
            raise RuntimeError("gdb did not attach")
        print("[perlumel] attached; running the golden EXEC batch ...", flush=True)
        saved = "/work/probe_perlumel.dx"
        drv.begin_script()
        ensure_load(drv, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        drv.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
        drv.exec("MAP REBUILD")
        drv.light_apply()
        drv.exec(f"MAP SAVE FILE={to_z_path(saved)}")
        try:
            drv.run_script(produces=saved, timeout=1800.0)
        except Exception as ex:
            print(f"[perlumel] batch wait ended: {ex}", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        log_bytes = subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/perlumel.log"],
                                   capture_output=True).stdout
        out.write_bytes(log_bytes)
        print(f"[perlumel] wrote {out} ({len(log_bytes)} bytes)", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
