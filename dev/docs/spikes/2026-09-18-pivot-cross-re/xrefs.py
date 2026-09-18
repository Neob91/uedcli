"""Find every 4-byte little-endian occurrence of given VAs in the given PE's sections."""
import sys, struct
sys.path.insert(0, "dev/docs/spikes/bspspike")
import pe

P = sys.argv[1]
targets = [int(a, 16) for a in sys.argv[2:]]
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


for t in targets:
    needle = struct.pack("<I", t)
    print(f"\n=== {t:#x}")
    for s in pef.sections:
        data = s.get_data()
        start = base + s.VirtualAddress
        i = 0
        while True:
            i = data.find(needle, i)
            if i < 0:
                break
            va = start + i
            nm = s.Name.rstrip(b"\x00").decode()
            print(f"   {va:#x}  in {nm}   {owner(va) if nm == '.text' else ''}")
            i += 1
