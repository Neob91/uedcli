#!/usr/bin/env python3
"""line_check.py -- offline oracle for the GAME's UModel::LineCheck.

Byte-anchored port of the collision trace in the game's Engine.dll
(/home/neob91/Games/LutrisDX/drive_c/DX/System/Engine.dll, ImageBase 0x10300000).
All RVAs below are file-RVAs at that base.  Decoded 2026-07-16 with leaf_disas.py.

Two completely different code paths live behind UModel::LineCheck (outer @0xf3c20):

  * Extent == (0,0,0): the node-plane recursion @0xf3560 ("LineCheckR").  Solidity
    comes from FBspNode::IsCsg (@0xf68b0) during the plane walk; NO LeafHulls, NO
    iCollisionBound.  This is what section 60 decoded.

  * Extent != (0,0,0) (every pawn/projectile-with-size sweep): outer @0xf3f6e builds
    an FBoxLineCheckInfo (ctor @0xf18e0) and calls FBoxLineCheckInfo::BoxLineCheck
    (@0xf42f0).  The descent uses IsCsg + plane push-out (Extent*1.1, const
    @0x10431c34) ONLY to decide which leaves to visit; the actual HIT is produced
    exclusively by clipping the swept box against the terminal leaf's convex hull
    read from Model.LeafHulls via Nodes[iParent].iCollisionBound:

        0xf4602  mov  ecx,[ebp+0x2c]      ; iCollisionBound of the leaf's parent node
        0xf4605  cmp  ecx,-1
        0xf4608  je   0xf5682             ; == -1  ->  return, NO HIT POSSIBLE

    The single DidHit store in the whole function is @0xf5678, reachable only
    through that hull clip.  So a model with iCollisionBound == -1 everywhere (our
    native builds) is completely non-solid for every non-zero-extent trace, no
    matter how correct its node planes / flags / topology are.

Public API:
    model = load_level_model(path)          # parses the largest Model export
    hit = line_check(model, start, end, extent=(20,20,44))
    -> None (no hit) or dict(time=..., location=..., normal=..., node=...)

See linecheck-oracle.md in the scratchpad re-out/ for the full decode notes.
"""
import struct
import sys
from math import sqrt
from pathlib import Path

# Derived from this file's own location, not hardcoded: harness/ -> <spike>/ -> spikes/ -> docs/
# -> dev/ -> repo root (parents[5]). A hardcoded absolute path resolved on exactly one machine, so everywhere
# else these imports failed and `test_native_materialize`'s two collision-oracle tests silently
# SKIPPED instead of running.
ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))
import utexture_decode as UT  # noqa: E402
from uedcli.native import umodel as UM  # noqa: E402
from uedcli.native.umodel import read_ci  # noqa: E402

INDEX_NONE = -1


# ---------------------------------------------------------------------------
# Loading: umodel.parse_model_body skips Bounds/LeafHulls/RootOutside; re-walk
# the serial body with the same primitives and keep them.
# ---------------------------------------------------------------------------

class LevelModel:
    def __init__(self, model, bounds, leaf_hulls, root_outside):
        self.model = model
        self.nodes = model.nodes
        self.bounds = bounds          # list[(min xyz, max xyz, valid)]
        self.leaf_hulls = leaf_hulls  # raw i32 array (box floats bit-stored)
        self.root_outside = root_outside


def load_level_model(path):
    pkg = UT.load_package(str(path))
    mi = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
             key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    data = pkg.buf[e["soff"]:e["soff"] + e["ssize"]]
    model = UM.parse_model_body(pkg.buf, e["soff"], e["ssize"])

    # Re-walk to the Bounds array (mirrors parse_model_body's field order).
    pos = UM._PREFIX
    _, pos = UM._fvector_array(data, pos)
    _, pos = UM._fvector_array(data, pos)
    _, pos = UM._parse_array(data, pos, UM._parse_node)
    _, pos = UM._parse_array(data, pos, UM._parse_surf)
    _, pos = UM._parse_array(data, pos, UM._parse_vert)
    _, pos = UM._i32(data, pos)
    num_zones, pos = UM._i32(data, pos)
    for _ in range(num_zones):
        _, pos = read_ci(data, pos)
        _, pos = UM._u64(data, pos)
        _, pos = UM._u64(data, pos)
    _, pos = read_ci(data, pos)
    _, pos = UM._parse_a8(data, pos)
    _, pos = UM._parse_bulk_bytes(data, pos)
    nb, pos = read_ci(data, pos)          # Bounds: FBox = 6*f32 + IsValid byte
    bounds = []
    for _ in range(nb):
        vals = struct.unpack_from("<6fB", data, pos)
        bounds.append((vals[0:3], vals[3:6], vals[6]))
        pos += 25
    nh, pos = read_ci(data, pos)          # LeafHulls: raw i32 array
    leaf_hulls = list(struct.unpack_from("<%di" % nh, data, pos))
    pos += nh * 4
    _, pos = UM._parse_array(data, pos, UM._parse_leaf)
    _, pos = UM._parse_e4(data, pos)
    root_outside, pos = UM._i32(data, pos)
    _locked, pos = UM._i32(data, pos)
    assert pos == len(data), (pos, len(data))
    return LevelModel(model, bounds, leaf_hulls, root_outside)


# ---------------------------------------------------------------------------
# Small vector helpers (FVector ops from Core.dll used by the trace)
# ---------------------------------------------------------------------------

def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):  # FVector::operator^  (Core.dll ??TFVector)
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _unsafe_normal(v):  # FVector::UnsafeNormal (no zero guard, like the engine)
    s = sqrt(_dot(v, v))
    return (v[0] / s, v[1] / s, v[2] / s)


def _box_push_out(extent, n):
    """FBoxPushOut @0xf6590: |Ex*nx| + |Ey*ny| + |Ez*nz|."""
    return abs(extent[0] * n[0]) + abs(extent[1] * n[1]) + abs(extent[2] * n[2])


def _plane_dot(n, w, p):  # FPlane::PlaneDot
    return _dot(n, p) - w


def _is_csg(node, extra=0):
    """FBspNode::IsCsg @0xf68b0: NumVertices>0 && (NodeFlags & (extra|0x21)) == 0."""
    return node.num_vertices > 0 and (node.node_flags & ((extra | 0x21) & 0xFF)) == 0


def _child(node, side):
    """Engine iChild[side]: serial +0x20 == parser i_front (side 0, BACK halfspace),
    serial +0x24 == parser i_back (side 1, FRONT halfspace).  Section 60 SS2.2."""
    return node.i_back if side == 1 else node.i_front


def _as_f32(i):
    return struct.unpack("<f", struct.pack("<i", i))[0]


def _norm_ci(v):
    """Parser may return iCollisionBound as unsigned; -1 sentinel handling."""
    if v is None:
        return -1
    if v >= 0x80000000:
        v -= 0x100000000
    return v


# ---------------------------------------------------------------------------
# Extent != 0 path: FBoxLineCheckInfo::BoxLineCheck @0xf42f0 (Owner == NULL,
# Coords == GMath.UnitCoords, exactly the world-model case).
# ---------------------------------------------------------------------------

class _BoxTrace:
    def __init__(self, lm, start, end, extent):
        self.nodes = lm.nodes
        self.leaf_hulls = lm.leaf_hulls
        self.start = start
        self.end = end
        self.extent = extent
        self.ext11 = (extent[0] * 1.1, extent[1] * 1.1, extent[2] * 1.1)  # 0x10431c34
        self.hit_time = 2.0        # outer inits Hit.Time = 2.0f @0xf3fa9
        self.hit_normal = None
        self.hit_node = None
        self.did_hit = False       # this+0x5ac

    # -- shared slab-clip step (inlined @0xf49f9.. and in ClipTo @0xf5c50..) --
    # st = [T0, T1, best_normal]; returns False on definite miss (-> abandon leaf)
    def _clip(self, st, d0, d1, push, n):
        adj = d0 - push
        if d0 > d1 and adj >= -push and adj < 0.0:
            adj = 0.0                       # start already interpenetrating: T=0
        delta = d0 - d1
        if delta < -1e-5:                   # 0x104335d8: exit plane
            t = adj / delta
            if t < st[1]:
                st[1] = t
        elif delta > 1e-5:                  # 0x104335c8: entry plane
            t = adj / delta
            if t > st[0]:
                st[0] = t
                st[2] = n
        else:                               # parallel
            if d0 > push and d1 > push:
                return False                # fully outside this plane -> never hits
        return st[0] < st[1]

    # -- leaf hull test (@0xf45e8..0xf5678); iparent = node owning the terminal --
    def _leaf(self, iparent):
        node = self.nodes[iparent]
        ic = _norm_ci(node.i_collision_bound)
        if ic == INDEX_NONE:                # 0xf4602/0xf4608: NO HULL -> NO HIT
            return
        LH = self.leaf_hulls
        planes = []                         # hull planes as ((nx,ny,nz), w)
        k = 0
        while k < 0x40:                     # 0xf4630: max 0x40 planes
            h = LH[ic + k]
            if h == -1:
                break
            nd = self.nodes[h & 0xBFFFFFFF]  # 0xf4645 (clears the flip bit 0x40000000)
            nx, ny, nz, w = nd.plane
            if h & 0x40000000:              # FPlane::Flip
                nx, ny, nz, w = -nx, -ny, -nz, -w
            planes.append(((nx, ny, nz), w))
            k += 1
        count = k
        # Leaf bounding box: 6 f32 bit-stored after the -1 terminator (0xf47b2).
        box = [_as_f32(LH[ic + count + 1 + j]) for j in range(6)]
        # Per-plane axis-sign flags (0xf46d4..0xf4769).
        flags = []
        for (nx, ny, nz), _w in planes:
            f = (1 if nx < 0 else (2 if nx > 0 else 0))
            f |= (4 if ny < 0 else (8 if ny > 0 else 0))
            f |= (0x10 if nz < 0 else (0x20 if nz > 0 else 0))
            flags.append(f)

        st = [-1.0, self.hit_time, (0.0, 0.0, 0.0)]  # T0 @+0x78=-1, T1 @+0x7c=Hit.Time

        # 1. hull face planes, pushed out by the (unscaled) extent (0xf480a..0xf4957)
        for n, w in planes:
            d0 = _plane_dot(n, w, self.start)
            d1 = _plane_dot(n, w, self.end)
            if not self._clip(st, d0, d1, _box_push_out(self.extent, n), n):
                return
        # 2. the 6 leaf-box face planes, pushed out 0.1 (blocks 0xf4968..0xf51a9;
        #    Owner==NULL variant with world axes)
        faces = ((( 0,  0, -1), 0.1 - box[2]),
                 (( 0,  0,  1), box[5] + 0.1),
                 ((-1,  0,  0), 0.1 - box[0]),
                 (( 1,  0,  0), box[3] + 0.1),
                 (( 0, -1,  0), 0.1 - box[1]),
                 (( 0,  1,  0), box[4] + 0.1))
        for n, w in faces:
            d0 = _plane_dot(n, w, self.start)
            d1 = _plane_dot(n, w, self.end)
            if not self._clip(st, d0, d1, _box_push_out(self.extent, n), n):
                return
        # 3. edge planes: hull-plane pairs x box axes (0xf51af..0xf55fd)
        axes = (((1.0, 0.0, 0.0), 0x03),
                ((0.0, 1.0, 0.0), 0x0C),
                ((0.0, 0.0, 1.0), 0x30))
        for i in range(count):
            for j in range(i):
                fl = flags[i] | flags[j]
                ni, wi = planes[i]
                nj, wj = planes[j]
                for axis, mask in axes:
                    if (fl & mask) != mask:
                        continue
                    c1 = _cross(axis, ni)
                    c2 = _cross(axis, nj)
                    if _dot(c1, c2) <= 0.001:   # 0xf5273: proceed only if > 0.001
                        continue
                    # FIntersectPlanes2 @0xf6600
                    d = _cross(ni, nj)
                    dd = _dot(d, d)
                    if dd < 1e-6:               # 0x10433610
                        ipt = (0.0, 0.0, 0.0)
                        d = (0.0, 0.0, 0.0)
                    else:
                        a = _cross(nj, d)       # P2 ^ D
                        b = _cross(d, ni)       # D ^ P1
                        ipt = ((wi * a[0] + wj * b[0]) / dd,
                               (wi * a[1] + wj * b[1]) / dd,
                               (wi * a[2] + wj * b[2]) / dd)
                    n = _unsafe_normal(_cross(axis, d))   # ZeroDivision == engine NaN
                    if _dot(n, ni) < 0.0:
                        n = (-n[0], -n[1], -n[2])         # operator*= -1 @0xf52f0
                    w = _dot(n, ipt)                      # FPlane(I, n)
                    # ClipTo @0xf5b80 (same slab step, unscaled extent)
                    d0 = _plane_dot(n, w, self.start)
                    d1 = _plane_dot(n, w, self.end)
                    if not self._clip(st, d0, d1, _box_push_out(self.extent, n), n):
                        return
        # acceptance @0xf561d: T0 > -1 && T0 < T1 && T1 > 0
        t0, t1 = st[0], st[1]
        if t0 <= -1.0 or not (t0 < t1) or t1 <= 0.0:
            return
        self.hit_time = t0                  # Hit.Time @0xf564f (tightens later leaves)
        self.hit_normal = st[2]
        self.hit_node = iparent
        self.did_hit = True                 # @0xf5678

    # -- descent (@0xf4309..0xf45df); iterative far side, recursive near side --
    def walk(self, iparent, inode, outside):
        while inode != INDEX_NONE:
            node = self.nodes[inode]
            nx, ny, nz, w = node.plane
            n = (nx, ny, nz)
            d0 = _plane_dot(n, w, self.start)   # this+0x590 = Start
            d1 = _plane_dot(n, w, self.end)     # this+0x584 = End
            push = _box_push_out(self.ext11, n)  # Extent * 1.1f
            use = ((d0 <= push) or (d1 <= push),      # [esp+0x1c]: visit BACK
                   (d0 >= -push) or (d1 >= -push))    # [esp+0x20]: visit FRONT
            side = 1 if d0 >= d1 else 0               # near = side start moves from
            if use[side]:
                if side == 1:
                    child_out = outside or _is_csg(node)        # inline, mask 0x21
                else:
                    child_out = outside and not _is_csg(node)   # IsCsg(0) call
                self.walk(inode, _child(node, side), child_out)  # @0xf4556
            if use[1 - side]:
                far = 1 - side
                if far == 1:
                    outside = outside or _is_csg(node)
                else:
                    outside = outside and not _is_csg(node)
                iparent = inode                     # ebx @0xf456a -> leaf parent
                inode = _child(node, far)
            else:
                return                              # @0xf4564
        if not outside:                             # @0xf45fa
            self._leaf(iparent)


def _box_line_check(lm, start, end, extent):
    """Outer UModel::LineCheck box branch @0xf3f6e..0xf413b."""
    tr = _BoxTrace(lm, start, end, extent)
    tr.walk(0, 0, lm.root_outside)                  # BoxLineCheck(0,0,0,RootOutside)
    if not tr.did_hit:
        return None
    dv = (end[0] - start[0], end[1] - start[1], end[2] - start[2])
    dist = sqrt(_dot(dv, dv))
    t = tr.hit_time - max(0.1 / dist, 0.1)          # @0xf403b..0xf405b
    t = min(max(t, 0.0), 1.0)                       # clamp [0,1]
    if t == 1.0:                                    # @0xf40f3: Time==1 -> no hit
        return None
    loc = (start[0] + dv[0] * t, start[1] + dv[1] * t, start[2] + dv[2] * t)
    return {"time": t, "location": loc, "normal": tr.hit_normal, "node": tr.hit_node}


# ---------------------------------------------------------------------------
# Extent == 0 path: LineCheckR @0xf3560 (node-plane walk, no hulls involved)
# ---------------------------------------------------------------------------

def _line_check_zero(lm, start, end, extra_flags):
    nodes = lm.nodes
    state = {"hit_empty": False}    # global @0x1058f34c, cleared by outer @0xf3c95
    res = {}

    def recurse(ihit, inode, v_end, v_start, outside):
        while True:
            if inode == INDEX_NONE:
                break
            node = nodes[inode]
            nx, ny, nz, w = node.plane
            n = (nx, ny, nz)
            d_start = _plane_dot(n, w, v_start)     # slot 0x10
            d_end = _plane_dot(n, w, v_end)         # slot 0x14
            masked = extra_flags & ~0x10            # @0xf3736: 0x10 stripped inline
            if d_start > -0.001 and d_end > -0.001:         # both front @0xf3703
                outside = outside or _is_csg(node, masked)
                inode = _child(node, 1)
            elif d_start < 0.001 and d_end < 0.001:         # both back @0xf3768
                outside = outside and not _is_csg(node, masked)
                inode = _child(node, 0)
            else:                                           # split @0xf37d2
                f = d_start / (d_end - d_start)
                middle = (v_start[0] + (v_start[0] - v_end[0]) * f,
                          v_start[1] + (v_start[1] - v_end[1]) * f,
                          v_start[2] + (v_start[2] - v_end[2]) * f)
                side = 1 if d_start > 0.0 else 0            # @0xf3883
                csg = _is_csg(node, extra_flags)            # thunk call, full flags
                near_out = (outside or csg) if side == 1 else (outside and not csg)
                if not recurse(ihit, _child(node, side), middle, v_start, near_out):
                    return 0                                # hit below -> stop all
                far = 1 - side
                outside = (outside or csg) if far == 1 else (outside and not csg)
                ihit = inode                                # @0xf39af..0xf39be
                v_start = middle
                inode = _child(node, far)
        # terminal @0xf3a03..
        if outside:
            state["hit_empty"] = True                       # @0xf3aab
            return 1
        if not state["hit_empty"] and (extra_flags & 0x10):
            return 1                                        # @0xf3a1f
        res["location"] = v_start
        res["normal"] = nodes[ihit].plane[:3]
        res["node"] = ihit
        return 0

    if recurse(0, 0, end, start, lm.root_outside):
        return None
    # outer time computation @0xf3d3d..0xf3e33
    dv = (end[0] - start[0], end[1] - start[1], end[2] - start[2])
    dsz = _dot(dv, dv)
    loc = res["location"]
    t = _dot(dv, (loc[0] - start[0], loc[1] - start[1], loc[2] - start[2])) / dsz
    t = min(max(t - 0.5 / sqrt(dsz), 0.0), 1.0)
    return {"time": t,
            "location": (start[0] + dv[0] * t, start[1] + dv[1] * t,
                         start[2] + dv[2] * t),
            "normal": res["normal"], "node": res["node"]}


# ---------------------------------------------------------------------------

def line_check(model, start, end, extent=(0.0, 0.0, 0.0), extra_flags=0):
    """Faithful UModel::LineCheck (@0xf3c20).  `model` is a LevelModel from
    load_level_model().  Returns None when unobstructed, else a hit dict."""
    lm = model
    if not lm.nodes:
        return None
    if extent[0] == 0.0 and extent[1] == 0.0 and extent[2] == 0.0:
        return _line_check_zero(lm, tuple(start), tuple(end), extra_flags)
    return _box_line_check(lm, tuple(start), tuple(end), tuple(extent))


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Swept-box / line BSP trace oracle")
    ap.add_argument("map", help="package (.dx/.unr) whose largest Model to trace")
    ap.add_argument("start", help="X,Y,Z sweep start")
    ap.add_argument("end", help="X,Y,Z sweep end")
    ap.add_argument("--extent", default="20,20,44", help="box half-size rx,ry,hz (0,0,0 = line)")
    a = ap.parse_args()
    lm = load_level_model(a.map)
    start = tuple(float(x) for x in a.start.split(","))
    end = tuple(float(x) for x in a.end.split(","))
    extent = tuple(float(x) for x in a.extent.split(","))
    nhull = sum(1 for n in lm.nodes if _norm_ci(n.i_collision_bound) != -1)
    print(f"{Path(a.map).name}: nodes={len(lm.nodes)} hull_nodes={nhull} "
          f"leaf_hulls={len(lm.leaf_hulls)} root_outside={lm.root_outside}")
    hit = line_check(lm, start, end, extent)
    if hit is None:
        print(f"  {start} -> {end} extent={extent}: NO HIT (falls through)")
    else:
        x, y, z = hit["location"]
        print(f"  {start} -> {end} extent={extent}: HIT t={hit['time']:.6f} "
              f"loc=({x:.2f},{y:.2f},{z:.2f}) normal={hit['normal']} node={hit['node']}")


if __name__ == "__main__":
    sys.setrecursionlimit(100000)
    main()
