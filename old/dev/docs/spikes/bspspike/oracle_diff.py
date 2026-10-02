"""Slice-1 differential oracle: build the same box in a REAL editor, read the node count from
the log, diff against the Python port. Spins a fresh isolated ephemeral editor and tears it down.
"""
import re, subprocess, sys, time, os

sys.path.insert(0, "/home/human/src/dx_lum/Tools/uedcli")
from uedcli.driver import Driver
from uedcli import builders, writes
import bsp_port

CONT = "uned-slice1"
VOL = "uned-wp-slice1"
COMPOSE_DIR = "/home/human/src/dx_lum/Tools/uedcli/uned"
T3D = "/home/human/src/dx_lum/_scratch/bspspike/diffbox.t3d"


def sh(*a, **k):
    return subprocess.run(a, capture_output=True, text=True, **k)


def spin():
    sh("docker", "rm", "-f", CONT)
    sh("docker", "volume", "rm", VOL)
    r = subprocess.run(["docker", "compose", "run", "-d", "--name", CONT,
                        "-v", f"{VOL}:/wineprefix", "uned"], cwd=COMPOSE_DIR,
                       capture_output=True, text=True)
    print("compose run rc", r.returncode, r.stderr[-300:] if r.returncode else "")
    for _ in range(90):
        s = sh("docker", "exec", CONT, "python3", "/opt/uned/wine_ctl.py", "status")
        if "alive=True" in s.stdout and re.search(r"window=\d+", s.stdout):
            time.sleep(3)                      # settle: let the window finish mapping
            print("editor ready:", s.stdout.strip().replace("\n", " "))
            return True
        time.sleep(2)
    print("editor never came up:", s.stdout, s.stderr)
    return False


def teardown():
    sh("docker", "rm", "-f", CONT)
    sh("docker", "volume", "rm", VOL)


def main():
    if not spin():
        teardown(); return 2
    try:
        d = Driver(CONT)
        d.exec("MAP GRID X=1 Y=1 Z=1")
        d.map_new(); time.sleep(1.0); d.dismiss_blocking_dialog()
        off = d.log_size()
        # brushes must enter via EDIT PASTE (not IMPORTADD) to participate in CSG
        actor = builders.make_brush_actor("DiffBox", builders.cube(256, 256, 256), csg="subtract")
        writes.add_actor(d, actor); time.sleep(1.0); d.dismiss_blocking_dialog()
        d.rebuild(); time.sleep(2.0); d.dismiss_blocking_dialog()
        # force a flush with guaranteed-large output, then read forward from `off`
        d.exec("OBJ LIST CLASS=Class"); time.sleep(1.5)
        log = d.read_log_since(off)
        for pat in (r"bspBuild built (\d+) convex polys into (\d+) nodes",
                    r"Portalized:.*?(\d+) leaves, (\d+) nodes",
                    r"Nodes: (\d+) -> (\d+)"):
            for m in re.finditer(pat, log):
                print("EDITOR LOG:", m.group(0))
        m = re.search(r"bspBuild built (\d+) convex polys into (\d+) nodes", log)
        if m:
            editor_nodes = int(m.group(2))
        else:   # fall back to the final "Nodes: X -> Y" (bspRefresh/optgeom) value
            ns = re.findall(r"Nodes: \d+ -> (\d+)", log)
            editor_nodes = int(ns[-1]) if ns else None
        port_nodes = bsp_port.count_nodes(bsp_port.split_poly_list(
            bsp_port.box(0, 0, 0, 128, 128, 128)))
        print(f"\n=== PARITY ===\nPython port nodes: {port_nodes}\nEditor nodes:      {editor_nodes}")
        print("MATCH" if editor_nodes == port_nodes else "DIFF (investigate)")
        if editor_nodes is None:
            print("\n[log tail for diagnosis]\n", log[-1500:])
    finally:
        teardown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
