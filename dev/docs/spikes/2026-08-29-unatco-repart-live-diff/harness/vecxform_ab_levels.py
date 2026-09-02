"""A/B the `rotation.editor_vector_xform` fix across offline goldens: counts + node-plane content.

Run once with `AB_OLD_VECXFORM=1` (monkeypatches back the old double `(L⁻¹)ᵀ` covariant) and once
without; diff the two outputs.  Golden paths are the main checkout's `_scratch/geo-confirm-*`
fixtures (stable data, read-only).  Originally `_scratch/pass1-trace/ab_levels.py` (pass1 trace
round, 2026-09-02)."""
import os
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

CASES = [
    ("UNATCO", "/workspace/uedcli/_scratch/bsp-parity-proj", "maps/unatco",
     "/workspace/uedcli/_scratch/bsp-parity-proj/golden_unatco_control.dx"),
    ("Wanchai", "/workspace/uedcli/dev/games/trunks/tmp-wanchai-market", None,
     "/workspace/uedcli/_scratch/golden_wanchai_world.dx"),
    ("Vandenberg", "/workspace/uedcli/_scratch/geo-confirm-vandenberg-gas", None,
     "/workspace/uedcli/_scratch/geo-confirm-vandenberg-gas/golden_vandenberg-gas.dx"),
    ("NYCBar", "/workspace/uedcli/_scratch/geo-confirm-nyc-bar", None,
     "/workspace/uedcli/_scratch/geo-confirm-nyc-bar/golden_nyc-bar.dx"),
    ("FreeClinic08", "/workspace/uedcli/_scratch/geo-confirm-freeclinic08-wk", None,
     "/workspace/uedcli/_scratch/geo-confirm-freeclinic08-wk/golden_freeclinic08.dx"),
    ("NSFHQ04", "/workspace/uedcli/_scratch/geo-confirm-nsfhq04-wk", None,
     "/workspace/uedcli/_scratch/geo-confirm-nsfhq04-wk/golden_nsfhq04.dx"),
    ("DX", "/workspace/uedcli/_scratch/geo-confirm-dx", None,
     "/workspace/uedcli/_scratch/geo-confirm-dx/golden_dx.dx"),
    ("Area51", "/workspace/uedcli/_scratch/geo-confirm-area51-entrance", None,
     "/workspace/uedcli/_scratch/geo-confirm-area51-entrance/golden_area51.dx"),
    ("OceanLab", "/workspace/uedcli/_scratch/geo-confirm-oceanlab-lab", None,
     "/workspace/uedcli/_scratch/geo-confirm-oceanlab-lab/golden_oceanlab-lab.dx"),
    ("TrainingFinal", "/workspace/uedcli/_scratch/geo-confirm-training-final", None,
     "/workspace/uedcli/_scratch/geo-confirm-training-final/golden_training-final.dx"),
    ("ParisClub", "/workspace/uedcli/_scratch/geo-confirm-paris-club", None,
     "/workspace/uedcli/_scratch/geo-confirm-paris-club/golden_paris-club.dx"),
    ("ParisChateau", "/workspace/uedcli/_scratch/geo-confirm-paris-chateau", None,
     "/workspace/uedcli/_scratch/geo-confirm-paris-chateau/golden_paris-chateau.dx"),
    ("ParisUnderground", "/workspace/uedcli/_scratch/geo-confirm-paris-underground", None,
     "/workspace/uedcli/_scratch/geo-confirm-paris-underground/golden_paris-underground.dx"),
    ("NYC747", "/workspace/uedcli/_scratch/geo-confirm-nyc-747", None,
     "/workspace/uedcli/_scratch/geo-confirm-nyc-747/golden_nyc-747.dx"),
    ("Underground04", "/workspace/uedcli/_scratch/geo-confirm-nyc-underground04", None,
     "/workspace/uedcli/_scratch/geo-confirm-nyc-underground04/golden_nyc-underground04.dx"),
    ("ShipFan", "/workspace/uedcli/_scratch/geo-confirm-nyc-shipfan", None,
     "/workspace/uedcli/_scratch/geo-confirm-nyc-shipfan/golden_nyc-shipfan.dx"),
    ("Helibase", "/workspace/uedcli/_scratch/geo-confirm-hk-helibase", None,
     "/workspace/uedcli/_scratch/geo-confirm-hk-helibase/golden_hk-helibase.dx"),
    ("WanchaiGarage", "/workspace/uedcli/_scratch/geo-confirm-wanchai-garage", None,
     "/workspace/uedcli/_scratch/geo-confirm-wanchai-garage/golden_wanchai-garage.dx"),
]

OLD = os.environ.get("AB_OLD_VECXFORM") == "1"

from uedcli import trunk                           # noqa: E402
from uedcli import rotation as ROT                 # noqa: E402
from uedcli.transform import covariant_axes        # noqa: E402
from uedcli.native import brush_marshal as BM      # noqa: E402
from uedcli.native import umodel as UM             # noqa: E402
import uedcli_native                               # noqa: E402
import utexture_decode as UT                       # noqa: E402
from spike_classindex import class_index           # noqa: E402

if OLD:
    ROT.editor_vector_xform = lambda actor: covariant_axes(ROT.actor_linear(actor))
    ROT.editor_point_xform = ROT.actor_linear   # old vert map: the double compose


def parse_golden(path):
    pkg = UT.load_package(str(path))
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    return UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])


def fb(x):
    return struct.unpack("<I", struct.pack("<f", x))[0]


for name, project, subpath, golden_path in CASES:
    os.environ["UEDCLI_PROJECT"] = project
    proj = Path(project)
    if subpath:
        trunk_path = proj / subpath
    elif (proj / "actors").exists():
        trunk_path = proj
    else:
        trunk_path = next((proj / "maps").iterdir())
    level, _ = trunk.read_level(trunk_path)
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    try:
        ins = [BM._build_brush_input(n, level.actors[n]) for n in names]
        built = uedcli_native.build_geometry_bspcsg(ins)
    except Exception as e:  # noqa: BLE001
        print(f"{name}: BUILD FAILED: {e}")
        continue
    nbody = uedcli_native.serialize_model(built)
    nm_ = UM.parse_model_body(nbody, 0, len(nbody))
    gm = parse_golden(golden_path)
    deltas = {f: len(getattr(nm_, f)) - len(getattr(gm, f))
              for f in ("nodes", "surfs", "leaves", "verts", "points", "vectors")}
    plane_eq = sum(
        1 for a, b in zip(nm_.nodes, gm.nodes)
        if (fb(a.plane[0]), fb(a.plane[1]), fb(a.plane[2]), fb(a.plane[3]))
        == (fb(b.plane[0]), fb(b.plane[1]), fb(b.plane[2]), fb(b.plane[3])))
    ncmp = min(len(nm_.nodes), len(gm.nodes))
    print(f"{name}: " + " ".join(f"{k}={v:+d}" for k, v in deltas.items())
          + f"  plane-exact {plane_eq}/{ncmp}")
