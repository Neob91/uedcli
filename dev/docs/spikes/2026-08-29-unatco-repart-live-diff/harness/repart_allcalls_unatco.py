#!/usr/bin/env python3
r"""Live GDB capture: `Model->Nodes.Num` at `bspRepartition` ENTRY, after its `bspBuild`, and after
its `bspRefresh`, for EVERY one of the ~209 sub-calls (plus the world repartition, idx=1), in ONE
`MAP REBUILD` run.

STATUS (2026-08-29, `unatco-verts-points-residual-after-the-zone`): **the `Nodes.Num`-based reading
this script produces is a DEAD END — do not trust it, and do not resume this exact approach without
first explaining the contradiction below.** The original idea: get editor's real per-call node-count
delta for all 209 calls cheaply (one live run) instead of one expensive per-call `repart_child_trace.py`
capture (~5-10 min each). What it actually shows: `Nodes.Num` reads EXACTLY the pre-loop value (6314)
after literally every one of the 209 calls, with a TEMPORARY bump at the post-`bspBuild`,
pre-`bspRefresh` checkpoint matching exactly how many nodes that call's own `bspBuild` appended (e.g.
`child=4077`: entry 6314 -> post-bspBuild 6389 (+75) -> post-bspRefresh 6314). This is DIRECTLY
CONTRADICTED by independently-verified ground truth: `child=6108`'s real 29-node subtree (from
`repart_child_trace.py`'s live `ADD`-sequence capture, cross-validated structurally against native's
own isolated merge-and-resplit tree) occupies freshly-built array indices 6314-6342 — real, distinct,
necessary nodes for a correct final map — yet this script's reading claims the array is back at 6314
(as if nothing final was added) right after that same call. Ruled out as measurement bugs: the model
pointer (`$m`) is confirmed IDENTICAL across all 210 calls, and each of `ENTRY`/`POSTBUILD`/`CALLEND`
fires exactly once per call index (no duplicate/missing breakpoint hits). So `Model+0x5c`, read at
this specific PC inside the per-subtree repartition path, is not simply "how many live node entries
exist" — some other explanation (the offset means something else in this call path; `bspRefresh`
restores a saved pre-call checkpoint for unrelated bookkeeping and the real, final compaction happens
in a separate later pass this script never breaks on) is needed before any conclusion can be drawn
from these numbers. Kept committed, with this docstring, so a future session doesn't re-walk into the
same trap; the harness structure (multi-breakpoint, one live run over all 209 calls) may still be
useful once the `Nodes.Num` semantics here are actually understood.

MECHANISM (as originally intended, still accurate for what each breakpoint fires on — only the
INTERPRETATION of the node counts is unreliable): `bspRepartition` entry `0x10049fc0` (`esp+4`=Model,
`esp+8`=iChild) fires once per call (1 world + ~209 subtree), caching `$m`/`$child`; `0x1004a047`
("after bspBuild") and `0x1004a05f` ("after bspRefresh", both reused from `repart_stage_unatco.py`'s
validated offsets) fire once each per call, reusing the cached `$m` rather than re-reading `esp+4`
(which would be wrong there — the earlier, since-fixed version of this script had that exact bug).

Usage:  repart_allcalls_unatco.py [golden.dx]   ->  logs/repart-allcalls-unatco.log
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OLD_HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
OLD_ORACLE = OLD_HARNESS / "editor-tree-oracle"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(OLD_HARNESS))
sys.path.insert(0, str(OLD_ORACLE))
import editor_tree_oracle as O  # noqa: E402
from uedcli import config  # noqa: E402
from uedcli.container_assets import resource_mounts  # noqa: E402
from uedcli.driver import Driver, to_z_path  # noqa: E402

GOLDEN = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    ROOT / "_scratch/bsp-parity-proj/golden_unatco_control.dx")
PROJECT_DIR = ROOT / "_scratch/oracle-project"
POLL, QUIET_FOR, DEADLINE = 2.0, 20.0, 2400.0

GDB = r"""
set pagination off
set confirm off
set height 0
set width 0
attach {pid}
handle SIGSEGV nostop noprint pass
handle SIGUSR1 nostop noprint pass
handle SIGUSR2 nostop noprint pass
handle SIGPIPE nostop noprint pass
set $callidx = 0
set $child = -1
set $m = 0
break *0x10049fc0
commands
silent
set $callidx = $callidx + 1
set $m = *(unsigned int *)($esp + 4)
set $child = *(int *)($esp + 8)
printf "ENTRY idx=%d child=%d model=%#x nodes_at_entry=%d\n", $callidx, $child, $m, *(int *)($m + 0x5c)
continue
end
break *0x1004a047
commands
silent
printf "POSTBUILD idx=%d child=%d nodes=%d\n", $callidx, $child, *(int *)($m + 0x5c)
continue
end
break *0x1004a05f
commands
silent
printf "CALLEND idx=%d child=%d nodes=%d\n", $callidx, $child, *(int *)($m + 0x5c)
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


def main() -> int:
    if not PROJECT_DIR.exists():
        PROJECT_DIR.mkdir(parents=True, exist_ok=True)
        (PROJECT_DIR / "uedcli.toml").write_text('game = "deusex"\n')

    O._ensure_dbg_image()
    project = config.load_project(str(PROJECT_DIR))
    user_config = config.load_user_config()
    mounts = resource_mounts(config.composed_search_dirs(project, user_config))
    state_dir = config.state_dir(project.root, create=True)

    container = "uned-allcalls-unatco"
    O.stop_dbg_editor(container, state_dir)
    print(f"[allcalls] golden={GOLDEN}", flush=True)
    print(f"[allcalls] starting {container} ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        print(f"[allcalls] editor pid {pid}; attaching gdb ...", flush=True)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/rau.gdb"],
                       input=GDB.format(pid=pid), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/rau.gdb > /tmp/rau.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/rau.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[allcalls] attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        prev, quiet, deadline = -1, 0.0, time.monotonic() + DEADLINE
        while quiet < QUIET_FOR:
            if time.monotonic() > deadline:
                print(f"[allcalls] WARNING: gave up after {DEADLINE:.0f}s, {max(prev,0)} calls seen",
                      flush=True)
                break
            n = subprocess.run(["docker", "exec", container, "bash", "-c",
                                "grep -c '^CALLEND ' /tmp/rau.log 2>/dev/null || true"],
                               capture_output=True, text=True).stdout.strip()
            n = int(n or 0)
            quiet = quiet + POLL if (n == prev and n > 0) else 0.0
            prev = n
            time.sleep(POLL)
        out = HERE.parent / "logs" / "repart-allcalls-unatco.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/rau.log"],
                                       capture_output=True).stdout)
        print(f"[allcalls] wrote {out} ({prev} calls seen)", flush=True)
    finally:
        O.stop_dbg_editor(container, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
