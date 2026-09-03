#!/usr/bin/env python3
"""Live oracle for MAP SAVE name/import table ORDER (UED22 core.dll SavePackage).

Drives one dbg editor through the toysmall MAP IMPORT + MAP SAVE, with gdb stopped at
the two `appQsort` calls in `UObject::SavePackage` (core.dll RVA 0x27fb0 names /
0x280d5 imports) and just after each. Dumps, to /tmp/saveorder_dump.txt in the
container (copied out next to --out):

  NAME <i> <flags> <text>      the FULL FName::Names table (global index order)
  OBJ <i> <flags> <name> <class> <outer>   the FULL GObjObjects table
  NMAP_PRE/POST <pos> <global-name-idx> [count]   the linker NameMap before/after qsort
  IMAP_PRE/POST <pos> <xobj> <internal> <nameidx> <count> <class> <outer>

Validates offline (validate_saveorder.py): counts == count_refs.py's, post == golden,
qsort port maps pre -> post.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
H0715 = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(H0715))
sys.path.insert(0, str(H0715 / "editor-tree-oracle"))

from uedcli import config, trunk, xfer                              # noqa: E402
from uedcli.apply import _level_referenced_packages                 # noqa: E402
from uedcli.driver import Driver, to_z_path                         # noqa: E402
from uedcli.emit import emit_map                                    # noqa: E402
from uedcli.materialize import levelinfo_first_order, _short_class  # noqa: E402
from uedcli.packages import editor_search_dirs, ensure_load         # noqa: E402

import editor_tree_oracle as O                                      # noqa: E402
from build_ued_golden import _scratch_project, _wait_idle           # noqa: E402

CONTAINER = "uned-saveorder"

GDB_PY = r"""
import struct
import gdb

OUT = open("/tmp/saveorder_dump.txt", "w")
PID = gdb.selected_inferior().pid
base = None
for line in open(f"/proc/{PID}/maps"):
    if line.rstrip().lower().endswith("core.dll"):
        base = int(line.split("-")[0], 16)
        break
assert base is not None, "core.dll not mapped"
OUT.write(f"BASE {base:#x}\n")

INF = gdb.selected_inferior()

def rd(addr, n):
    return bytes(INF.read_memory(addr, n))

def u32(addr):
    return struct.unpack("<I", rd(addr, 4))[0]

def i32(addr):
    return struct.unpack("<i", rd(addr, 4))[0]

def wstr(addr, maxlen=64):
    try:
        data = rd(addr, 2 * maxlen)          # one bulk read (fast at 40k-name scale)
    except gdb.MemoryError:
        data = b""
        for i in range(maxlen):              # fallback near unmapped page ends
            try:
                data += rd(addr + 2 * i, 2)
            except gdb.MemoryError:
                break
    out = []
    for i in range(0, len(data) - 1, 2):
        c = data[i] | (data[i + 1] << 8)
        if c == 0:
            break
        out.append(chr(c) if 32 <= c < 127 else "?")
    return "".join(out)

NAMES_DATA = base + 0x139D50
NAMES_NUM = base + 0x139D54
OBJS_DATA = base + 0x13A260
OBJS_NUM = base + 0x13A264
LINKER = base + 0x13C594

_NCACHE = {}

def name_text(idx):
    if idx < 0:
        return "-"
    if idx not in _NCACHE:
        e = u32(u32(NAMES_DATA) + 4 * idx)
        _NCACHE[idx] = wstr(e + 0xC) if e else "-"
    return _NCACHE[idx]

def obj_nameidx(objp):
    return u32(objp + 0x20)

def dump_names_and_objects():
    data, num = u32(NAMES_DATA), i32(NAMES_NUM)
    for i in range(num):
        e = u32(data + 4 * i)
        if e:
            OUT.write(f"NAME {i} {u32(e + 4):#x} {wstr(e + 0xC)}\n")
        else:
            OUT.write(f"NAME {i} - -\n")
    data, num = u32(OBJS_DATA), i32(OBJS_NUM)
    for i in range(num):
        p = u32(data + 4 * i)
        if not p:
            OUT.write(f"OBJ {i} - - - -\n")
            continue
        flags = u32(p + 0x1C)
        nm = name_text(obj_nameidx(p))
        cl = u32(p + 0x24)
        cln = name_text(obj_nameidx(cl)) if cl else "-"
        ou = u32(p + 0x18)
        oun = name_text(obj_nameidx(ou)) if ou else "-"
        OUT.write(f"OBJ {i} {flags:#x} {nm} {cln} {oun}\n")

def dump_nmap(tag):
    lk = u32(LINKER)
    data, num = u32(lk + 0x6C), i32(lk + 0x70)
    counts = u32(lk + 0xEC)
    for pos in range(num):
        gi = u32(data + 4 * pos)
        OUT.write(f"{tag} {pos} {gi} {i32(counts + 4 * gi)} {name_text(gi)}\n")

def dump_imap(tag):
    lk = u32(LINKER)
    data, num = u32(lk + 0x78), i32(lk + 0x7C)
    ocounts = u32(lk + 0xE0)
    for pos in range(num):
        e = data + 0x1C * pos
        xo = u32(e + 0x10)
        internal = u32(xo + 4)
        nmi = obj_nameidx(xo)
        cnt = i32(ocounts + 4 * internal)
        cl = u32(xo + 0x24)
        cln = name_text(obj_nameidx(cl)) if cl else "-"
        ou = u32(xo + 0x18)
        oun = name_text(obj_nameidx(ou)) if ou else "-"
        OUT.write(f"{tag} {pos} {xo:#x} {internal} {nmi} {cnt} {name_text(nmi)} {cln} {oun}\n")

for rva in (0x27FB0, 0x27FB5, 0x280D5, 0x280DA):
    gdb.Breakpoint(f"*{base + rva:#x}")

gdb.execute("continue")                 # -> pre name qsort
dump_names_and_objects()
dump_nmap("NMAP_PRE")
OUT.flush()
gdb.execute("continue")                 # -> post name qsort
dump_nmap("NMAP_POST")
OUT.flush()
gdb.execute("continue")                 # -> pre import qsort
dump_imap("IMAP_PRE")
OUT.flush()
gdb.execute("continue")                 # -> post import qsort
dump_imap("IMAP_POST")
OUT.write("DUMP_DONE\n")
OUT.close()
gdb.execute("detach")
gdb.execute("quit")
"""

GDB_MAIN = """
set pagination off
set confirm off
set height 0
set width 0
attach {pid}
handle SIGSEGV nostop noprint pass
handle SIGUSR1 nostop noprint pass
handle SIGUSR2 nostop noprint pass
handle SIGPIPE nostop noprint pass
echo ORACLE_ATTACHED\\n
source /tmp/saveorder_gdb.py
"""


def _dexec(args, **kw):
    return subprocess.run(["docker", "exec", *args], **kw)


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--trunk",
                    default=str(ROOT / "_scratch/unbuilt-parity/toys/toysmall/maps/toysmall"))
    ap.add_argument("--out", default=str(ROOT / "_scratch/unbuilt-parity/toys/toysmall_traced.dx"))
    args = ap.parse_args()

    trunk_dir = Path(args.trunk).resolve()
    host_out = Path(args.out).resolve()
    dump_out = host_out.with_suffix(".dump.txt")

    user_config = config.load_user_config()
    project = _scratch_project(trunk_dir, "deusex")
    search_dirs = config.composed_search_dirs(project, user_config)
    mounts = O._composed_mounts(project.root)
    host_search_dirs = editor_search_dirs(search_dirs)
    state_dir = config.state_dir(project.root, create=True)

    lvl, _ranks = trunk.read_level(trunk_dir)
    classes = {n: lvl.actors[n].cls for n in lvl.order}
    has_brush = {n: lvl.actors[n].brush is not None for n in lvl.order}
    imp_order = levelinfo_first_order(lvl.order, classes, has_brush)
    actors = [lvl.actors[n] for n in imp_order]
    ref_pkgs = _level_referenced_packages(
        type("L", (), {"actors": {n: lvl.actors[n] for n in imp_order}})())
    print(f"importing {len(actors)} actors; ref pkgs {ref_pkgs}", flush=True)

    others = [n for n in subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                                        capture_output=True, text=True).stdout.split()
              if n.startswith("uned-") and n != CONTAINER]
    if others:
        print(f"refusing to start: other uned containers running: {others}", file=sys.stderr)
        return 2

    O._ensure_dbg_image()
    O.stop_dbg_editor(CONTAINER, state_dir)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        ed = Driver(container=CONTAINER)
        print("editor up", flush=True)
        if ref_pkgs:
            ensure_load(ed, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
            _wait_idle(ed, label="obj-load")
        t3d_path = ed.write_work_file(emit_map(actors), ext="t3d")
        ed.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
        _wait_idle(ed, label="map-import", timeout=3600.0, quiet_reads=30)

        pid = O._editor_pid(CONTAINER)
        _dexec(["-i", CONTAINER, "bash", "-c", "cat > /tmp/saveorder_gdb.py"],
               input=GDB_PY, text=True, check=True)
        _dexec(["-i", CONTAINER, "bash", "-c", "cat > /tmp/so.gdb"],
               input=GDB_MAIN.format(pid=pid), text=True, check=True)
        _dexec(["-d", CONTAINER, "bash", "-c",
                "exec gdb -batch -x /tmp/so.gdb > /tmp/so.log 2>&1"], check=True)
        for _ in range(240):
            r = _dexec([CONTAINER, "bash", "-c",
                        "grep -c ORACLE_ATTACHED /tmp/so.log 2>/dev/null || true"],
                       capture_output=True, text=True).stdout.strip()
            if r and r != "0":
                break
            time.sleep(0.5)
        else:
            raise TimeoutError("gdb never attached; see /tmp/so.log")
        print("gdb attached; MAP SAVE ...", flush=True)

        work_out = xfer.work_path("dx")
        ed.exec(f"MAP SAVE FILE={to_z_path(work_out)}")
        deadline = time.time() + 1800
        while time.time() < deadline:
            r = _dexec([CONTAINER, "bash", "-c",
                        "grep -c DUMP_DONE /tmp/saveorder_dump.txt 2>/dev/null || true"],
                       capture_output=True, text=True).stdout.strip()
            if r and r != "0":
                break
            time.sleep(2.0)
        else:
            log = _dexec([CONTAINER, "cat", "/tmp/so.log"],
                         capture_output=True, text=True).stdout
            raise TimeoutError(f"dump never completed; gdb log:\n{log[-4000:]}")
        _wait_idle(ed, label="map-save", timeout=600.0)
        # docker cp fails on this rootless daemon (remount-ro); stream via exec instead
        dump_out.write_bytes(_dexec([CONTAINER, "cat", "/tmp/saveorder_dump.txt"],
                                    capture_output=True, check=True).stdout)
        host_out.write_bytes(_dexec([CONTAINER, "cat", work_out],
                                    capture_output=True, check=True).stdout)
        print(f"WROTE {host_out} and {dump_out}", flush=True)
    finally:
        log = _dexec([CONTAINER, "cat", "/tmp/so.log"], capture_output=True)
        host_out.with_suffix(".gdb.log").write_bytes(log.stdout or b"")
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
