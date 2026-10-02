#!/usr/bin/env python3
r"""Dump every BSP node's LIVE `NodeFlags` at the moment `LIGHT APPLY` traces a chosen surface.

Why: UNATCO N=26's world Model diverges only in lighting — the editor lists `Light155` on three
`Brush420` surfaces and native does not. Native's shadow-ray walker (`linecheck.rs`) is a verified
port of `Editor.dll 0x17ce190`, and both builds' BSP is byte-identical, so the only remaining input
that can differ is the node `NodeFlags` the walker READS. Those flags include renderer scratch bits
(`NF_PolyOccluded 0x08`, `NF_BoxOccluded`/`NF_BrightCorners 0x10`) that the parity gate excludes from
the saved package — but `IsCsg` tests `NodeFlags & (ExtraNodeFlags|0x21)`, and at a CROSSING site the
walker does NOT strip `0x10` (`0x17ce32f`/`0x17ce34e`/`0x17ce3d8`/`0x17ce3f2` have no `and $0xef`),
so a live `0x10` makes a node non-occluding for a `PF_BrightCorners` ray. This probe reads the flags
the editor actually holds at trace time so the hypothesis can be tested offline
(`replay_all.py --flags <dump>`).

Method: `MAP LOAD <built .dx>` (keeps the saved Model verbatim), attach gdb, arm on
`illuminateSurf` (`0x100a5043`) entering with `iSurf == --isurf`, then at the first shadow-ray
walker entry (`0x17ce193`) walk `Model->Nodes` — base `*(Model+0x58)`, stride 64, `NumVertices` at
`+0x36`, `NodeFlags` at `+0x37`; the walker's own arg `0xc(%ebp)` is the Model — and print every
node's flags before continuing.

Usage: nodeflags_at_lightapply.py <built.dx> --isurf N --nodes N [--out dump.txt]
"""
from __future__ import annotations

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

PROJECT_DIR = ROOT / "_scratch/oracle-project"
CONTAINER = "uned-lightapply-nodeflags"

GDB = r"""
set pagination off
set confirm off
set height 0
set width 0
attach __PID__
handle SIGSEGV nostop noprint pass
handle SIGUSR1 nostop noprint pass
handle SIGUSR2 nostop noprint pass
handle SIGPIPE nostop noprint pass

set $armed = 0
set $dumped = 0

break *0x100a5043
commands
silent
set $hit = *(int*)($ebp+0xc)
if $armed == 0 && $hit == __ISURF__
  set $armed = 1
  printf "SURF_ENTER isurf=%d\n", $hit
  break *0x17ce193
  commands
  silent
  if $dumped == 0
    set $dumped = 1
    set $model = *(unsigned int*)($ebp+0x0c)
    set $nodes = *(unsigned int*)($model+0x58)
    printf "MODEL=0x%x NODES=0x%x xf=0x%x\n", $model, $nodes, *(unsigned int*)($ebp+0x38)
    set $i = 0
    while $i < __NODES__
      printf "NODE %d flags=0x%02x nv=%d\n", $i, *(unsigned char*)($nodes+$i*64+0x37), *(unsigned char*)($nodes+$i*64+0x36)
      set $i = $i + 1
    end
    printf "TARGET_DONE\n"
    detach
    quit
  end
  continue
  end
  continue
end
continue
end

printf "ORACLE_ATTACHED\n"
continue
"""


def main() -> int:
    built = Path(sys.argv[1]).resolve()
    isurf = nnodes = None
    out = HERE.parent / "logs" / "nodeflags-at-lightapply.log"
    for i, a in enumerate(sys.argv):
        if a == "--isurf":
            isurf = int(sys.argv[i + 1])
        if a == "--nodes":
            nnodes = int(sys.argv[i + 1])
        if a == "--out":
            out = Path(sys.argv[i + 1]).resolve()
    if not built.exists() or isurf is None or nnodes is None:
        print(__doc__)
        return 2

    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    (PROJECT_DIR / "uedcli.toml").write_text('game = "deusex"\n')
    O._ensure_dbg_image()
    project = config.load_project(str(PROJECT_DIR))
    mounts = resource_mounts(config.composed_search_dirs(project, config.load_user_config()))
    state_dir = config.state_dir(project.root, create=True)

    O.stop_dbg_editor(CONTAINER, state_dir)
    print(f"[nodeflags] {built.name} isurf={isurf} nodes={nnodes}; starting {CONTAINER}", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /work/built.dx"],
                       input=built.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/built.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(CONTAINER)
        script = (GDB.replace("__PID__", str(pid)).replace("__ISURF__", str(isurf))
                  .replace("__NODES__", str(nnodes)))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/nf.gdb"],
                       input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/nf.gdb > /tmp/nf.log 2>&1"], check=True)
        for _ in range(120):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/nf.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[nodeflags] attached; LIGHT APPLY ...", flush=True)
        drv.exec("LIGHT APPLY")
        deadline = time.monotonic() + 900.0
        while time.monotonic() < deadline:
            done = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                   "grep -c '^TARGET_DONE' /tmp/nf.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                break
            time.sleep(3.0)
        else:
            print("[nodeflags] WARNING: gave up waiting", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/nf.log"],
                                       capture_output=True).stdout)
        print(f"[nodeflags] wrote {out}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
