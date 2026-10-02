import sys, struct
sys.path.insert(0, "dev/docs/spikes/bspspike")
import pe
P = sys.argv[1]
for a in sys.argv[2:]:
    va = int(a, 16)
    b = pe.read_at_va(P, va, 16)
    print(f"{va:#x}: {b.hex()}  f32={struct.unpack('<4f', b)}  u32={struct.unpack('<4I', b)}")
