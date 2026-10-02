import time, math, random
random.seed(1)

# ---- Atom 1: plane classify (the CSG / SplitWithPlaneFast inner op) ----
# A poly = list of (x,y,z); plane = (bx,by,bz, nx,ny,nz). Classify all verts vs ±T.
def make_poly(nv=4):
    return [(random.uniform(-1000,1000),random.uniform(-1000,1000),random.uniform(-1000,1000)) for _ in range(nv)]
def classify(poly, base, normal, T=0.25):
    bx,by,bz=base; nx,ny,nz=normal
    mx=-1e30; mn=1e30
    for (x,y,z) in poly:
        d=(x-bx)*nx+(y-by)*ny+(z-bz)*nz
        if d>mx: mx=d
        if d<mn: mn=d
    if mx<T and mn>-T: return 0
    if mx<T: return 2
    if mn>-T: return 1
    return 3

polys=[make_poly(4) for _ in range(200)]
base=(0.0,0.0,0.0); normal=(0.577,0.577,0.577)
N=1_000_000
t0=time.perf_counter()
c=0
i=0
for _ in range(N):
    c+=classify(polys[i%200], base, normal); i+=1
t1=time.perf_counter()
t_classify=(t1-t0)/N
print(f"classify: {t_classify*1e9:.0f} ns/call  ({1/t_classify/1e6:.2f}M/s)  [avg 4-vert poly]")

# ---- Atom 2: BSP line descent (the LineCheck inner op for lighting shadow rays) ----
# Build a fake balanced-ish tree of NN nodes; each node has a plane; descend picking child by dot sign.
NN=8000
nodes=[]
for i in range(NN):
    pl=(random.uniform(-1,1),random.uniform(-1,1),random.uniform(-1,1),random.uniform(-500,500))
    L = (2*i+1) if (2*i+1)<NN else -1
    R = (2*i+2) if (2*i+2)<NN else -1
    nodes.append((pl,L,R))
def linecheck(start, end, nodes):
    # walk from root; at each node classify both endpoints, follow (simplified single-path w/ split recursion cost approx)
    sx,sy,sz=start; ex,ey,ez=end
    idx=0; visits=0
    while idx>=0:
        pl,L,R=nodes[idx]
        nx,ny,nz,w=pl
        ds=sx*nx+sy*ny+sz*nz-w
        de=ex*nx+ey*ny+ez*nz-w
        visits+=1
        if ds>=0 and de>=0: idx=R
        elif ds<0 and de<0: idx=L
        else:
            # straddle: in a real linecheck this recurses BOTH sides; approximate by following one + counting extra
            idx=R
        if visits>40: break
    return visits
M=200_000
t0=time.perf_counter()
tot=0
for _ in range(M):
    s=(random.uniform(-500,500),random.uniform(-500,500),random.uniform(-500,500))
    e=(random.uniform(-500,500),random.uniform(-500,500),random.uniform(-500,500))
    tot+=linecheck(s,e,nodes)
t1=time.perf_counter()
t_lc=(t1-t0)/M
print(f"linecheck: {t_lc*1e6:.2f} us/ray  ({1/t_lc/1e3:.1f}k/s)  avg visits={tot/M:.1f} (tree {NN} nodes)")

# ---- Extrapolate ----
print("\n=== EXTRAPOLATION (pure CPython, single core) ===")
for name, Nsurf, raytraces in [("UNATCO-HQ", 3570, 3_000_000), ("UNATCO-Island", 6821, 31_000_000)]:
    csg_classifies = 2*Nsurf*Nsurf          # ~2N^2 SplitWithPlaneFast calls over the whole bspBuild
    t_csg = csg_classifies * t_classify
    t_light = raytraces * t_lc
    print(f"{name}: bspBuild classifies~{csg_classifies/1e6:.0f}M -> CSG {t_csg:.0f}s | lighting rays~{raytraces/1e6:.0f}M -> {t_light:.0f}s | TOTAL ~{t_csg+t_light:.0f}s")
