"""Find every `call dword ptr [IAT_VA]` in a PE's .text, with N instructions of context before it.

Usage: scan_iat.py <dll> <iat_va_hex> [context_instructions]
"""
import struct
import sys
import capstone
import pefile

path, iat = sys.argv[1], int(sys.argv[2], 16)
nctx = int(sys.argv[3]) if len(sys.argv) > 3 else 6

pe = pefile.PE(path, fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
data = pe.get_memory_mapped_image()
text = next(s for s in pe.sections if s.Name.rstrip(b'\x00') == b'.text')
lo, hi = text.VirtualAddress, text.VirtualAddress + text.Misc_VirtualSize
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)

needle = b'\xff\x15' + struct.pack('<I', iat)
off = lo
while True:
    i = data.find(needle, off, hi)
    if i < 0:
        break
    off = i + 1
    # Walk back far enough to decode context, then print the tail that ends at the call.
    window = 4 * nctx + 24
    start = max(lo, i - window)
    ins = list(md.disasm(data[start:i + 6], base + start))
    if not ins or ins[-1].address != base + i:
        # resync: try later start offsets until the last instruction lands on the call
        for skip in range(1, window):
            ins = list(md.disasm(data[start + skip:i + 6], base + start + skip))
            if ins and ins[-1].address == base + i:
                break
    print(f"--- call site VA 0x{base + i:x} ---")
    for c in ins[-(nctx + 1):]:
        print(f"    {c.address:#010x}  {c.mnemonic} {c.op_str}")
