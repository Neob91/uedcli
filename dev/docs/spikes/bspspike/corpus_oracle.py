"""Run the whole discriminating corpus in ONE fresh ephemeral editor and capture the BSP-build
log channels per case. Caps to a single editor (memory), polls readiness, tears down in finally.

For each case: MAP NEW -> EDIT PASTE each brush in order -> MAP REBUILD -> flush log ->
parse `bspBuild built X convex polys into Y nodes`, `Nodes: A -> B`, `Portalized: ... L leaves,
N nodes`, `bspBuildBounds: ... bounds, ... hulls`, `BspMergeCoplanars reduced X->Y`.
"""
import re, subprocess, sys, time, json

sys.path.insert(0, "/home/human/src/dx_lum/Tools/uedcli")
from uedcli.driver import Driver
from uedcli import builders, writes

import cases as casemod

CONT = "uned-bspcorpus"
VOL = "uned-wp-bspcorpus"
COMPOSE_DIR = "/home/human/src/dx_lum/Tools/uedcli/uned"

# Live builder spec per case: (cube dims, location, csg, poly_flags).
# Mirrors cases.CASES geometry. cube(width=2hx, breadth=2hy, height=2hz) centered at origin,
# then placed at `location`.
LIVE = {
    "single_box": [((256, 256, 256), (0, 0, 0), "subtract", 0)],
    "abutting_subtracts": [
        ((256, 256, 256), (-128, 0, 0), "subtract", 0),
        ((256, 256, 256), (128, 0, 0), "subtract", 0),
    ],
    "overlapping_subtracts_L": [
        ((384, 192, 192), (0, 0, 0), "subtract", 0),
        ((192, 384, 192), (0, 0, 0), "subtract", 0),
    ],
    "room_with_pillar": [
        ((512, 512, 256), (0, 0, 0), "subtract", 0),
        ((64, 64, 256), (0, 0, 0), "add", 0),
    ],
    "room_offset_pillar": [
        ((512, 512, 256), (0, 0, 0), "subtract", 0),
        ((64, 64, 256), (96, 64, 0), "add", 0),
    ],
}


def sh(*a, **k):
    return subprocess.run(a, capture_output=True, text=True, **k)


def spin():
    sh("docker", "rm", "-f", CONT); sh("docker", "volume", "rm", VOL)
    r = subprocess.run(["docker", "compose", "run", "-d", "--name", CONT,
                        "-v", f"{VOL}:/wineprefix", "uned"], cwd=COMPOSE_DIR,
                       capture_output=True, text=True)
    if r.returncode:
        print("compose run failed:", r.stderr[-400:]); return False
    for _ in range(90):
        s = sh("docker", "exec", CONT, "python3", "/opt/uned/wine_ctl.py", "status")
        if "alive=True" in s.stdout and re.search(r"window=\d+", s.stdout):
            time.sleep(3); print("editor ready:", s.stdout.strip().replace("\n", " ")); return True
        time.sleep(2)
    print("editor never came up"); return False


def teardown():
    sh("docker", "rm", "-f", CONT); sh("docker", "volume", "rm", VOL)


def run_case(d, name, t=20):
    d.map_new(); time.sleep(1.0); d.dismiss_blocking_dialog()
    off = d.log_size()
    for i, (dims, loc, csg, pf) in enumerate(LIVE[name]):
        actor = builders.make_brush_actor(f"B{i}", builders.cube(*dims), location=loc,
                                          csg=csg, poly_flags=pf)
        writes.add_actor(d, actor); time.sleep(0.6); d.dismiss_blocking_dialog()
    d.rebuild(); time.sleep(2.5); d.dismiss_blocking_dialog()
    d.exec("OBJ LIST CLASS=Class"); time.sleep(1.5)
    log = d.read_log_since(off)
    res = {"raw": None, "after_refresh": None, "leaves": None, "portal_nodes": None,
           "merge": None, "bounds": None, "hulls": None}
    if (m := re.search(r"bspBuild built (\d+) convex polys into (\d+) nodes", log)):
        res["raw"] = int(m.group(2))
    ns = re.findall(r"Nodes: \d+ -> (\d+)", log)
    if ns:
        res["after_refresh"] = int(ns[-1])
    if (m := re.search(r"Portalized:.*?(\d+) leaves, (\d+) nodes", log)):
        res["leaves"] = int(m.group(1)); res["portal_nodes"] = int(m.group(2))
    if (m := re.search(r"[Mm]erge[Cc]oplanars reduced (\d+)\s*->\s*(\d+)", log)):
        res["merge"] = (int(m.group(1)), int(m.group(2)))
    if (m := re.search(r"bspBuildBounds: Generated (\d+) bounds, (\d+) hulls", log)):
        res["bounds"] = int(m.group(1)); res["hulls"] = int(m.group(2))
    res["_logtail"] = log[-600:]
    return res


def main():
    if not spin():
        teardown(); return 2
    out = {}
    try:
        d = Driver(CONT)
        d.exec("MAP GRID X=1 Y=1 Z=1")
        for name in casemod.CASES:
            try:
                live = run_case(d, name)
            except Exception as e:
                live = {"error": repr(e)}
            off = casemod.offline_counts(name)
            out[name] = {"editor": live, "port": off}
            print(f"\n=== {name} ===")
            print(" editor:", {k: v for k, v in live.items() if k != "_logtail"})
            print(" port:  ", off)
    finally:
        teardown()
    with open("/home/human/src/dx_lum/_scratch/bspspike/corpus_result.json", "w") as f:
        json.dump(out, f, indent=2)
    print("\nwrote corpus_result.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
