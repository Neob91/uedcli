"""Analyze the v68/69 package header FGuid + generation table across real maps,
to determine how to MINT them for a brand-new package.

Header (v>=68): 36 fixed bytes, then FGuid(16), u32 GenerationCount,
GenerationCount*(u32 ExportCount, u32 NameCount).

Checks:
 - Does the LAST generation's (ExportCount, NameCount) equal the header's
   ExportCount / NameCount?  (=> a fresh single-save package uses
   GenerationCount=1, gen[0]=(header.ExportCount, header.NameCount).)
 - Is the GUID referenced anywhere else in the file (does any import/other field
   embed it)?  (=> whether it must satisfy a constraint or can be random.)
 - PackageFlags values seen on maps.

Usage: python guid_generations.py <map.dx> [...]  |  --all
"""
from __future__ import annotations
import struct, sys, glob

MAGIC = 0x9E2A83C1


def analyze(path):
    buf = open(path, "rb").read()
    tag, ver_l, flags, namecnt, nameoff, expcnt, expoff, impcnt, impoff = \
        struct.unpack_from("<9I", buf, 0)
    if tag != MAGIC:
        return f"{path}: bad magic"
    ver = ver_l & 0xFFFF; lic = ver_l >> 16
    if ver < 68:
        return f"{path.split('/')[-1]:30s} v{ver} (pre-68, no GUID/gen table)"
    guid = buf[36:52]
    gencount, = struct.unpack_from("<I", buf, 52)
    gens = [struct.unpack_from("<II", buf, 56 + 8*k) for k in range(gencount)]
    last = gens[-1] if gens else (None, None)
    # is guid echoed elsewhere in the file?
    occ = buf.count(guid)
    return (f"{path.split('/')[-1]:30s} v{ver} lic={lic} flags={flags:#010x} "
            f"names={namecnt} exports={expcnt} gens={gencount} "
            f"last_gen=(exp={last[0]},name={last[1]}) "
            f"last==hdr:{last==(expcnt,namecnt)} guid={guid.hex()} guid_occ={occ}")


def main(argv):
    paths = argv[1:]
    if paths == ["--all"]:
        paths = sorted(glob.glob("/home/neob91/Games/LutrisDX/drive_c/DX/Maps/*.dx"))
    allmatch = True
    for p in paths:
        line = analyze(p)
        print(line)
        if "last==hdr:False" in line:
            allmatch = False
    print(f"\nALL last-gen == header counts: {allmatch}")


if __name__ == "__main__":
    main(sys.argv)
