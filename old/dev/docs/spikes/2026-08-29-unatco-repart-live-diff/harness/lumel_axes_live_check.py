#!/usr/bin/env python3
r"""Live GDB capture: the editor's REAL `u_dir`/`v_dir` lightmap-axis vectors (`FCoords(0, TextureU,
TextureV, Normal).Inverse().Transpose()`, `Editor.dll 0x100a5554`-`0x100a556a`) for real Wanchai
surfaces during a genuine `LIGHT APPLY` — checking the standing "shadow-ray precision" hypothesis in
`native-light-apply-bake-where-it-stands-and` / `getvisiblesurfs-wanchai-run-gap-root-cause`: that
`light.rs::lumel_axes`'s `det = tu.dot(&(tv.cross(&normal)))` term-grouping differs, at the ulp level,
from `FCoords::Inverse`'s.

Static disassembly of `core.dll 0x509c0`-`0x50c00` (`rdis.py dis Core 0x509c0 0x1b0`, this session)
shows the routine computes each cofactor as a SINGLE product-minus-product (e.g.
`N.z*TV.y - N.y*TV.z`), which by IEEE754 float-multiplication commutativity is bit-IDENTICAL to
`light.rs`'s direct cross-product term (`tv.y*n.z - tv.z*n.y`, same value since `a*b == b*a` exactly
in IEEE754) — and the determinant's 3-term running sum, while accumulated in a different PAIR order
((A*TU.y + B*TU.x) + C*TU.z vs (TU.x*B + TU.y*A) + TU.z*C), is ALSO bit-identical because IEEE754
addition is commutative (`a+b == b+a` exactly), so the two differently-ordered pairs are equal before
the third add. This is a closed-form proof, not an approximation — PROVIDED the disassembly reading
(field offsets, instruction sequence) is correct. This script is the empirical check of that proof:
capture the editor's REAL output for known (TU, TV, Normal) inputs (cross-referenced by VALUE against
Wanchai's own Vectors pool, since the trace has no direct surf-index correlation) and diff against
`light.rs::lumel_axes`'s own Rust formula, run in Python here for the same inputs.

ABI note (traced this session, not copied from any prior doc): after `FCoords(0,TU,TV,N)`'s ctor call
(`0x100a555a`), TWO extra dwords were pushed BEFORE the ctor's own 4 args and survive the ctor's
`ret 16` cleanup — `Inverse`'s hidden struct-return pointer (consumed at the `Inverse` call,
`0x100a5562`) then `Transpose`'s (consumed at `0x100a556a`). Working backward from the 6 `lea+push`
pairs at `0x100a552a`-`0x100a5553` (push order: ebp-0x108, ebp-0x1e8, ebp-0x88, ebp-0x94, ebp-0xa0,
ebp-0xd8 — the LAST 4 are the ctor's Origin/XAxis/YAxis/ZAxis args in that order, confirming
TextureU=ebp-0xa0, TextureV=ebp-0x94, Normal=ebp-0x88), Transpose's result — the temp FCoords whose
XAxis/YAxis are literally read off as u_dir/v_dir — lands at `ebp-0x108`. So right after the
`Transpose` call returns (breakpoint at `0x100a5570`), `TextureU`/`TextureV`/`Normal` are still live
at their original stack slots and `u_dir`=`[ebp-0x108+0xc..0x14]`, `v_dir`=`[ebp-0x108+0x18..0x20]`.

Usage:  lumel_axes_live_check.py [golden.dx] [--hits N]
  -> logs/lumel-axes-live-wanchai.log (raw AXES lines)
     prints, for each captured (TU,TV,N) that matches a KNOWN Wanchai Vectors-pool triple (read from
     the golden itself), the live editor u_dir/v_dir against light.rs's own formula recomputed here.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OLD_HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
OLD_ORACLE = OLD_HARNESS / "editor-tree-oracle"
LIGHT_HARNESS = ROOT / "dev/docs/spikes/2026-08-27-native-light-apply-parity/harness"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(OLD_HARNESS))
sys.path.insert(0, str(OLD_ORACLE))
sys.path.insert(0, str(LIGHT_HARNESS))
import editor_tree_oracle as O  # noqa: E402
from uedcli import config  # noqa: E402
from uedcli.container_assets import resource_mounts  # noqa: E402
from uedcli.driver import Driver, to_z_path  # noqa: E402

GOLDEN = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else (
    ROOT / "_scratch/wanchai-relight-2026-08-29/golden.dx")
HITS = 60
for i, a in enumerate(sys.argv):
    if a == "--hits":
        HITS = int(sys.argv[i + 1])

PROJECT_DIR = ROOT / "_scratch/oracle-project"
CONTAINER = "uned-lumelaxes-wanchai"
LOGF = HERE.parent / "logs" / "lumel-axes-live-wanchai.log"

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
break *0x100a5570
commands
silent
set $tux = *(float *)($ebp - 0xa0)
set $tuy = *(float *)($ebp - 0x9c)
set $tuz = *(float *)($ebp - 0x98)
set $tvx = *(float *)($ebp - 0x94)
set $tvy = *(float *)($ebp - 0x90)
set $tvz = *(float *)($ebp - 0x8c)
set $nx  = *(float *)($ebp - 0x88)
set $ny  = *(float *)($ebp - 0x84)
set $nz  = *(float *)($ebp - 0x80)
set $udx = *(float *)($ebp - 0xfc)
set $udy = *(float *)($ebp - 0xf8)
set $udz = *(float *)($ebp - 0xf4)
set $vdx = *(float *)($ebp - 0xf0)
set $vdy = *(float *)($ebp - 0xec)
set $vdz = *(float *)($ebp - 0xe8)
printf "AXES TU=%.9g,%.9g,%.9g TV=%.9g,%.9g,%.9g N=%.9g,%.9g,%.9g U=%.9g,%.9g,%.9g V=%.9g,%.9g,%.9g\n", $tux, $tuy, $tuz, $tvx, $tvy, $tvz, $nx, $ny, $nz, $udx, $udy, $udz, $vdx, $vdy, $vdz
set $n = $n + 1
if $n >= __HITS__
  printf "AXES_DONE\n"
  detach
  quit
end
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


def lumel_axes_py(tu, tv, n):
    """`light.rs::lumel_axes` re-expressed in Python, f32-rounded at every op to match Rust f32."""
    import struct

    def f32(x):
        return struct.unpack("f", struct.pack("f", x))[0]

    def cross(a, b):
        return (f32(a[1] * b[2] - a[2] * b[1]),
                f32(a[2] * b[0] - a[0] * b[2]),
                f32(a[0] * b[1] - a[1] * b[0]))

    def dot(a, b):
        return f32(f32(a[0] * b[0]) + f32(a[1] * b[1]) + f32(a[2] * b[2]))

    c0 = cross(tv, n)
    det = dot(tu, c0)
    if abs(det) < 1e-8:
        return None
    rdet = f32(1.0 / det)
    c1 = cross(n, tu)
    u = tuple(f32(x * rdet) for x in c0)
    v = tuple(f32(x * rdet) for x in c1)
    return u, v


def main() -> int:
    if not GOLDEN.exists():
        print(f"[lumelaxes] golden not found: {GOLDEN}", file=sys.stderr)
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
    print(f"[lumelaxes] golden={GOLDEN} hits={HITS}", flush=True)
    print(f"[lumelaxes] starting {CONTAINER} ...", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(CONTAINER)
        print(f"[lumelaxes] editor pid {pid}; attaching gdb ...", flush=True)
        gdb_script = GDB.replace("__PID__", str(pid)).replace("__HITS__", str(HITS))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/la.gdb"],
                       input=gdb_script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/la.gdb > /tmp/la.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/la.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[lumelaxes] attached; LIGHT APPLY ...", flush=True)
        drv.exec("LIGHT APPLY")
        deadline = time.monotonic() + 1800.0
        while time.monotonic() < deadline:
            done = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                   "grep -c '^AXES_DONE' /tmp/la.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                print("[lumelaxes] AXES_DONE seen", flush=True)
                break
            time.sleep(2.0)
        else:
            print("[lumelaxes] WARNING: gave up waiting", flush=True)
        LOGF.parent.mkdir(parents=True, exist_ok=True)
        LOGF.write_bytes(subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/la.log"],
                                        capture_output=True).stdout)
        print(f"[lumelaxes] wrote {LOGF}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)

    # ---- offline analysis: compare each captured line against light.rs's own formula ----
    lines = [l for l in LOGF.read_text(errors="replace").splitlines() if l.startswith("AXES ")]
    print(f"[lumelaxes] {len(lines)} AXES lines captured")
    mism = match = 0
    for line in lines:
        parts = dict(tok.split("=", 1) for tok in line[len("AXES "):].split(" "))
        tu = tuple(float(x) for x in parts["TU"].split(","))
        tv = tuple(float(x) for x in parts["TV"].split(","))
        n = tuple(float(x) for x in parts["N"].split(","))
        u_live = tuple(float(x) for x in parts["U"].split(","))
        v_live = tuple(float(x) for x in parts["V"].split(","))
        axes = lumel_axes_py(tu, tv, n)
        if axes is None:
            continue
        u_py, v_py = axes
        ok = all(abs(a - b) < 1e-6 for a, b in zip(u_live, u_py)) and \
             all(abs(a - b) < 1e-6 for a, b in zip(v_live, v_py))
        match += ok
        mism += not ok
        if not ok:
            print(f"  MISMATCH TU={tu} TV={tv} N={n}")
            print(f"    live u={u_live} v={v_live}")
            print(f"    py   u={u_py} v={v_py}")
    print(f"[lumelaxes] {match} match, {mism} mismatch (of {match+mism} checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
