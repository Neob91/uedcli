"""Given a FILE OFFSET of a wide string in a PE, compute its VA and find code xrefs."""
import sys, struct
sys.path.insert(0, "dev/docs/spikes/bspspike")
import pe

P = sys.argv[1]
pef = pe.load(P)
base = pe.image_base(P)
exp = sorted((rva, n) for n, rva in pe.exports(P).items())


def owner(va):
    rva = va - base
    best = (0, "<none>")
    for r, n in exp:
        if r <= rva:
            best = (r, n)
        else:
            break
    return best[1]


for a in sys.argv[2:]:
    off = int(a, 16)
    va = None
    for s in pef.sections:
        lo = s.PointerToRawData
        hi = lo + s.SizeOfRawData
        if lo <= off < hi:
            va = base + s.VirtualAddress + (off - lo)
            break
    print(f"\nfile offset {off:#x} -> VA {va:#x}")
    needle = struct.pack("<I", va)
    for s in pef.sections:
        data = s.get_data()
        sbase = base + s.VirtualAddress
        i = 0
        while True:
            i = data.find(needle, i)
            if i < 0:
                break
            x = sbase + i
            print(f"   ref at {x:#x} ({s.Name.rstrip(chr(0).encode()).decode()})  {owner(x)}")
            i += 1
