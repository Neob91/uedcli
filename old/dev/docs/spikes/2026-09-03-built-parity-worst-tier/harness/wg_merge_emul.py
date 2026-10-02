"""Emulate bsp_merge_coplanars' merge_group over the dumped ilink-240 pre-merge rings (Garage
n=40) per uedcli-native/src/bspcsg.rs + fpoly.rs, with per-attempt tracing, to find why native
ends at 13 polys where the editor ends at 1."""
import sys
import re
import math
from pathlib import Path

S = Path(__file__).resolve().parent.parent / "logs"
SAME, NEAR, COLIN = 0.002, 0.015, 0.0001
SMALL = 1e-8


def load(ilink):
    polys = []
    cur = None
    for line in (S / "wg-n40-premerge-native.log").read_text().splitlines():
        if line.startswith("PREMERGE"):
            m = re.search(r"ilink=(\d+) .*N=([^ ]+)", line)
            cur = None
            if int(m.group(1)) == ilink:
                cur = {"N": tuple(float(x) for x in m.group(2).split(",")), "v": []}
                polys.append(cur)
        elif line.startswith("PMVERT") and cur is not None:
            cur["v"].append(tuple(float(x) for x in line.split()[1].split(",")))
    return polys


def sub(a, b): return (a[0]-b[0], a[1]-b[1], a[2]-b[2])
def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def dot(a, b): return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]


def safe_normal(v):
    s = dot(v, v)
    if s < SMALL:
        return None
    l = math.sqrt(s)
    return (v[0]/l, v[1]/l, v[2]/l)


def points_close(p, q, tol):
    return all(abs(p[i]-q[i]) < tol for i in range(3))


def split_side(verts, base, normal, t=0.25):
    ds = [dot(sub(v, base), normal) for v in verts]
    mx, mn = max(ds), min(ds)
    if mx < t and mn > -t:
        return "coplanar"
    if mx < t:
        return "back"
    if mn > -t:
        return "front"
    return "split"


def remove_colinears(poly):
    verts = list(poly["v"])
    N = poly["N"]
    if len(verts) < 3:
        return None
    sides = []
    i = 0
    while i < len(verts):
        prev = verts[(i + len(verts) - 1) % len(verts)]
        s = safe_normal(cross(sub(verts[i], prev), N))
        if s is None:
            verts.pop(i)
        else:
            sides.append(s)
            i += 1
        if len(verts) < 3:
            return None
    i = 0
    while i < len(verts):
        ni = (i + 1) % len(verts)
        if points_close(sides[i], sides[ni], COLIN):
            verts.pop(i)
            sides.pop(i)
            if len(verts) < 3:
                return None
            continue
        side = split_side(verts, verts[i], sides[i])
        if side in ("front", "split"):
            return "REFLEX"
        i += 1
    return {"N": N, "v": verts}


def try_to_merge(a, b, *, neigh_tol=NEAR, gate="pre", trace=None):
    nv1, nv2 = len(a["v"]), len(b["v"])
    if gate == "pre" and nv1 + nv2 > 16:
        if trace is not None:
            trace.append("gate16")
        return None
    s1 = s2 = -1
    for i in range(nv1):
        for j in range(nv2):
            if points_close(a["v"][i], b["v"][j], SAME):
                s1, s2 = i, j
                break
        if s1 >= 0:
            break
    if s1 < 0:
        if trace is not None:
            trace.append("nopoint")
        return None
    e1, e2 = s1, s2
    tf1, tf2 = (s1+1) % nv1, (s2-1) % nv2
    if points_close(a["v"][tf1], b["v"][tf2], neigh_tol):
        e1, s2 = tf1, tf2
    else:
        tb1, tb2 = (s1-1) % nv1, (s2+1) % nv2
        if points_close(a["v"][tb1], b["v"][tb2], neigh_tol):
            s1, e2 = tb1, tb2
        else:
            if trace is not None:
                trace.append("noedge")
            return None
    ring = [a["v"][(e1+k) % nv1] for k in range(nv1)]
    ring += [b["v"][(e2+1+k) % nv2] for k in range(nv2-2)]
    out = {"N": a["N"], "v": ring}
    rc = remove_colinears(out)
    if rc == "REFLEX" or rc is None:
        if trace is not None:
            trace.append("reflex" if rc == "REFLEX" else "collapse")
        return None
    if len(rc["v"]) > 16:
        if trace is not None:
            trace.append("post16")
        return None
    if gate == "post" and False:
        pass
    if trace is not None:
        trace.append("OK")
    return rc


def merge_group(polys, **kw):
    fails = {}
    g = len(polys)
    again = True
    while again:
        again = False
        for a in range(g):
            if polys[a] is None or not polys[a]["v"]:
                continue
            for b in range(a+1, g):
                if polys[b] is None or not polys[b]["v"]:
                    continue
                tr = []
                m = try_to_merge(polys[a], polys[b], trace=tr, **kw)
                fails[tr[-1]] = fails.get(tr[-1], 0) + 1
                if m is not None:
                    polys[a] = m
                    polys[b] = {"N": polys[b]["N"], "v": []}
                    again = True
    alive = [p for p in polys if p and p["v"]]
    return alive, fails


def try_to_merge_retry(a, b, *, neigh_tol=NEAR, anchor_tol=SAME, trace=None):
    """Variant: keep scanning (i,j) anchor pairs when the neighbour test fails, instead of
    giving up after the FIRST coincident point."""
    nv1, nv2 = len(a["v"]), len(b["v"])
    if nv1 + nv2 > 16:
        if trace is not None:
            trace.append("gate16")
        return None
    found = False
    for i in range(nv1):
        for j in range(nv2):
            if not points_close(a["v"][i], b["v"][j], anchor_tol):
                continue
            found = True
            s1, s2, e1, e2 = i, j, i, j
            tf1, tf2 = (s1+1) % nv1, (s2-1) % nv2
            tb1, tb2 = (s1-1) % nv1, (s2+1) % nv2
            if points_close(a["v"][tf1], b["v"][tf2], neigh_tol):
                e1, s2 = tf1, tf2
            elif points_close(a["v"][tb1], b["v"][tb2], neigh_tol):
                s1, e2 = tb1, tb2
            else:
                continue
            ring = [a["v"][(e1+k) % nv1] for k in range(nv1)]
            ring += [b["v"][(e2+1+k) % nv2] for k in range(nv2-2)]
            rc = remove_colinears({"N": a["N"], "v": ring})
            if rc == "REFLEX" or rc is None or len(rc["v"]) > 16:
                continue
            if trace is not None:
                trace.append("OK")
            return rc
    if trace is not None:
        trace.append("noedge" if found else "nopoint")
    return None


def merge_group_with(polys, merger):
    fails = {}
    g = len(polys)
    again = True
    while again:
        again = False
        for a in range(g):
            if polys[a] is None or not polys[a]["v"]:
                continue
            for b in range(a+1, g):
                if polys[b] is None or not polys[b]["v"]:
                    continue
                tr = []
                m = merger(polys[a], polys[b], trace=tr)
                fails[tr[-1]] = fails.get(tr[-1], 0) + 1
                if m is not None:
                    polys[a] = m
                    polys[b] = {"N": polys[b]["N"], "v": []}
                    again = True
    alive = [p for p in polys if p and p["v"]]
    return alive, fails


polys = load(240)
print(f"loaded {len(polys)} premerge polys, nv seq: {[len(p['v']) for p in polys]}")
for gate, tol, label in [("pre", NEAR, "as-ported (pre-gate16, NEAR neigh)"),
                         ("pre", SAME, "pre-gate16, SAME neigh")]:
    alive, fails = merge_group([dict(p) for p in polys], gate=gate, neigh_tol=tol)
    print(f"{label}: -> {len(alive)} polys, nv={[len(p['v']) for p in alive]}, fails={fails}")
import functools
for atol, ntol, label in [(SAME, NEAR, "RETRY anchors, anchor SAME, neigh NEAR"),
                          (NEAR, NEAR, "RETRY anchors, anchor NEAR, neigh NEAR")]:
    alive, fails = merge_group_with([dict(p) for p in polys],
                                    functools.partial(try_to_merge_retry,
                                                      anchor_tol=atol, neigh_tol=ntol))
    print(f"{label}: -> {len(alive)} polys, nv={[len(p['v']) for p in alive]}, fails={fails}")
if len(sys.argv) > 1 and sys.argv[1] == "rings":
    alive, _ = merge_group([dict(p) for p in polys], gate="pre", neigh_tol=NEAR)
    for p in alive:
        print([tuple(round(c, 2) for c in v) for v in p["v"]])
