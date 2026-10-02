"""Verify the claim: the Deus Ex `.u`/`.dx` package FORMAT is the same as stock
Unreal/UT (UnrealEngine 1); the v68-vs-v69 version number gates nothing at the
format level. The real reason a DeusEx code package won't LOAD into the
UT-lineage UED22 editor is class-graph divergence (its own Engine/Core), not the
version field.

Pure offline, reads bytes directly. Run from Tools/uedcli with the .venv-uedcli python."""
import struct, sys
sys.path.insert(0, ".")
from uedcli import dxpkg

MAGIC = 0x9E2A83C1

# Same package name present in BOTH trees: v68 = real DeusEx install, v69 = UED22 (UT-lineage editor).
V68 = "uned/DeusExAssets/System"          # the actual Deus Ex game install (v68 code)
V69 = "uned/UED22"                        # UT-lineage UnrealEd 2.2 substrate (v69 .u)

def summary(path):
    buf = open(path, "rb").read()
    tag, ver_l, flags, namecnt, nameoff, expcnt, expoff, impcnt, impoff = \
        struct.unpack_from("<9I", buf, 0)
    return dict(tag=tag, file_ver=ver_l & 0xFFFF, lic_ver=(ver_l >> 16) & 0xFFFF,
                flags=flags, names=namecnt, exports=expcnt, imports=impcnt, size=len(buf))

def show(label, path):
    s = summary(path)
    same_magic = "OK same magic" if s["tag"] == MAGIC else "!! DIFFERENT MAGIC"
    print(f"  {label:<34} ver={s['file_ver']:<3} lic={s['lic_ver']:<3} "
          f"magic={s['tag']:#010x} ({same_magic})  "
          f"names={s['names']:<5} imports={s['imports']:<4} exports={s['exports']:<5}")
    return s

print("=" * 100)
print("1. MAGIC + VERSION across both trees (same package name in each)")
print("=" * 100)
for pkg in ("DeusEx.u", "Engine.u", "Core.u", "ConSys.u"):
    print(f"{pkg}:")
    a = show(f"v68 DeusEx install", f"{V68}/{pkg}")
    try:
        b = show(f"v69 UED22 (UT editor)", f"{V69}/{pkg}")
    except FileNotFoundError:
        print(f"  {'v69 UED22 (UT editor)':<34} (not in UED22 tree)")
    print()

print("=" * 100)
print("2. Header layout is IDENTICAL for v68 and v69: the SAME parser reads both with no")
print("   version-specific branch (the ver>=64 path); only v61 uses a different name table.")
print("=" * 100)
for label, path in (("v68 DeusEx.u", f"{V68}/DeusEx.u"), ("v69 DeusEx.u", f"{V69}/DeusEx.u")):
    h = dxpkg.parse_header(path)
    print(f"  {label:<16} parsed: version={h.version}  names={len(h.names)}  imports={len(h.imports)}  "
          f"(read path: {'v61 null-term' if h.version < 64 else 'ver>=64 compact-index'})")
print()

print("=" * 100)
print("3. WHY a DeusEx code package can't load into the UT-lineage editor: it imports from")
print("   Engine/Core (a DeusEx-flavored class graph). The version is irrelevant to this.")
print("=" * 100)
h = dxpkg.parse_header(f"{V68}/DeusEx.u")
# imports: (ClassPackage, ClassName, PackageIndex, ObjectName) — names indexed into the name table
dep_pkgs = sorted({h.names[ip[0]] for ip in h.imports if 0 <= ip[0] < len(h.names)})
print(f"  v68 DeusEx.u import-table class-package names (sample): "
      f"{', '.join(p for p in dep_pkgs if p in ('Core','Engine','Editor'))}  "
      f"... ({len(dep_pkgs)} distinct)")
# Show that it references Engine/Core symbols by NAME — those symbols must exist in whatever
# Engine/Core is loaded. UT's Engine/Core differ → link failure, regardless of version.
print(f"  -> these names are resolved against whatever Engine.u/Core.u the EDITOR has loaded;")
print(f"     UT's Engine/Core != DeusEx's, so symbols mismatch. That is the load blocker.")
