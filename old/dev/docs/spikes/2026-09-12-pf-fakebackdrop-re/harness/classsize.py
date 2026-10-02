"""Find sizeof(AActor)/sizeof(AZoneInfo) from the UClass ctor call sites in Engine.dll."""
import re
import struct
import sys

sys.path.insert(0, "dev/docs/spikes/bspspike")
import pe  # noqa: E402

path = "uned/UED22/Engine.dll"
p = pe.load(path)
base = pe.image_base(path)
exp = pe.exports(path)
want = ("AActor@", "AZoneInfo@", "ASkyZoneInfo@", "APlayerPawn@", "APawn@", "AInfo@")
targets = {n: r for n, r in exp.items() if "PrivateStaticClass" in n and any(k in n for k in want)}
sec = [x for x in p.sections if x.Name.rstrip(b"\0") == b".text"][0]
raw = p.__data__[sec.PointerToRawData : sec.PointerToRawData + min(sec.Misc_VirtualSize, sec.SizeOfRawData)]
from capstone import CS_ARCH_X86, CS_MODE_32, Cs  # noqa: E402

md = Cs(CS_ARCH_X86, CS_MODE_32)
md.detail = True
for n, r in sorted(targets.items()):
    va = base + r
    for m in re.finditer(re.escape(struct.pack("<I", va)), raw):
        off = m.start()
        rva = sec.VirtualAddress + off
        # dump the ~0x60 bytes before the reference: the ctor's pushed args
        start = max(0, off - 0x60)
        ins = list(md.disasm(raw[start : off + 8], base + sec.VirtualAddress + start))
        pushes = [i.op_str for i in ins if i.mnemonic == "push"]
        print(f"{n}\n   ref rva {rva:#x}  preceding pushes: {pushes[-14:]}")
