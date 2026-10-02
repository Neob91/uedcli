import pefile, sys
pe = pefile.PE(sys.argv[1])
want = int(sys.argv[2], 16) if len(sys.argv) > 2 else None
base = pe.OPTIONAL_HEADER.ImageBase
for d in pe.DIRECTORY_ENTRY_IMPORT:
    for imp in d.imports:
        va = imp.address
        if want is not None and va != want:
            continue
        print(f"0x{va:08x} {d.dll.decode()} {imp.name.decode() if imp.name else imp.ordinal}")
