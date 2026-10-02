"""Emit a T3D with N axis-aligned cube brushes at given locations (probe scene)."""
import sys

CUBE = [
    # (normal, [verts]) for a half-size H cube centred on the brush origin
]


def cube_polys(h):
    faces = [
        ((0, 0, 1), [(-h, -h, h), (-h, h, h), (h, h, h), (h, -h, h)]),
        ((0, 0, -1), [(-h, -h, -h), (h, -h, -h), (h, h, -h), (-h, h, -h)]),
        ((0, 1, 0), [(-h, h, -h), (h, h, -h), (h, h, h), (-h, h, h)]),
        ((0, -1, 0), [(-h, -h, -h), (-h, -h, h), (h, -h, h), (h, -h, -h)]),
        ((1, 0, 0), [(h, -h, -h), (h, -h, h), (h, h, h), (h, h, -h)]),
        ((-1, 0, 0), [(-h, -h, -h), (-h, h, -h), (-h, h, h), (-h, -h, h)]),
    ]
    return faces


def emit(name, model, loc, h, oper):
    out = [f"Begin Actor Class=Brush Name={name}",
           f"     CsgOper={oper}",
           "     MainScale=(SheerAxis=SHEER_ZX)",
           "     PostScale=(SheerAxis=SHEER_ZX)",
           "     Level=LevelInfo'MyLevel.LevelInfo0'",
           '     Tag="Brush"',
           "     Region=(Zone=LevelInfo'MyLevel.LevelInfo0',iLeaf=-1)",
           f"     Location=(X={loc[0]:f},Y={loc[1]:f},Z={loc[2]:f})",
           f"    Begin Brush Name={model}",
           "       Begin PolyList"]
    for i, (n, vs) in enumerate(cube_polys(h)):
        out.append(f"          Begin Polygon Item=OUTSIDE Link={i}")
        out.append("             Origin   %+012.6f,%+012.6f,%+012.6f" % vs[0])
        out.append("             Normal   %+012.6f,%+012.6f,%+012.6f" % n)
        u = (1, 0, 0) if n[0] == 0 else (0, 1, 0)
        v = (0, 1, 0) if n[2] != 0 else (0, 0, 1)
        out.append("             TextureU %+012.6f,%+012.6f,%+012.6f" % u)
        out.append("             TextureV %+012.6f,%+012.6f,%+012.6f" % v)
        for vert in vs:
            out.append("             Vertex   %+012.6f,%+012.6f,%+012.6f" % vert)
        out.append("          End Polygon")
    out += ["       End PolyList", "    End Brush",
            f"     Brush=Model'MyLevel.{model}'", "End Actor"]
    return out


lines = ["Begin Map"]
specs = [("BrushA", "ModelA", (-512, 0, 0), 128, "CSG_Add"),
         ("BrushB", "ModelB", (512, 0, 0), 128, "CSG_Add"),
         ("BrushC", "ModelC", (0, 512, 0), 128, "CSG_Add")]
for s in specs:
    lines += emit(*s)
lines.append("End Map")
open(sys.argv[1], "w").write("\n".join(lines) + "\n")
print(f"wrote {sys.argv[1]}")
