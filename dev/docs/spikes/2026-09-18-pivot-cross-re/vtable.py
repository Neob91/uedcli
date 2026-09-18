"""Find the UEditorEngine vtable in Editor.dll's .rdata and print slot -> export name.

A class vtable is a run of dwords that are all .text VAs. We locate it by requiring that
some slot holds the VA of a known UEditorEngine virtual (e.g. NoteSelectionChange), then
print the whole run.
"""
import sys, struct
sys.path.insert(0, "dev/docs/spikes/bspspike")
import pe

P = "uned/UED22/Editor.dll"
pef = pe.load(P)
base = pe.image_base(P)
exp = {base + rva: n for n, rva in pe.exports(P).items()}
text = [s for s in pef.sections if s.Name.rstrip(b"\x00") == b".text"][0]
tlo, thi = base + text.VirtualAddress, base + text.VirtualAddress + text.Misc_VirtualSize

anchor = base + 0x45880  # NoteSelectionChange
needle = struct.pack("<I", anchor)
for s in pef.sections:
    if s.Name.rstrip(b"\x00") not in (b".rdata", b".data"):
        continue
    data = s.get_data()
    sbase = base + s.VirtualAddress
    i = 0
    while True:
        i = data.find(needle, i)
        if i < 0:
            break
        va = sbase + i
        # walk back/forward while dwords look like .text pointers
        lo = i
        while lo - 4 >= 0:
            v = struct.unpack("<I", data[lo - 4:lo])[0]
            if not (tlo <= v < thi):
                break
            lo -= 4
        hi = i
        while hi + 4 <= len(data):
            v = struct.unpack("<I", data[hi:hi + 4])[0]
            if not (tlo <= v < thi):
                break
            hi += 4
        print(f"\n=== vtable run at {sbase + lo:#x} .. {sbase + hi:#x} "
              f"({(hi - lo) // 4} slots), anchor slot +{i - lo:#x}")
        for k in range(lo, hi, 4):
            v = struct.unpack("<I", data[k:k + 4])[0]
            nm = exp.get(v, "")
            off = k - lo
            if 0xB0 <= off <= 0x110 or nm:
                print(f"   +{off:#05x}  {v:#x}  {nm}")
        i += 1
