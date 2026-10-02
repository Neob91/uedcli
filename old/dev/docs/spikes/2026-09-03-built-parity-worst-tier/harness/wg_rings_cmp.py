"""Compare editor vs native pre-merge ilink-240 rings (Garage n=40), then run the as-ported
merge emulation on the EDITOR rings."""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = HERE.parent / "logs/fpolys-stage-order-wg-n40-verts.log"
sys.path.insert(0, str(HERE))
import wg_merge_emul as E  # noqa: E402 (loads native premerge itself; we reuse its merge funcs)


def load_editor():
    polys = []
    cur = None
    for line in LOG.read_text(errors="replace").splitlines():
        if line.startswith("PREMERGE"):
            m = re.search(r"nv=(\d+) normal=([^ ]+)", line)
            cur = {"N": tuple(float(x) for x in m.group(2).split(",")), "v": []}
            polys.append(cur)
        elif line.startswith("V ") and cur is not None:
            cur["v"].append(tuple(float(x) for x in line.split()[1].split(",")))
        elif not line.startswith("V "):
            cur = None  # any other line (POSTMERGE/HEADER/...) ends the current ring
    return polys


ed = load_editor()
nat = E.load(240)
print(f"editor {len(ed)} native {len(nat)}")
ndiff = 0
for k, (a, b) in enumerate(zip(ed, nat)):
    if len(a["v"]) != len(b["v"]):
        print(f"k#{k}: nv {len(a['v'])} vs {len(b['v'])}")
        ndiff += 1
        continue
    for va, vb in zip(a["v"], b["v"]):
        if any(abs(va[i] - vb[i]) > 1e-4 for i in range(3)):
            print(f"k#{k}: vert {va} vs {vb}")
            ndiff += 1
print(f"{ndiff} ring differences > 1e-4")

alive, fails = E.merge_group([dict(p) for p in ed], gate="pre", neigh_tol=E.NEAR)
print(f"as-ported merge on EDITOR rings: -> {len(alive)} polys, "
      f"nv={[len(p['v']) for p in alive]}, fails={fails}")
