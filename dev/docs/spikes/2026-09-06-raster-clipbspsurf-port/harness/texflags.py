"""Which UE1 texture flag bools does each texture on stdin carry? (one `Pkg.Name` ref per line)

    grep -rhoP '(?<=Texture=)[A-Za-z0-9_.]+' <trunk>/actors/*/*.t3d | sort -u | texflags.py

The editor ORs `Texture->PolyFlags` (composed from these bools) into every surface's `PolyFlags`
before deciding whether it occludes; native builds without textures and cannot see them. This says
whether that gap can matter for a given level. Run from the repo root.
"""
import sys, glob, os
sys.path.insert(0, '.')
from uedcli import utexture as ut

BOOLS = ["bInvisible", "bMasked", "bTransparent", "bModulate", "bCloudWavy", "bNotSolid",
         "bEnvironment", "bSemisolid", "bFakeBackdrop", "bTwoSided", "bNoSmooth", "bBigWavy",
         "bSmallWavy", "bWaterWavy", "bLowShadowDetail", "bNoMerge", "bHighShadowDetail",
         "bSpecialLit", "bGouraud", "bUnlit", "bAlphaTexture", "bMirrored", "bPortal",
         "bAutoUPan", "bAutoVPan", "bFlat", "bDirtyShadows", "bBrightCorners"]

refs = [l.strip() for l in sys.stdin if l.strip()]
dirs = ["/workspace/uedcli/dev/games/deusex/Textures", "/workspace/uedcli/dev/games/deusex/System"]
files = {}
for d in dirs:
    for f in glob.glob(os.path.join(d, "*")):
        files.setdefault(os.path.splitext(os.path.basename(f))[0].lower(), f)

for ref in refs:
    pkgname, rest = ref.split(".", 1)
    grp = None
    name = rest
    path = files.get(pkgname.lower())
    if not path:
        print(ref, "PACKAGE NOT FOUND")
        continue
    pkg = ut.load_package(path)
    hit = None
    for i, e in enumerate(pkg.exports):
        if (pkg.name(e["nm"]) or "").lower() == name.lower() and (ut.class_fqcn_of_export(pkg, i) or "").lower().endswith("texture"):
            hit = i
            break
    if hit is None:
        print(ref, "TEXTURE NOT FOUND")
        continue
    t = ut.decode_texture(pkg, hit)
    on = [b for b in BOOLS if t.props.get(b) and bool(t.props[b][1])]
    print(f"{ref}: {on}")
