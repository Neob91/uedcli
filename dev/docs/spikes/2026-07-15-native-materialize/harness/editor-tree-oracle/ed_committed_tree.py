#!/usr/bin/env python3
r"""EDITOR committed (pre-repartition) world tree for ANY golden .dx.

`repart_stage_unatco.py` proves the world repartition is `bspRepartition`'s FIRST invocation in a
`MAP REBUILD`, so a breakpoint at its entry (`Editor.dll 0x49fc0`), dumping `Model->Nodes` once and
detaching, captures exactly the committed incremental-CSG tree the repartition consumes — the state
native prints under `UEDCLI_BSPCSG_TREE_STRUCT`.

Line format matches `committed_tree_diff.py`'s `_ED` regex ("ND <i> plane=... iF=... iB=... iP=...
isurf=... nv=...").

Usage: ed_committed_tree.py <golden.dx> <out.log>
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
HERE = HARNESS / "editor-tree-oracle"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HARNESS)); sys.path.insert(0, str(HERE))
import editor_tree_oracle as O                                   # noqa: E402
from uedcli import config                                        # noqa: E402
from uedcli.container_assets import resource_mounts              # noqa: E402
from uedcli.driver import Driver, to_z_path                      # noqa: E402

GOLDEN = Path(sys.argv[1])
OUT = Path(sys.argv[2])
PROJECT_DIR = ROOT / "_scratch/oracle-project"
DEADLINE = 1200.0          # rules/background-work.md's ~20-minute hang detector
ATTACH_TIMEOUT = 120.0

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
break *0x10049fc0
commands
silent
set $m = *(unsigned int *)($esp + 4)
set $nd = *(unsigned int *)($m + 0x58)
set $nn = *(int *)($m + 0x5c)
printf "TREEBEGIN num=%d\n", $nn
set $i = 0
while $i < $nn
  set $n = $nd + $i * 0x40
  printf "ND %d plane=%.5f,%.5f,%.5f,%.5f iF=%d iB=%d iP=%d isurf=%d nv=%d nf=%#x\n", $i, *(float *)($n), *(float *)($n+4), *(float *)($n+8), *(float *)($n+0xc), *(int *)($n+0x24), *(int *)($n+0x20), *(int *)($n+0x28), *(int *)($n+0x1c), *(unsigned char *)($n+0x36), *(unsigned char *)($n+0x37)
  set $i = $i + 1
end
printf "TREEEND\n"
detach
quit
end
printf "ORACLE_ATTACHED\n"
continue
"""


def _grep(container, needle, log="/tmp/ect.log"):
    return subprocess.run(["docker", "exec", container, "bash", "-c",
                           f"grep -c {needle} {log} 2>/dev/null || true"],
                          capture_output=True, text=True).stdout.strip()


def main():
    if not PROJECT_DIR.exists():
        PROJECT_DIR.mkdir(parents=True, exist_ok=True)
        (PROJECT_DIR / "uedcli.toml").write_text('game = "deusex"\n')

    O._ensure_dbg_image()
    project = config.load_project(str(PROJECT_DIR))
    mounts = resource_mounts(config.composed_search_dirs(project, config.load_user_config()))
    state_dir = config.state_dir(project.root, create=True)

    container = "uned-committedtree"
    O.stop_dbg_editor(container, state_dir)
    print(f"starting {container} (golden={GOLDEN}) ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/ect.gdb"],
                       input=GDB.format(pid=pid), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/ect.gdb > /tmp/ect.log 2>&1"], check=True)
        # Driving `MAP REBUILD` before gdb is attached silently produces an EMPTY log — the whole run
        # then looks like "the editor wedged" when it actually finished unobserved.  So a failed
        # attach is an error, not a warning.
        attach_deadline = time.monotonic() + ATTACH_TIMEOUT
        while _grep(container, "ORACLE_ATTACHED") in ("", "0"):
            if time.monotonic() > attach_deadline:
                print(f"gdb never attached within {ATTACH_TIMEOUT:.0f}s "
                      f"(container {container}) — nothing captured", file=sys.stderr)
                return 1
            time.sleep(0.5)
        print("attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        deadline = time.monotonic() + DEADLINE
        while _grep(container, "TREEEND") in ("", "0"):
            if time.monotonic() > deadline:
                # A partial dump is a silent half-answer: `committed_tree_diff.py` would read the
                # truncated node array as a real count difference.  Name it and fail.
                OUT.parent.mkdir(parents=True, exist_ok=True)
                OUT.write_bytes(subprocess.run(
                    ["docker", "exec", container, "cat", "/tmp/ect.log"],
                    capture_output=True).stdout)
                print(f"no TREEEND within {DEADLINE:.0f}s — {OUT} is PARTIAL, do not diff it",
                      file=sys.stderr)
                return 1
            time.sleep(2.0)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/ect.log"],
                                       capture_output=True).stdout)
        print(f"wrote {OUT}", flush=True)
        for line in OUT.read_text(errors="replace").splitlines():
            if line.startswith("TREEBEGIN"):
                print("  " + line)
    finally:
        O.stop_dbg_editor(container, state_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
