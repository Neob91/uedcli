import pefile, sys, re
p = sys.argv[1]
pe = pefile.PE(p)
base = pe.OPTIONAL_HEADER.ImageBase
pat = sys.argv[2] if len(sys.argv) > 2 else ""
out = []
for e in pe.DIRECTORY_ENTRY_EXPORT.symbols:
    if not e.name:
        continue
    n = e.name.decode()
    if pat and not re.search(pat, n, re.I):
        continue
    out.append((e.address, n))
out.sort()
for a, n in out:
    print(f"0x{a:08x} {n}")
print(f"# {len(out)} matches, imagebase 0x{base:x}", file=sys.stderr)
