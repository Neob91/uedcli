#!/usr/bin/env python3
r"""Live GDB capture: inside `bspBuild` (`Editor.dll 0x10035ef0`, resolved live via `vtable_dump.py`),
dump `ebx` ("this" — the SAME persistent world Model `bspRepartition` passes through to all 4 of its
sub-calls) vs `esi` (`bspBuild`'s own arg1, "CTX" — the object `EmptyModel` is actually called ON,
`mov ecx, esi; call EmptyModel`, per the 2026-08-30 disassembly) for EVERY `bspBuild` invocation in
one `MAP REBUILD` — i.e. once per `bspRepartition` call (world-level + every subtree call).

WHY. `unatco-verts-points-residual-after-the-zone` / `wanchai-verts-points-residual-independently`:
full disassembly of `bspRepartition` (2026-08-30) found it's a short dispatcher (4 sequential virtual
calls, no extra logic after `bspRefresh`) that passes the SAME persistent Model as `this` to all 4 —
but `bspBuild` (vtable `+0x1fc`) computes its OWN separate "CTX" pointer (`esi`, via TWO levels of
indirection: `arg1` itself, where `arg1 = [[Model+0xa8]+0x98]`, computed fresh inside `bspRepartition`
per sub-call) and calls `UModel::EmptyModel` (a real, named, non-virtual import,
`Engine.dll!EmptyModel@UModel@@QAEXHH@Z`) ON THAT — not on `ebx` (Model itself). If `esi != ebx`
(a real, distinct object) and/or `esi` VARIES across different `bspBuild` calls in the same
`MAP REBUILD`, that's the "scratch model per subtree" mechanism this investigation has been
suspecting since the `Nodes.Num`-flat-at-baseline contradiction was first found — this dump settles
it directly, live, cheaply (one MAP REBUILD, breakpoint hit count = number of bspRepartition calls,
~120-210).

Break address `0x10035f27` = right after `mov esi, [ebp+8]` (raw CTX, un-dereferenced) and after
`mov ebx, ecx` (persistent Model) — both already set, before anything overwrites them.

Usage:  bspbuild_ctx_dump.py [golden.dx]   (default: Wanchai's golden, the coordinator's steer —
        119 subtree calls, of which 9 are known-affected and 110 known-clean, per the sibling board
        item `wanchai-verts-points-residual-independently`)
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

GOLDEN = Path(sys.argv[1]) if len(sys.argv) > 1 else (ROOT / "_scratch/golden_wanchai_world.dx")
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
break *0x10049fc0
commands
silent
set $callidx = $callidx + 1
set $child = *(int *)($esp + 8)
continue
end
break *0x10035f27
commands
silent
printf "CTXDUMP callidx=%d child=%d ebx_model=%#x esi_ctx=%#x same=%d ebx_nodes=%d esi_nodes=%d\n", $callidx, $child, $ebx, $esi, ($ebx==$esi), *(int*)($ebx+0x5c), *(int*)($esi+0x5c)
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

    container = "uned-bspbuild-ctx"
    O.stop_dbg_editor(container, state_dir)
    print(f"[ctxdump] golden={GOLDEN}", flush=True)
    print(f"[ctxdump] starting {container} ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        print(f"[ctxdump] editor pid {pid}; attaching gdb ...", flush=True)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/bctx.gdb"],
                       input=GDB.format(pid=pid), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/bctx.gdb > /tmp/bctx.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/bctx.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[ctxdump] attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        prev, quiet, deadline = -1, 0.0, time.monotonic() + DEADLINE
        while quiet < QUIET_FOR:
            if time.monotonic() > deadline:
                print(f"[ctxdump] WARNING: gave up after {DEADLINE:.0f}s, {max(prev,0)} hits seen",
                      flush=True)
                break
            n = subprocess.run(["docker", "exec", container, "bash", "-c",
                                "grep -c '^CTXDUMP ' /tmp/bctx.log 2>/dev/null || true"],
                               capture_output=True, text=True).stdout.strip()
            n = int(n or 0)
            quiet = quiet + POLL if (n == prev and n > 0) else 0.0
            prev = n
            time.sleep(POLL)
        out = HERE.parent / "logs" / "bspbuild-ctx-dump.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/bctx.log"],
                                       capture_output=True).stdout)
        print(f"[ctxdump] wrote {out} ({prev} hits)", flush=True)
    finally:
        O.stop_dbg_editor(container, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
