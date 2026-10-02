"""Compare two subtraction methods, exporting the full level after each.

A) uedcli method  : make_brush_actor(csg="subtract") -> EDIT PASTE -> MAP REBUILD
B) canonical UED  : BRUSH IMPORT cube polylist -> BRUSH MOVETO -> BRUSH SUBTRACT -> REBUILD
"""
import sys
sys.path.insert(0, "/home/human/src/dx_lum/Extra/AI")
from uedcli import builders, emit, writes
from uedcli import driver as drv

TEX = "Engine.DefaultTexture"
d = drv.Driver()


def clear():
    d.exec("ACTOR SELECT ALL")
    d.actor_delete()
    d.select_none()
    d.rebuild()


def grid1():
    d.set_grid(1, 1, 1)


# ---------- Trial A: uedcli paste method ----------
clear()
grid1()
cube = builders.cube(256, 256, 256, texture=TEX)
actor = builders.make_brush_actor("SubMine", cube, location=(0, 0, 0), csg="subtract")
writes.add_actor(d, actor)
d.rebuild()
d.map_export("/repo/Temp/sub_mine.t3d")
print("A done: uedcli paste method")

# ---------- Trial B: canonical BRUSH SUBTRACT ----------
clear()
grid1()
cube2 = builders.cube(256, 256, 256, texture=TEX)
polylist = ("Begin PolyList\n"
            + "\n".join(emit.emit_polygon(p) for p in cube2.polys)
            + "\nEnd PolyList\n")
with open("/home/human/src/dx_lum/Temp/builder_cube.t3d", "w") as f:
    f.write(polylist)
d.brush_import("/repo/Temp/builder_cube.t3d")
d.brush_moveto(0, 0, 0)
d.exec("BRUSH SUBTRACT")
d.rebuild()
d.map_export("/repo/Temp/sub_canon.t3d")
print("B done: canonical BRUSH SUBTRACT")
