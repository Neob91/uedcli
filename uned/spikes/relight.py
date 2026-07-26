"""Rebuild the carved room and add a DIMMER, more-saturated colored light."""
import sys
sys.path.insert(0, "/home/human/src/dx_lum/Extra/AI")
from uedcli import builders, writes
from uedcli import driver as drv

TEX = "Engine.DefaultTexture"
d = drv.Driver()

# clean slate
d.exec("ACTOR SELECT ALL"); d.actor_delete(); d.select_none(); d.rebuild()
d.set_grid(1, 1, 1)

# carve the 256^3 room (textured)
cube = builders.cube(256, 256, 256, texture=TEX)
room = builders.make_brush_actor("Room", cube, location=(0, 0, 0), csg="subtract")
writes.add_actor(d, room)
d.rebuild()

# dimmer + more-colored light: brightness 96 (was 255), LightSaturation 24 (was 120 -> more vivid)
light = (
    "Begin Map\n"
    "Begin Actor Class=Light Name=Light0\n"
    "    LightBrightness=96\n"
    "    LightRadius=64\n"
    "    LightHue=40\n"
    "    LightSaturation=24\n"
    "    Location=(X=0.000000,Y=0.000000,Z=96.000000)\n"
    '    Name="Light0"\n'
    "End Actor\n"
    "End Map\n"
)
with open("/home/human/src/dx_lum/Temp/light_dim.t3d", "w") as f:
    f.write(light)
d.map_importadd("/repo/Temp/light_dim.t3d")
d.exec("LIGHT APPLY")
d.exec("JUMPTO 0,0,0")
print("rebuilt room + dimmer colored light")
