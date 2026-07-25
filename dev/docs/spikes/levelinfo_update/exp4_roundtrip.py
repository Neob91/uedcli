#!/usr/bin/env python3
"""EXP4: full materialize round-trip for an updated LevelInfo.

  1. MAP NEW
  2. MAP IMPORT a merged level T3D whose actor 0 is an authored LevelInfo
     (Title/Author/Ambient/Fog/Gravity/bLonePlayer/IdealPlayerCount), plus a real
     CSG_Subtract room brush so the level is non-trivial and REBUILD does work.
  3. MAP REBUILD
  4. MAP SAVE FILE=Z:\repo\...\li_roundtrip.dx
  5. UCC batchexport that .dx offline -> read the LevelInfo block back.
Confirms the authored fields persist through the save + an INDEPENDENT offline reader.
"""
import re
import subprocess
import sys
import lidrv as L

CONT = L.CONT

# A merged level: authored LevelInfo (actor 0) + a subtract room brush.
LEVEL = r"""Begin Map
Begin Actor Class=LevelInfo Name=LevelInfo0
     Title="SpikeTest"
     Author="uedctl"
     IdealPlayerCount="3-4"
     bLonePlayer=True
     AmbientBrightness=42
     FogDistance=1337.000000
     ZoneGravity=(X=0.000000,Y=0.000000,Z=-666.000000)
     Name="LevelInfo0"
End Actor
Begin Actor Class=Brush Name=RoomBrush
     CsgOper=CSG_Subtract
     Location=(X=0.000000,Y=0.000000,Z=0.000000)
     Begin Brush Name=Model
        Begin PolyList
           Begin Polygon
              Origin   -256.000000,-256.000000,-256.000000
              Normal   1.000000,0.000000,0.000000
              TextureU 0.000000,1.000000,0.000000
              TextureV 0.000000,0.000000,-1.000000
              Vertex   256.000000,-256.000000,-256.000000
              Vertex   256.000000,256.000000,-256.000000
              Vertex   256.000000,256.000000,256.000000
              Vertex   256.000000,-256.000000,256.000000
           End Polygon
        End PolyList
     End Brush
     Brush=Model'MyLevel.Model'
     Name="RoomBrush"
End Actor
End Map
"""

try:
    p = L.put(LEVEL, "rt_level")
    L.ex("MAP NEW")
    L.ex("MAP GRID X=1 Y=1 Z=1")
    L.ex(f"MAP IMPORT FILE={p}")
    pre = L.export("rt_presave")
    print("=== after IMPORT, before save ===", flush=True)
    print(L.levelinfo_block(pre), flush=True)

    L.ex("MAP REBUILD")
    dxz = r"Z:\repo\Tools\uedctl\_scratch\liupdate\li_roundtrip.dx"
    L.ex(f"MAP SAVE FILE={dxz}")
    # confirm the file exists in the container
    r = subprocess.run(["docker", "exec", CONT, "ls", "-la",
                        "/repo/Tools/uedctl/_scratch/liupdate/li_roundtrip.dx"],
                       capture_output=True, text=True)
    print(f"\n=== saved .dx: {r.stdout.strip()}{r.stderr.strip()} ===", flush=True)

    # --- INDEPENDENT offline reader: UCC batchexport the saved .dx ---
    outdir = r"Z:\repo\Tools\uedctl\_scratch\liupdate\ucc_out"
    subprocess.run(["docker", "exec", CONT, "mkdir", "-p",
                    "/repo/Tools/uedctl/_scratch/liupdate/ucc_out"],
                   capture_output=True, text=True)
    ucc = subprocess.run(
        ["docker", "exec", CONT, "sh", "-c",
         "cd /opt/UED22 && wine UCC.exe batchexport "
         "Z:\\repo\\Tools\\uedctl\\_scratch\\liupdate\\li_roundtrip.dx "
         "Level T3D " + outdir + " 2>&1"],
        capture_output=True, text=True)
    print("\n=== UCC batchexport output (tail) ===", flush=True)
    print("\n".join(ucc.stdout.splitlines()[-15:]), flush=True)

    # read the exported T3D
    rd = subprocess.run(["docker", "exec", CONT, "sh", "-c",
                         "cat /repo/Tools/uedctl/_scratch/liupdate/ucc_out/*.t3d 2>/dev/null"],
                        capture_output=True, text=True)
    print("\n=== UCC-exported LevelInfo block (offline reader, post-save) ===", flush=True)
    print(L.levelinfo_block(rd.stdout) if rd.stdout.strip() else "<empty / not exported>", flush=True)
    print(f"\n=== exported headers: {L.all_actor_headers(rd.stdout)} ===", flush=True)

    print("\nDONE exp4", flush=True)
except L.EditorDead as e:
    print(f"*** EDITOR DIED: {e}", flush=True)
    sys.exit(1)
