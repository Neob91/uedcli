"""Inspect an N8 built .dx Model: classify points near x=448 as node-vertex / surf-base / neither.
Validates the FindNearestVertex-reachability model of bspAddPoint dedup."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/"dev/docs/spikes/2026-08-31-native-parity-report/harness"))
import parity_compare as PC

dx = Path(sys.argv[1])
m = PC.parse_dx_model(dx)
pts = m.points
print(f"{dx.name}: points={len(pts)} vectors={len(m.vectors)} nodes={len(m.nodes)} surfs={len(m.surfs)} verts={len(m.verts)}")

# points referenced as node vert-pool vertices
vert_pt = set(v.i_vertex for v in m.verts)
# points referenced as surf bases
base_pt = set(s.p_base for s in m.surfs)
# which surf bases belong to a node actually in the tree (all surfs are, but a base is reachable
# only if some node references that surf). node.i_surf:
node_surfs = set(n.i_surf for n in m.nodes if hasattr(n,'i_surf'))

def classify(i):
    tags=[]
    if i in vert_pt: tags.append("NODE-VERT")
    if i in base_pt: tags.append("SURF-BASE")
    return "+".join(tags) or "ORPHAN"

# find points with x near 448
print("\n-- points with |x-448|<0.01 --")
for i,p in enumerate(pts):
    if abs(p[0]-448.0) < 0.01:
        print(f"  P[{i}] = ({p[0]!r}, {p[1]!r}, {p[2]!r})  {classify(i)}")

# find surfs whose normal is (-1,0,0) and base.x near 448
print("\n-- surfs normal~(-1,0,0) --")
for si,s in enumerate(m.surfs):
    nv = m.vectors[s.v_normal]
    if abs(nv[0]+1.0)<1e-3 and abs(nv[1])<1e-3 and abs(nv[2])<1e-3:
        b = pts[s.p_base]
        if abs(b[0]-448.0)<0.5:
            print(f"  Surf[{si}] pBase={s.p_base} base=({b[0]!r},{b[1]!r},{b[2]!r})")

# node planes with normal (-1,0,0)
print("\n-- node planes normal~(-1,0,0), |W+448|<0.5 --")
for ni,n in enumerate(m.nodes):
    pl=n.plane
    if abs(pl[0]+1.0)<1e-3 and abs(pl[1])<1e-3 and abs(pl[2])<1e-3 and abs(pl[3]+448.0)<0.5:
        print(f"  Node[{ni}] plane W={pl[3]!r} iSurf={getattr(n,'i_surf','?')}")
