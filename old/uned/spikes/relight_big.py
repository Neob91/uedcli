"""Big room so the default load-camera is inside it -> MAP LOAD renders lit, no mouse."""
import sys
sys.path.insert(0, "/home/human/src/dx_lum/Extra/AI")
from uedcli import builders, writes
from uedcli import driver as drv

TEX = "Engine.DefaultTexture"
d = drv.Driver()

d.exec("ACTOR SELECT ALL"); d.actor_delete(); d.select_none(); d.rebuild()
d.set_grid(1, 1, 1)

# large carved room (+/-512) -> default camera lands inside
cube = builders.cube(1024, 1024, 1024, texture=TEX)
room = builders.make_brush_actor("Room", cube, location=(0, 0, 0), csg="subtract")
writes.add_actor(d, room)
d.rebuild()

# dim + saturated colored light at the origin (where the camera lands)
light = (
    "Begin Map\n"
    "Begin Actor Class=Light Name=Light0\n"
    "    LightBrightness=80\n"
    "    LightRadius=48\n"
    "    LightHue=40\n"
    "    LightSaturation=24\n"
    "    Location=(X=0.000000,Y=0.000000,Z=0.000000)\n"
    '    Name="Light0"\n'
    "End Actor\n"
    "End Map\n"
)
with open("/home/human/src/dx_lum/Temp/light_big.t3d", "w") as f:
    f.write(light)
d.map_importadd("/repo/Temp/light_big.t3d")
d.exec("LIGHT APPLY")
d.map_save("/repo/Temp/big.dx")
print("saved big.dx (1024 room + dim colored light at origin)")
