import sys
from pathlib import Path
ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedctl/harness"))
from uedctl import trunk
from uedctl.native import materialize as M, umodel as UM
import uedctl_native
import utexture_decode as UT

TRUNK = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/castle/uedctl/maps/foobar"
EDITOR = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx"

def load(path):
    pkg = UT.load_package(path)
    mi = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
             key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    return UM.parse_model_body(pkg.buf, e["soff"], e["ssize"]), e["ssize"]

lvl, _ = trunk.read_level(Path(TRUNK))
brush_order = [n for n in lvl.order if lvl.actors[n].brush is not None]
bs = [M._build_brush_input(n, lvl.actors[n]) for n in brush_order]
nat_body = uedctl_native.serialize_model(uedctl_native.build_geometry(bs))
nat = UM.parse_model_body(nat_body, 0, len(nat_body))
ed, ed_size = load(EDITOR)

def cnt(m, a):
    v = getattr(m, a, None)
    return len(v) if v is not None else "-"

print(f"{'section':<14}{'native':>10}{'editor':>10}")
for a in ["vectors","points","nodes","surfs","verts","bounds","leaf_hulls"]:
    print(f"{a:<14}{str(cnt(nat,a)):>10}{str(cnt(ed,a)):>10}")
print(f"{'body bytes':<14}{len(nat_body):>10}{ed_size:>10}")
print(f"num brushes materialized: {len(brush_order)}")
