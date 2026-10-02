#!/usr/bin/env python3
r"""Live GDB capture of `FSpanBuffer::MergeWith` (`render.dll` file RVA `0x1001e3b0`, i.e.
`0x1001e3b0 - 0x10000000` past render.dll's OWN preferred image base) during a real Wanchai
`LIGHT APPLY`.

**Confirmed live this session, `--probe`: render.dll does NOT load at its preferred base
0x10000000 in this wine process — it loads at 0x015b0000** (`/proc/PID/maps`; Engine.dll similarly
relocates to 0x01620000, core.dll to 0x019a0000). Only Editor.dll keeps its preferred 0x10000000
slot (matching every prior live capture in this repo, which all targeted Editor.dll addresses).
This was previously UNVERIFIED for render.dll — every existing "render.dll 0x1001XXXX"-style
citation in this codebase (`SUBTRACT_OCCLUSION`'s `PF_NONOCCLUDING` mask, the `CopyFromRaster`/
`CopyFromRasterUpdate` decode) is a STATIC FILE RVA (reading the .dll bytes directly, e.g. via
`rdis.py`), which is unaffected by runtime relocation — near `call`s and struct-relative offsets
are position-independent and remain byte-correct — but NONE of those addresses had been used as a
LIVE breakpoint before this script. A live VA must be computed as
`render_base + (static_va - 0x10000000)`, resolving `render_base` fresh from `/proc/PID/maps` each
run (this container's wine loader appears deterministic across restarts, but this script never
assumes so).

Step 1 (`--probe`): resolve render.dll's live base and read memory at the computed live address of
`MergeWith`'s entry, diffing the first bytes against the known static prologue (`push ebp; mov ebp,
esp; push -1; push <SEH-handler-RVA-relocated>`) to confirm addressing before a full capture.

Step 2 (default): break at 0x1001e3b0 (function entry, prologue NOT yet run — args at $ecx=this,
[esp+4]=Other per __thiscall/`ret 4`), dump `this`/`Other`'s StartY/EndY/ValidLines/Index/Mem, then
single-step to just before `ret` (address 0x1001e60c, the epilogue's first instruction, confirmed
static from the full decode) and re-dump `this`'s fields plus one row's raw Index[] linked-list
content (X0,X1 pairs) BEFORE and AFTER, for direct comparison against a Python re-implementation of
`merge_into`'s algorithm fed the same two input rows.

Usage: mergewith_live_check.py [golden.dx] [--hits N] [--probe]
  -> logs/mergewith-live-check.log
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

GOLDEN = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else (
    ROOT / "_scratch/wanchai-relight-2026-08-29/golden.dx")
HITS = 6
PROBE = "--probe" in sys.argv
for i, a in enumerate(sys.argv):
    if a == "--hits":
        HITS = int(sys.argv[i + 1])

PROJECT_DIR = ROOT / "_scratch/oracle-project"
CONTAINER = "uned-mergewith-check"
LOGF = HERE.parent / "logs" / "mergewith-live-check.log"

PROBE_GDB = r"""
set pagination off
set confirm off
set height 0
set width 0
attach __PID__
handle SIGSEGV nostop noprint pass
handle SIGUSR1 nostop noprint pass
handle SIGUSR2 nostop noprint pass
handle SIGPIPE nostop noprint pass
printf "PROBE_BYTES: "
x/16xb __MW_VA__
printf "PROBE_DONE\n"
detach
quit
"""

# One row's linked list is {X0,X1,Next}*4 (12-byte nodes, FMemStack-allocated) per the pre-existing
# CopyFromRaster/CopyFromRasterUpdate decode this session's ledger cites. Dump a row as a chain of
# up to 8 (X0,X1) pairs (plenty for Wanchai's clutter rows, bounded so a corrupt/cyclic chain can't
# hang gdb).
DUMP_ROW = r"""
set $p = {ptr}
set $k = 0
while $p != 0 && $k < 8
printf "  ROW{label} node=%#x X0=%d X1=%d\n", $p, *(int*)$p, *(int*)($p+4)
set $p = *(int*)($p+8)
set $k = $k + 1
end
"""

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
set $n = 0
break *__MW_VA__
commands
silent
set $this = $ecx
set $other = *(int*)($esp+4)
set $this_start = *(int*)($this)
set $this_end = *(int*)($this+4)
set $this_valid = *(int*)($this+8)
set $this_index = *(int*)($this+0xc)
set $other_start = *(int*)($other)
set $other_end = *(int*)($other+4)
set $other_valid = *(int*)($other+8)
set $other_index = *(int*)($other+0xc)
printf "HIT n=%d this=%#x this_start=%d this_end=%d this_valid=%d this_index=%#x other=%#x other_start=%d other_end=%d other_valid=%d other_index=%#x\n", $n, $this, $this_start, $this_end, $this_valid, $this_index, $other, $other_start, $other_end, $other_valid, $other_index
if $other_start < $other_end
set $y = $other_start
set $found_both = -1
set $found_other = -1
while $y < $other_end
set $orow_test = *(int*)($other_index + ($y - $other_start) * 4)
if $orow_test != 0
if $found_other == -1
set $found_other = $y
end
if $this_start <= $y && $y < $this_end
set $trow_test = *(int*)($this_index + ($y - $this_start) * 4)
if $trow_test != 0 && $found_both == -1
set $found_both = $y
end
end
end
set $y = $y + 1
end
set $y = $found_both
if $y == -1
set $y = $found_other
end
if $y != -1
printf "ROWCHOICE y=%d (both_nonnull_row=%d other_nonnull_row=%d)\n", $y, $found_both, $found_other
set $trow_ptr = $this_index + ($y - $this_start) * 4
set $orow_ptr = $other_index + ($y - $other_start) * 4
if $this_start <= $y && $y < $this_end
set $trow = *(int*)$trow_ptr
else
set $trow = 0
end
set $orow = *(int*)$orow_ptr
printf "PRE_THIS_ROW y=%d head=%#x\n", $y, $trow
"""

DUMP_PRE_THIS = DUMP_ROW.replace("{ptr}", "$trow").replace("{label}", "_PRE_THIS")
DUMP_PRE_OTHER = DUMP_ROW.replace("{ptr}", "$orow").replace("{label}", "_PRE_OTHER")

GDB_TAIL = r"""
set $bp2 = __EPI_VA__
break *$bp2
commands
silent
printf "AT_EPILOGUE this=%#x\n", $this
set $this_index2 = *(int*)($this+0xc)
set $this_start2 = *(int*)($this)
set $trow_ptr2 = $this_index2 + ($y - $this_start2) * 4
set $trow2 = *(int*)$trow_ptr2
printf "POST_THIS_ROW y=%d head=%#x\n", $y, $trow2
"""

DUMP_POST_THIS = DUMP_ROW.replace("{ptr}", "$trow2").replace("{label}", "_POST_THIS")

GDB_TAIL2 = r"""
delete 2
continue
end
else
printf "ROWCHOICE skip (no non-empty other row found in range)\n"
end
else
printf "ROWCHOICE skip (other range empty)\n"
end
set $n = $n + 1
if $n >= __HITS__
  printf "TARGET_DONE\n"
  detach
  quit
end
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


RENDER_PREFERRED_BASE = 0x10000000
MERGEWITH_STATIC_VA = 0x1001e3b0
EPILOGUE_STATIC_VA = 0x1001e60c


def _render_dll_base(container: str, pid: int) -> int:
    """Resolve render.dll's REAL runtime load base from /proc/PID/maps — confirmed live this
    session that it does NOT sit at its preferred 0x10000000 (only Editor.dll does, in this wine
    process; render.dll actually loads at 0x015b0000 in one observed run). Never assume it."""
    out = subprocess.run(
        ["docker", "exec", container, "bash", "-c", f"cat /proc/{pid}/maps"],
        capture_output=True, text=True, check=True,
    ).stdout
    for line in out.splitlines():
        if line.rstrip().lower().endswith("/opt/ued22/render.dll"):
            return int(line.split("-", 1)[0], 16)
    raise RuntimeError(f"render.dll not found in /proc/{pid}/maps")


def _live_va(render_base: int, static_va: int) -> int:
    return render_base + (static_va - RENDER_PREFERRED_BASE)


def build_gdb_script(hits: int, render_base: int) -> str:
    mw_va = _live_va(render_base, MERGEWITH_STATIC_VA)
    epi_va = _live_va(render_base, EPILOGUE_STATIC_VA)
    print(f"[mergewith-check] render.dll base={render_base:#x} MergeWith={mw_va:#x} "
          f"epilogue={epi_va:#x}", flush=True)
    return (
        (GDB + DUMP_PRE_THIS + DUMP_PRE_OTHER + GDB_TAIL + DUMP_POST_THIS + GDB_TAIL2)
        .replace("__HITS__", str(hits))
        .replace("__MW_VA__", hex(mw_va))
        .replace("__EPI_VA__", hex(epi_va))
    )


def main() -> int:
    if not GOLDEN.exists():
        print(f"[mergewith-check] golden not found: {GOLDEN}", file=sys.stderr)
        return 2
    if not PROJECT_DIR.exists():
        PROJECT_DIR.mkdir(parents=True, exist_ok=True)
        (PROJECT_DIR / "uedcli.toml").write_text('game = "deusex"\n')

    O._ensure_dbg_image()
    project = config.load_project(str(PROJECT_DIR))
    user_config = config.load_user_config()
    mounts = resource_mounts(config.composed_search_dirs(project, user_config))
    state_dir = config.state_dir(project.root, create=True)

    O.stop_dbg_editor(CONTAINER, state_dir)
    print(f"[mergewith-check] golden={GOLDEN} hits={HITS} probe={PROBE}", flush=True)
    print(f"[mergewith-check] starting {CONTAINER} ...", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(CONTAINER)
        render_base = _render_dll_base(CONTAINER, pid)
        print(f"[mergewith-check] editor pid {pid} render.dll base={render_base:#x}; "
              f"attaching gdb ...", flush=True)
        if PROBE:
            mw_va = _live_va(render_base, MERGEWITH_STATIC_VA)
            gdb_script = PROBE_GDB.replace("__MW_VA__", hex(mw_va))
        else:
            gdb_script = build_gdb_script(HITS, render_base)
        gdb_script = gdb_script.replace("__PID__", str(pid))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/mw.gdb"],
                       input=gdb_script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/mw.gdb > /tmp/mw.log 2>&1"], check=True)
        if PROBE:
            time.sleep(5.0)
        else:
            for _ in range(120):
                out = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                      "grep -c ORACLE_ATTACHED /tmp/mw.log 2>/dev/null || true"],
                                     capture_output=True, text=True).stdout.strip()
                if out and out != "0":
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError("gdb did not attach")
            print("[mergewith-check] attached; LIGHT APPLY ...", flush=True)
            drv.exec("LIGHT APPLY")
            deadline = time.monotonic() + 1800.0
            while time.monotonic() < deadline:
                done = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                       "grep -c '^TARGET_DONE' /tmp/mw.log 2>/dev/null || true"],
                                      capture_output=True, text=True).stdout.strip()
                if done and done != "0":
                    print("[mergewith-check] TARGET_DONE seen", flush=True)
                    break
                time.sleep(2.0)
            else:
                print("[mergewith-check] WARNING: gave up waiting", flush=True)
        LOGF.parent.mkdir(parents=True, exist_ok=True)
        LOGF.write_bytes(subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/mw.log"],
                                        capture_output=True).stdout)
        print(f"[mergewith-check] wrote {LOGF}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
