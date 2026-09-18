"""Resolve an IAT slot VA in a PE to its imported symbol name."""
import sys
sys.path.insert(0, "dev/docs/spikes/bspspike")
import pe

P = sys.argv[1]
wanted = {int(a, 16) for a in sys.argv[2:]}
pef = pe.load(P)
base = pe.image_base(P)
for entry in pef.DIRECTORY_ENTRY_IMPORT:
    dll = entry.dll.decode()
    for imp in entry.imports:
        if imp.address in wanted:
            nm = imp.name.decode() if imp.name else f"ord{imp.ordinal}"
            print(f"{imp.address:#x}  {dll}  {nm}")
