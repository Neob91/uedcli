import sys, struct
from pathlib import Path
from collections import defaultdict, Counter
ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl")
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT/"dev/docs/spikes/2026-07-15-native-materialize/harness"))
import surf_class_diff as SCD, unatco_subset as U
bits=lambda x:struct.unpack("<I",struct.pack("<f",x))[0]
def plane(m,nd):
    s=m.surfs[nd.i_surf]; n=m.vectors[s.v_normal]; b=m.points[s.p_base]
    return n,(n[0]*b[0]+n[1]*b[1]+n[2]*b[2])
def key(n,o): return (round(n[0],3),round(n[1],3),round(n[2],3),round(o,1))
def collect(m):
    d=defaultdict(Counter)
    for nd in m.nodes:
        n,o=plane(m,nd); d[key(n,o)][tuple(bits(c) for c in n)]+=1
    return d
nat=U.native_surfs(105); gold=SCD.load_model(str(U.golden_path(105)))
dn=collect(nat); dg=collect(gold)
twin=exact=0
for k in set(dn)&set(dg):
    for nb in dn[k]:
        if nb in dg[k]: exact+=1
        elif dg[k]: twin+=1
print(f"node-plane NORMAL bit-exact={exact} twins={twin}")
