"""Differential gate for the NEW incremental `build_geometry_bspcsg` core (flagged, opt-in).

Runs the castle trunk through BOTH the default `build_geometry` and the new
`build_geometry_bspcsg`, prints section counts vs the editor golden, and measures each built
Model's PointRegion-descent solidity against the independent point-in-solid ORACLE (CSG replay
against the brush convex hulls, computed here in Python) on a world grid.

Usage:  .venv/bin/python docs/.../harness/bspcsg_diff.py [grid_step]
"""
import sys
from pathlib import Path
ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedctl/harness"))
from uedctl import trunk
from uedctl.native import materialize as M, umodel as UM
import uedctl_native
import utexture_decode as UT

TRUNK = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/castle/uedctl/maps/foobar"
EDITOR = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx"

# editor golden target counts (from the task brief)
ED_TARGET = dict(nodes=1156, verts=16163, surfs=485, points=2035, vectors=26,
                 num_shared_sides=2739, bounds=484)


def load_editor():
    pkg = UT.load_package(EDITOR)
    mi = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
             key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    return UM.parse_model_body(pkg.buf, e["soff"], e["ssize"])


# ---- oracle: CSG replay against brush convex hulls (Python) -----------------

def _mat_apply(rot, v):
    return (rot[0][0]*v[0]+rot[0][1]*v[1]+rot[0][2]*v[2],
            rot[1][0]*v[0]+rot[1][1]*v[1]+rot[1][2]*v[2],
            rot[2][0]*v[0]+rot[2][1]*v[1]+rot[2][2]*v[2])


def _brush_world_faces(bt):
    (verts_flat, poly_sizes, _normals, oper, _pf, loc, rot, prepivot, scale, _pff) = bt
    faces = []
    off = 0
    for sz in poly_sizes:
        ring = []
        for _ in range(sz):
            v = (verts_flat[off], verts_flat[off+1], verts_flat[off+2]); off += 3
            p = (v[0]-prepivot[0], v[1]-prepivot[1], v[2]-prepivot[2])
            p = _mat_apply(rot, p)
            ring.append((p[0]+loc[0], p[1]+loc[1], p[2]+loc[2]))
        # winding normal (CCW -> outward), matching the Rust oracle's calc_normal
        nx = ny = nz = 0.0
        for i in range(2, len(ring)):
            a = (ring[i-1][0]-ring[0][0], ring[i-1][1]-ring[0][1], ring[i-1][2]-ring[0][2])
            b = (ring[i][0]-ring[0][0], ring[i][1]-ring[0][1], ring[i][2]-ring[0][2])
            nx += a[1]*b[2]-a[2]*b[1]; ny += a[2]*b[0]-a[0]*b[2]; nz += a[0]*b[1]-a[1]*b[0]
        mag = (nx*nx+ny*ny+nz*nz) ** 0.5
        if mag < 1e-6:
            continue
        faces.append((ring[0], (nx/mag, ny/mag, nz/mag)))
    return faces, oper


def build_oracle(brush_tuples):
    brushes = []
    for bt in brush_tuples:
        pf = bt[4]
        pff = bt[9]
        # non-solid if brush-level or ANY per-poly NotSolid/Portal? use brush-level + portal force
        nonsolid = (pf & 0x08) != 0 or (pf & 0x04000000) != 0
        faces, oper = _brush_world_faces(bt)
        brushes.append((faces, oper, nonsolid))
    return brushes


def oracle_solid(p, brushes, eps=0.1):
    solid = True  # DX level: solid world, subtract carves
    for faces, oper, nonsolid in brushes:
        if nonsolid or len(faces) < 4:
            continue
        inside = True
        for base, n in faces:
            d = (p[0]-base[0])*n[0]+(p[1]-base[1])*n[1]+(p[2]-base[2])*n[2]
            if d > eps:
                inside = False
                break
        if inside:
            solid = (oper == 1)  # Add -> solid, else empty
    return solid


def model_solid(model, p):
    """PointRegion descent solidity: solid iff the region resolves to zone 0."""
    if not model.nodes:
        return True
    ni = 0
    for _ in range(4096):
        n = model.nodes[ni]
        nx, ny, nz, w = n.plane
        pd = nx*p[0]+ny*p[1]+nz*p[2]-w
        side = 1 if pd >= 0 else 0
        child = n.i_back if side == 1 else n.i_front
        if child == -1:
            lf = n.i_leaf[side]
            if 0 <= lf < len(model.leaves):
                return model.leaves[lf].i_zone == 0
            return True  # no leaf -> solid
        ni = child
    return True


def main():
    step = float(sys.argv[1]) if len(sys.argv) > 1 else 64.0
    lvl, _ = trunk.read_level(Path(TRUNK))
    brush_order = [n for n in lvl.order if lvl.actors[n].brush is not None]
    bs = [M._build_brush_input(n, lvl.actors[n]) for n in brush_order]

    default = uedctl_native.build_geometry(bs)
    new = uedctl_native.build_geometry_bspcsg(bs)
    nb = uedctl_native.serialize_model(new)
    db = uedctl_native.serialize_model(default)
    m_new = UM.parse_model_body(nb, 0, len(nb))
    m_def = UM.parse_model_body(db, 0, len(db))
    ed = load_editor()

    def counts(m):
        return dict(nodes=len(m.nodes), verts=len(m.verts), surfs=len(m.surfs),
                    points=len(m.points), vectors=len(m.vectors),
                    num_shared_sides=getattr(m, "num_shared_sides", 0),
                    bounds=len(getattr(m, "bounds", []) or []),
                    leaf_hulls=len(getattr(m, "leaf_hulls", []) or []))

    cd, cn = counts(m_def), counts(m_new)
    print(f"num brushes: {len(brush_order)}")
    print(f"{'section':<16}{'default':>10}{'new':>10}{'editor':>10}")
    for k in ["nodes", "verts", "surfs", "points", "vectors", "num_shared_sides", "bounds"]:
        print(f"{k:<16}{cd[k]:>10}{cn[k]:>10}{ED_TARGET.get(k,'-'):>10}")
    print(f"{'body bytes':<16}{len(db):>10}{len(nb):>10}")

    # solidity differential over a grid
    brushes = build_oracle(bs)
    mn = [min(p[i] for p in m_new.points) for i in range(3)] if m_new.points else [0,0,0]
    mx = [max(p[i] for p in m_new.points) for i in range(3)] if m_new.points else [0,0,0]

    def grid_agree(model):
        tot = agree = 0
        z = mn[2]
        while z <= mx[2]:
            y = mn[1]
            while y <= mx[1]:
                x = mn[0]
                while x <= mx[0]:
                    p = (x, y, z)
                    o = oracle_solid(p, brushes)
                    m = model_solid(model, p)
                    tot += 1
                    if o == m:
                        agree += 1
                    x += step
                y += step
            z += step
        return agree, tot

    for label, model in [("default", m_def), ("new", m_new)]:
        a, t = grid_agree(model)
        print(f"solidity agreement ({label}) vs oracle: {a}/{t} = {100.0*a/t:.2f}%")


if __name__ == "__main__":
    main()
