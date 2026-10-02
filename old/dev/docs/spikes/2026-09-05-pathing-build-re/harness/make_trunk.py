#!/usr/bin/env python3
"""Synthesize a uedcli trunk (`actors/<Name>/actor.t3d` + `order_value`) for path-build probes.

Level "pathlab":
  room A  — 8192×512×512 corridor; PathNodes along X with growing gaps (100..1200) → the
            candidate-pair distance cutoff and how Distance is stored.
  room B  — 2048×768×1024 hall with step platforms of rising heights (16..160) → the
            step-up / jump / fall thresholds and their asymmetry (R_WALK vs R_JUMP vs none).
  room C  — 1024×512×512 box with a WaterZone → R_SWIM.
  room D  — 1536×512×512 box with a PlayerStart + PathNodes → non-PathNode nav classes.

Usage: make_trunk.py <trunk-dir> [--level pathlab]
"""
from __future__ import annotations

import sys
from pathlib import Path


def box_polys(cx: float, cy: float, cz: float, hx: float, hy: float, hz: float, item: str = "OUTSIDE") -> str:
    x0, x1, y0, y1, z0, z1 = cx - hx, cx + hx, cy - hy, cy + hy, cz - hz, cz + hz
    faces = [
        ((x1, cy, cz), (1, 0, 0), (0, 1, 0), (0, 0, 1), [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)]),
        ((x0, cy, cz), (-1, 0, 0), (0, 1, 0), (0, 0, -1), [(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)]),
        ((cx, y1, cz), (0, 1, 0), (1, 0, 0), (0, 0, -1), [(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)]),
        ((cx, y0, cz), (0, -1, 0), (1, 0, 0), (0, 0, 1), [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)]),
        ((cx, cy, z1), (0, 0, 1), (1, 0, 0), (0, 1, 0), [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]),
        ((cx, cy, z0), (0, 0, -1), (1, 0, 0), (0, -1, 0), [(x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0)]),
    ]

    def v3(v):
        return ",".join(f"{c:+013.6f}" for c in v)

    out = []
    for origin, normal, tu, tv, verts in faces:
        out.append(f"         Begin Polygon Item={item}")
        out.append(f"         Origin   {v3(origin)}")
        out.append(f"         Normal   {v3(normal)}")
        out.append(f"         TextureU {v3(tu)}")
        out.append(f"         TextureV {v3(tv)}")
        for v in verts:
            out.append(f"         Vertex   {v3(v)}")
        out.append("         End Polygon")
    return "\n".join(out)


def brush_actor(csg: str, cx, cy, cz, hx, hy, hz) -> str:
    # Polys are authored in WORLD space around the brush origin; Location stays 0 so the CSG
    # sees them where written (the trunk's own cube/corridor brushes do the same).
    return (f"Begin Actor Class=Engine.Brush\n    CsgOper={csg}\n"
            f"    Location=(X=0.000000,Y=0.000000,Z=0.000000)\n"
            f"    MainScale=(SheerAxis=SHEER_ZX)\n    PostScale=(SheerAxis=SHEER_ZX)\n"
            f"    Begin Brush Name=Model\n       Begin PolyList\n{box_polys(cx, cy, cz, hx, hy, hz)}\n"
            f"       End PolyList\n    End Brush\n    Brush=Model'MyLevel.Model'\nEnd Actor\n")


def point_actor(cls: str, x, y, z, extra: str = "") -> str:
    return (f"Begin Actor Class={cls}\n    Location=(X={x:.6f},Y={y:.6f},Z={z:.6f})\n{extra}End Actor\n")


def pathlab() -> list[tuple[str, str]]:
    acts: list[tuple[str, str]] = [("LevelInfo", "Begin Actor Class=Engine.LevelInfo\nEnd Actor\n")]
    # room A: corridor along X, centred (0, 0, 0), floor at z=-256
    acts.append(("RoomA", brush_actor("CSG_Subtract", 0, 0, 0, 4096, 256, 256)))
    x = -3900.0
    acts.append(("A_N00", point_actor("Engine.PathNode", x, 0, -216)))
    for i, gap in enumerate([100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 1100, 1200], 1):
        x += gap
        acts.append((f"A_N{i:02d}", point_actor("Engine.PathNode", x, 0, -216)))
    # room B: hall at y=+2048, floor z=-256; platforms of rising height, nodes on top
    acts.append(("RoomB", brush_actor("CSG_Subtract", 0, 2048, 256, 1024, 384, 512)))
    acts.append(("B_Floor0", point_actor("Engine.PathNode", -900, 2048, -216)))
    px = -700.0
    for i, h in enumerate([16, 32, 40, 48, 56, 64, 80, 96, 128, 160], 1):
        acts.append((f"B_Step{i:02d}", brush_actor("CSG_Add", px, 2048, -256 + h / 2, 64, 96, h / 2)))
        acts.append((f"B_N{i:02d}", point_actor("Engine.PathNode", px, 2048, -256 + h + 40)))
        acts.append((f"B_F{i:02d}", point_actor("Engine.PathNode", px, 2048 + 240, -216)))
        px += 180
    # room C: water box at y=-2048
    acts.append(("RoomC", brush_actor("CSG_Subtract", 0, -2048, 0, 512, 256, 256)))
    acts.append(("C_Water", point_actor("Engine.WaterZone", 0, -2048, 0)))
    acts.append(("C_N00", point_actor("Engine.PathNode", -300, -2048, -100)))
    acts.append(("C_N01", point_actor("Engine.PathNode", 0, -2048, 100)))
    acts.append(("C_N02", point_actor("Engine.PathNode", 300, -2048, -100)))
    # room D: PlayerStart + nodes at x=+6144 (beyond room A)
    acts.append(("RoomD", brush_actor("CSG_Subtract", 6144, 0, 0, 768, 256, 256)))
    acts.append(("D_Start", point_actor("Engine.PlayerStart", 5600, 0, -216)))
    acts.append(("D_N00", point_actor("Engine.PathNode", 6144, 0, -216)))
    acts.append(("D_N01", point_actor("Engine.PathNode", 6700, 0, -216)))
    acts.append(("D_Light", point_actor("Engine.Light", 6144, 0, 0)))
    return acts


def mover_actor(cls, cx, cy, cz, hx, hy, hz, extra=""):
    # KeyPos(1) is the open position; the mover rests at key 0 (closed) in the editor.
    return (f"Begin Actor Class={cls}\n{extra}"
            f"    Location=(X={cx:.6f},Y={cy:.6f},Z={cz:.6f})\n"
            f"    MainScale=(SheerAxis=SHEER_ZX)\n    PostScale=(SheerAxis=SHEER_ZX)\n"
            f"    Begin Brush Name=Model\n       Begin PolyList\n{box_polys(0, 0, 0, hx, hy, hz)}\n"
            f"       End PolyList\n    End Brush\n    Brush=Model'MyLevel.Model'\nEnd Actor\n")


def pathlab2() -> list[tuple[str, str]]:
    """Room E water (ZoneInfo bWaterZone), F door mover, G lift, H teleporters, I pickup, J node
    props, K corridor widths (radius cap), L ceiling heights (height cap)."""
    acts: list[tuple[str, str]] = [("LevelInfo", "Begin Actor Class=Engine.LevelInfo\nEnd Actor\n")]
    # E: water box, y=0 — the whole room is one zone; ZoneInfo makes it water
    acts.append(("RoomE", brush_actor("CSG_Subtract", 0, 0, 0, 512, 256, 256)))
    acts.append(("E_Zone", point_actor("Engine.ZoneInfo", 0, 0, 0, "    bWaterZone=True\n")))
    acts.append(("E_N00", point_actor("Engine.PathNode", -300, 0, -100)))
    acts.append(("E_N01", point_actor("Engine.PathNode", 0, 0, 100)))
    acts.append(("E_N02", point_actor("Engine.PathNode", 300, 0, -100)))
    # F: corridor with a closed door mover across it, nodes either side (y=2048)
    acts.append(("RoomF", brush_actor("CSG_Subtract", 0, 2048, 0, 512, 128, 128)))
    acts.append(("F_Door", mover_actor("Engine.Mover", 0, 2048, 0, 16, 128, 128,
                                       "    KeyPos(1)=(X=0.000000,Y=0.000000,Z=256.000000)\n    Tag=F_Door\n")))
    acts.append(("F_N00", point_actor("Engine.PathNode", -300, 2048, -88)))
    acts.append(("F_N01", point_actor("Engine.PathNode", 300, 2048, -88)))
    acts.append(("F_Trig", point_actor("Engine.Trigger", -300, 2048, -60, "    Event=F_Door\n")))
    # G: lift shaft — lower room and upper room joined by a lift mover; LiftCenter/LiftExit (y=4096)
    acts.append(("RoomG", brush_actor("CSG_Subtract", 0, 4096, 256, 512, 256, 512)))
    acts.append(("G_Ledge", brush_actor("CSG_Add", 384, 4096, 128, 128, 256, 128)))
    acts.append(("G_Lift", mover_actor("Engine.Mover", -256, 4096, -240, 96, 96, 16,
                                       "    KeyPos(1)=(X=0.000000,Y=0.000000,Z=480.000000)\n    Tag=G_Lift\n")))
    acts.append(("G_Center", point_actor("Engine.LiftCenter", -256, 4096, -184, "    LiftTag=G_Lift\n")))
    acts.append(("G_ExitLo", point_actor("Engine.LiftExit", 0, 4096, -216, "    LiftTag=G_Lift\n")))
    acts.append(("G_ExitHi", point_actor("Engine.LiftExit", 320, 4096, 296, "    LiftTag=G_Lift\n")))
    acts.append(("G_N00", point_actor("Engine.PathNode", 200, 4096, -216)))
    # H: two separate boxes joined by teleporters (y=6144 / y=6144, x split)
    acts.append(("RoomH1", brush_actor("CSG_Subtract", -1024, 6144, 0, 256, 256, 256)))
    acts.append(("RoomH2", brush_actor("CSG_Subtract", 1024, 6144, 0, 256, 256, 256)))
    acts.append(("H_T1", point_actor("Engine.Teleporter", -1024, 6144, -216, "    URL=H_T2\n    Tag=H_T1\n")))
    acts.append(("H_T2", point_actor("Engine.Teleporter", 1024, 6144, -216, "    URL=H_T1\n    Tag=H_T2\n")))
    acts.append(("H_N00", point_actor("Engine.PathNode", -1200, 6144, -216)))
    acts.append(("H_N01", point_actor("Engine.PathNode", 1200, 6144, -216)))
    # I: pickup → InventorySpot marker (y=-2048)
    acts.append(("RoomI", brush_actor("CSG_Subtract", 0, -2048, 0, 512, 256, 256)))
    acts.append(("I_Item", point_actor("DeusEx.MedKit", 100, -2048, -230)))
    acts.append(("I_N00", point_actor("Engine.PathNode", -300, -2048, -216)))
    acts.append(("I_N01", point_actor("Engine.PathNode", 300, -2048, -216)))
    # J: node property variants in one room (y=-4096)
    acts.append(("RoomJ", brush_actor("CSG_Subtract", 0, -4096, 0, 1024, 256, 256)))
    acts.append(("J_N00", point_actor("Engine.PathNode", -800, -4096, -216)))
    acts.append(("J_EndOnly", point_actor("Engine.PathNode", -400, -4096, -216, "    bEndPointOnly=True\n")))
    acts.append(("J_PlayerOnly", point_actor("Engine.PathNode", 0, -4096, -216, "    bPlayerOnly=True\n")))
    acts.append(("J_Extra", point_actor("Engine.PathNode", 400, -4096, -216, "    ExtraCost=500\n")))
    acts.append(("J_N04", point_actor("Engine.PathNode", 800, -4096, -216)))
    # K: corridors of widths 40..200 (radius cap), each with 2 nodes 300 apart (y=-6144.., x rows)
    for i, w in enumerate([40, 56, 72, 96, 128, 160, 200]):
        y = -6144 - i * 512
        acts.append((f"RoomK{i}", brush_actor("CSG_Subtract", 0, y, 0, 512, w / 2, 128)))
        acts.append((f"K{i}_N00", point_actor("Engine.PathNode", -150, y, -88)))
        acts.append((f"K{i}_N01", point_actor("Engine.PathNode", 150, y, -88)))
    # L: corridors of heights 48..200 (height cap), width 256 (x=4096 rows)
    for i, h in enumerate([48, 64, 80, 96, 128, 160, 200]):
        y = -6144 - i * 512
        acts.append((f"RoomL{i}", brush_actor("CSG_Subtract", 4096, y, 0, 512, 128, h / 2)))
        acts.append((f"L{i}_N00", point_actor("Engine.PathNode", 3946, y, -h / 2 + min(40, h / 2 - 4))))
        acts.append((f"L{i}_N01", point_actor("Engine.PathNode", 4246, y, -h / 2 + min(40, h / 2 - 4))))
    acts.append(("Start", point_actor("Engine.PlayerStart", -800, -4096, -216)))
    return acts


def main(argv):
    out = Path(argv[0])
    acts = pathlab2() if "--level" in argv and argv[argv.index("--level") + 1] == "pathlab2" else pathlab()
    for i, (name, t3d) in enumerate(acts):
        d = out / "actors" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "actor.t3d").write_text(t3d)
        (d / "order_value").write_text(f"{i:04d}")
    print(f"wrote {len(acts)} actors to {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
