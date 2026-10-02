"""D0 live validation: prove capture_build_log catches a real hole on a live build.
Clean box -> no holes; open box (one face removed) -> not-watertight leak."""
import subprocess, sys, time, re

sys.path.insert(0, "/home/human/src/dx_lum/Tools/uedcli")
from uedcli.driver import Driver
from uedcli import builders, writes
from bsp_editorlog import capture_build_log

CONT, VOL = "uned-d0", "uned-wp-d0"
CD = "/home/human/src/dx_lum/Tools/uedcli/uned"


def sh(*a): return subprocess.run(a, capture_output=True, text=True)


def spin():
    sh("docker", "rm", "-f", CONT); sh("docker", "volume", "rm", VOL)
    subprocess.run(["docker", "compose", "run", "-d", "--name", CONT, "-v", f"{VOL}:/wineprefix", "uned"],
                   cwd=CD, capture_output=True, text=True)
    for _ in range(90):
        s = sh("docker", "exec", CONT, "python3", "/opt/uned/wine_ctl.py", "status")
        if "alive=True" in s.stdout and re.search(r"window=\d+", s.stdout):
            time.sleep(3); return True
        time.sleep(2)
    return False


def teardown(): sh("docker", "rm", "-f", CONT); sh("docker", "volume", "rm", VOL)


def build_and_capture(d, actor, label):
    d.exec("MAP GRID X=1 Y=1 Z=1")
    d.map_new(); time.sleep(1.0); d.dismiss_blocking_dialog()
    writes.add_actor(d, actor); time.sleep(1.0); d.dismiss_blocking_dialog()
    bl = capture_build_log(d)
    print(f"\n=== {label} ===")
    print(f"  nodes={bl.final_nodes} leaves={bl.leaves} has_holes_or_hom={bl.has_holes_or_hom}")
    for f in bl.findings(): print("   -", f)
    if not bl.findings(): print("   (no holes/HoM reported)")
    return bl


def main():
    if not spin():
        print("editor did not start"); teardown(); return 2
    try:
        d = Driver(CONT)
        clean = builders.make_brush_actor("CleanBox", builders.cube(256, 256, 256), csg="subtract")
        ok = build_and_capture(d, clean, "CLEAN BOX (expect: no holes)")
        openb = builders.make_brush_actor("OpenBox", builders.cube(256, 256, 256), csg="subtract")
        openb.brush.polys.pop()                     # remove one face -> not watertight
        leak = build_and_capture(d, openb, "OPEN BOX (expect: not-watertight leak)")
        print("\n=== D0 VERDICT ===")
        print("clean box clean:", not ok.has_holes_or_hom)
        print("open box flagged:", leak.has_holes_or_hom, "->", leak.findings())
    finally:
        teardown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
