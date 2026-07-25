"""Build a LIT single-subtract-box .dx via the native path (CSG + N-4 lightmap bake).

Same room as build_realcsg.py, plus a Light actor at the room centre so the LIGHT APPLY
bake produces a non-empty lightmap (the surfaces render lit in-game instead of black).
Prints lightmap stats for a quick sanity check.
"""
import sys
sys.path.insert(0, '/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl')

from decimal import Decimal as D
from spike_classindex import class_index   # the schema-aware mover gate's ClassIndex
from uedctl.builders import cube, make_brush_actor
from uedctl.model import Level, Actor
from uedctl.native.materialize import run_materialize_native
from uedctl.native.umodel import parse_model_body
from uedctl.native.pkg_write import parse_package

room = make_brush_actor("RoomA", cube(512, 512, 256), location=(D(0), D(0), D(0)),
                        csg="subtract")
ps = Actor(name="PlayerStart0", cls="Engine.PlayerStart", props=[], location=(D(0), D(0), D(-88)))
li = Actor(name="LevelInfo0", cls="Engine.LevelInfo", props=[], location=None)
# A steady light near the ceiling of the room.
light = Actor(name="Light0", cls="Engine.Light",
              props=[("LightType", "LT_Steady"), ("LightBrightness", "220"),
                     ("LightRadius", "48")],
              location=(D(0), D(0), D(96)))

lvl = Level()
for a in (li, room, ps, light):
    lvl.actors[a.name] = a
lvl.order = ["LevelInfo0", "RoomA", "PlayerStart0", "Light0"]

out = sys.argv[1] if len(sys.argv) > 1 else "_scratch/litcsg.dx"
warnings = run_materialize_native(level=lvl, out_path=out, class_index=class_index(),
                                  overwrite=True, version=68)
print("WROTE", out, "warnings:", warnings)

# Decode the written package and report lightmap stats.
pkg = parse_package(open(out, "rb").read())
mi = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
         key=lambda i: pkg.exports[i]["ssize"])
e = pkg.exports[mi]
m = parse_model_body(pkg.buf, e["soff"], e["ssize"])
lit_surfs = sum(1 for s in m.surfs if s.i_light_map != -1)
set_bits = sum(bin(b).count("1") for b in m.light_bits)
print(f"surfs={len(m.surfs)} lightmapped={lit_surfs} "
      f"light_map_records={len(m.light_map)} light_bits={len(m.light_bits)}B "
      f"set_bits={set_bits} lights_array={m.lights}")
for ri, rec in enumerate(m.light_map):
    print(f"  rec[{ri}] off={rec.data_offset} run={rec.i_light_actors} "
          f"U={rec.u_size} V={rec.v_size} scale=({rec.u_scale:.2f},{rec.v_scale:.2f})")
