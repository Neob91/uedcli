"""Resolve IAT slot VAs to imported symbol names."""
import sys
import pefile

pe = pefile.PE(sys.argv[1], fast_load=True)
pe.parse_data_directories([pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
slots = {int(a, 16) for a in sys.argv[2:]}
for entry in pe.DIRECTORY_ENTRY_IMPORT:
    for imp in entry.imports:
        if imp.address in slots:
            name = imp.name.decode() if imp.name else str(imp.ordinal)
            print(f"0x{imp.address:x}  {entry.dll.decode()}  {name}")
