import sys, re
sys.path.insert(0, "dev/docs/spikes/bspspike")
import pe

P = "uned/UED22/Editor.dll"
exp = pe.exports(P)
base = pe.image_base(P)
print("image base", hex(base))
pat = sys.argv[1] if len(sys.argv) > 1 else r"SetPivot|ResetPivot|NoteSelectionChange|MouseDelta|Click@|edact"
for n, rva in sorted(exp.items(), key=lambda kv: kv[1]):
    if re.search(pat, n):
        print(f"{rva:#08x}  VA={base+rva:#x}  {n}")
