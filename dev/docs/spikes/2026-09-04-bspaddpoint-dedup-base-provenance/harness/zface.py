import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]; sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/"dev/docs/spikes/2026-08-31-native-parity-report/harness"))
import parity_compare as PC
for tag,fn in [("ref",sys.argv[1])]:
    m=PC.parse_dx_model(Path(fn))
    print(f"== {tag} Z-normal nodes, |W|~240 or ~416 ==")
    for i,n in enumerate(m.nodes):
        pl=n.plane
        if abs(pl[0])<1e-3 and abs(pl[1])<1e-3 and abs(abs(pl[2])-1)<1e-3:
            w=pl[3]
            if any(abs(abs(w)-t)<0.01 for t in (240,416,239.99998)):
                s=m.surfs[n.i_surf]; pb=m.points[s.p_base]; nv=m.vectors[s.v_normal]
                wp = pb[0]*nv[0]+pb[1]*nv[1]+pb[2]*nv[2]
                print(f" Node[{i}] W={w!r} iSurf={n.i_surf} pBase={s.p_base} Points[pBase]=({pb[0]!r},{pb[1]!r},{pb[2]!r}) Points[pBase].N={wp!r} W==pBaseN? {abs(w-wp)<1e-6}")
