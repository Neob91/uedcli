import sys, pefile
for path in sys.argv[1:]:
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories([pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
    base = pe.OPTIONAL_HEADER.ImageBase
    exp = getattr(pe, 'DIRECTORY_ENTRY_EXPORT', None)
    if not exp:
        continue
    for s in exp.symbols:
        if not s.name:
            continue
        n = s.name.decode()
        if any(k in n for k in ('Circle', 'DrawBox', 'Draw2D', 'DrawLine', 'Radii', 'Arrow', 'Draw3D')):
            print(f"{path} RVA=0x{s.address:x} VA=0x{base + s.address:x} {n}")
