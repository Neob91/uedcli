#!/usr/bin/env python3
# recipe_ini.py — apply ONLY the proven 2026-08-03 boot_game.sh patches to the default DeusEx.ini.
# Keeps the default DeusEx engine/GameInfo/player; just points LocalMap at room.dx, sets the
# UedPreview console + SoftDrv + FirstRun. Boots DIRECTLY into room via LocalMap (no menu travel).
import sys
ini, sx, sy = sys.argv[1], sys.argv[2], sys.argv[3]
fix = {
    "localmap": "LocalMap=room.dx",
    "console": "Console=UedPreview.UedPreviewConsole",
    "gamerenderdevice": "GameRenderDevice=SoftDrv.SoftwareRenderDevice",
    "renderdevice": "RenderDevice=SoftDrv.SoftwareRenderDevice",
    "windowedrenderdevice": "WindowedRenderDevice=SoftDrv.SoftwareRenderDevice",
    "windowedcolorbits": "WindowedColorBits=32",
    "startupfullscreen": "StartupFullscreen=False",
    "windowedviewportx": f"WindowedViewportX={sx}",
    "windowedviewporty": f"WindowedViewportY={sy}",
    "firstrun": "FirstRun=400",
}
raw = open(ini, "rb").read().decode("latin-1")
out, seen_paths = [], False
for l in raw.split("\r\n"):
    k = l.split("=", 1)[0].strip().lower()
    if k == "paths":
        if not seen_paths:
            out += ["Paths=../System/*.u", "Paths=../Maps/*.dx", "Paths=../Textures/*.utx",
                    "Paths=../Sounds/*.uax", "Paths=../Music/*.umx"]
            seen_paths = True
        continue
    out.append(fix.pop(k) if k in fix else l)
if fix:
    i = out.index("[Core.System]")
    out[i+1:i+1] = list(fix.values())
open(ini, "wb").write(("\r\n".join(out)).encode("latin-1"))
print("[recipe] ini patched: LocalMap=room.dx, Console=UedPreviewConsole, SoftDrv, FirstRun=400 (default engine kept)")
