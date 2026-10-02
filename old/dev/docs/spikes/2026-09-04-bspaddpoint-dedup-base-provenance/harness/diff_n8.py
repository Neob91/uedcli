"""Full node/surf/point/poly diff native vs ref N8, and per-node plane provenance:
is editor's plane W == raw base (Base·N) or == Points[pBase]·N ?"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/"dev/docs/spikes/2026-08-31-native-parity-report/harness"))
import parity_compare as PC
nat = PC.parse_dx_model(Path(sys.argv[1]))
ref = PC.parse_dx_model(Path(sys.argv[2]))
print(f"nat nodes={len(nat.nodes)} ref nodes={len(ref.nodes)}  surfs {len(nat.surfs)}/{len(ref.surfs)} points {len(nat.points)}/{len(ref.points)}")

def dot(pl_or_pt, n):
    return pl_or_pt[0]*n[0]+pl_or_pt[1]*n[1]+pl_or_pt[2]*n[2]

print("\n== node-plane W differences (native vs ref) ==")
for i,(a,b) in enumerate(zip(nat.nodes, ref.nodes)):
    if a.plane != b.plane:
        s = b.i_surf
        nvec = ref.vectors[ref.surfs[s].v_normal]
        pbase_pt = ref.points[ref.surfs[s].p_base]
        w_from_pbase = -dot(pbase_pt, nvec)   # plane W = base·N, W stored is -(base·N)? check sign
        print(f" Node[{i}] iSurf={s} pBase={ref.surfs[s].p_base}")
        print(f"    nat.plane={tuple(round(x,5) for x in a.plane)}")
        print(f"    ref.plane={tuple(round(x,5) for x in b.plane)}")
        print(f"    Points[pBase]={tuple(round(x,5) for x in pbase_pt)}  N={tuple(round(x,4) for x in nvec)}")
        print(f"    ref.W={b.plane[3]!r}   -(Points[pBase].N)={-dot(pbase_pt,nvec)!r}   match_pbase={abs(b.plane[3]-(-dot(pbase_pt,nvec)))<1e-6}")

print("\n== surf pBase differences ==")
for i,(a,b) in enumerate(zip(nat.surfs, ref.surfs)):
    if a.p_base != b.p_base:
        print(f" Surf[{i}] nat.pBase={a.p_base}({tuple(round(x,4) for x in nat.points[a.p_base])}) ref.pBase={b.p_base}({tuple(round(x,4) for x in ref.points[b.p_base])})")

print("\n== point table differences ==")
d=0
for i,(a,b) in enumerate(zip(nat.points, ref.points)):
    if a!=b:
        print(f" P[{i}] nat={a} ref={b}"); d+=1
print(f" ({d} point diffs)")
