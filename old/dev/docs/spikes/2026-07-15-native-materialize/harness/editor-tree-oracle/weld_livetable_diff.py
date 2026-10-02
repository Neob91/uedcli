#!/usr/bin/env python3
r"""EVIDENCE for the bspOptGeom pass-1 LIVE-TABLE dup-guard fix (decode §42.9).

The T-junction dup-guard (`edge_shared_elsewhere`, Editor.dll 0x36985) reads a vertex-occurrence
table keyed by point index.  The editor's inserter (0x31920) UPDATES that table's per-point head list
when it welds a vertex in, so a later edge whose two endpoints have BOTH become vertices of one node
(one of them via an earlier weld) is correctly treated as a SHARED edge and skipped.  Our port
originally used a STATIC pre-pass1 table -> it over-welded.

This harness reconstructs each side's PRE-pass1 model (final rings minus the logged welds, by
coordinate) from the built `.dx` + the weld log, then runs a faithful pass-1 with the dup-guard table
either STATIC (`live_table=False`) or LIVE-updated on each weld (`live_table=True`), counting total
welds and welds of the two z=-12 pit points (48,-500,-12)/(48,-410,-12) into node 1096.

Result (both the native AND the editor pre-pass1 model):
    static -> 977 welds, +2 spurious into node 1096
    live   -> 975 welds,  0 into node 1096   (== the editor's actual 975)

So the +2 castle over-weld is the missing live-table update, NOT a detector/Pass-D divergence.

Usage:  weld_livetable_diff.py     # needs _scratch/gtruth/NativeCastle.dx + nins.log, + the golden
"""
import re,sys,math
from pathlib import Path
from collections import defaultdict
ROOT=Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
sys.path.insert(0,str(ROOT))
from uedcli.native import umodel as UM
from uedcli.native.pkg_write import parse_package
THRESH=0.25; DEGEN=1e-6; CAP=0.251001
def load(p):
    pkg=parse_package(Path(p).read_bytes())
    mi=max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i)=="Model"),key=lambda i:pkg.exports[i]["ssize"])
    e=pkg.exports[mi]; return UM.parse_model_body(pkg.buf,e["soff"],e["ssize"])
def build_preopt(mp, il):
    m=load(mp)
    welds=defaultdict(list)
    for line in open(il):
        mm=re.match(r'(?:N?INS) node=(\d+) edge=(\d+) point=(-?\d+) plane=\S+ P=(\S+?)(?: nv=\d+)?\s*$',line.strip())
        if not mm: continue
        welds[int(mm.group(1))].append(tuple(round(float(x),1) for x in mm.group(4).split(',')))
    pts=[tuple(round(c,1) for c in p) for p in m.points]
    prerings=[]
    for ni,n in enumerate(m.nodes):
        ring=[m.verts[n.i_vert_pool+j].i_vertex for j in range(n.num_vertices)]
        for Pc in welds.get(ni,[]):
            for k,vi in enumerate(ring):
                if pts[vi]==Pc: ring.pop(k); break
        prerings.append(ring)
    return m, prerings, pts

def run(m,prerings,pts,LIVE):
    nodes=m.nodes
    table=defaultdict(set)
    for ni,ring in enumerate(prerings):
        for p in ring: table[p].add(ni)
    def shared(pa,pb,inode): return len((table[pa]&table[pb])-{inode})>0
    def pdot(pl,vi):
        p=m.points[vi]; return pl[0]*p[0]+pl[1]*p[1]+pl[2]*p[2]-pl[3]
    total=[0]; into1096=[0]
    def tj(ni,point):
        n=nodes[ni]; ring=prerings[ni]; nv=len(ring)
        if nv<1 or point in ring: return None
        N=(n.plane[0],n.plane[1],n.plane[2]); P=m.points[point]; best=-1
        for j in range(nv):
            vp=m.points[ring[j-1]]; vc=m.points[ring[j]]
            E=(vc[0]-vp[0],vc[1]-vp[1],vc[2]-vp[2])
            C=(E[1]*N[2]-E[2]*N[1],E[2]*N[0]-E[0]*N[2],E[0]*N[1]-E[1]*N[0])
            c2=C[0]**2+C[1]**2+C[2]**2
            if c2<=DEGEN: continue
            D=(P[0]-vc[0],P[1]-vc[1],P[2]-vc[2])
            proj=(C[0]*D[0]+C[1]*D[1]+C[2]*D[2])/math.sqrt(c2)
            if proj>=THRESH: return None
            if proj<=-THRESH: continue
            e2=E[0]**2+E[1]**2+E[2]**2
            M=(0.5*(vp[0]+vc[0]),0.5*(vp[1]+vc[1]),0.5*(vp[2]+vc[2]))
            R=(P[0]-M[0],P[1]-M[1],P[2]-M[2])
            if e2*CAP<(R[0]**2+R[1]**2+R[2]**2): continue
            best=j
        return best if best>=0 else None
    def apl(inode,point):
        if inode<0 or inode>=len(nodes): return
        dot=pdot(nodes[inode].plane,point)
        if dot<THRESH and nodes[inode].i_front!=-1: apl(nodes[inode].i_front,point)
        if dot<=-THRESH: return
        if nodes[inode].i_back!=-1: apl(nodes[inode].i_back,point)
        if dot>=THRESH: return
        cur=inode; g=0
        while cur!=-1 and g<len(nodes)+1:
            g+=1
            e=tj(cur,point)
            if e is not None:
                total[0]+=1
                if cur==1096 and pts[point] in {(48.0,-500.0,-12.0),(48.0,-410.0,-12.0)}: into1096[0]+=1
                prerings[cur].insert(e,point)
                if LIVE: table[point].add(cur)
            cur=nodes[cur].i_plane
    for ni in range(len(nodes)):
        b=0
        while b<len(prerings[ni]):
            r=prerings[ni]; nv=len(r); a=b-1 if b>0 else nv-1
            if not shared(r[a],r[b],ni): apl(0,r[a]); apl(0,r[b])
            b+=1
    return total[0], into1096[0]

for tag,mp,il in [("NATIVE","_scratch/gtruth/NativeCastle.dx","_scratch/gtruth/nins.log"),
                  ("EDITOR","/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx","dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle/logs/bspopt-insert.log")]:
    for LIVE in (False,True):
        m,pre,pts=build_preopt(mp,il)
        tot,i96=run(m,pre,pts,LIVE)
        print(f"[{tag}] live_table={LIVE}: total_welds={tot} welds_into_1096(targets)={i96}")
