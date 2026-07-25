"""Dump node/leaf/collision structure of a .dx level Model."""
import sys
from uedctl.native import pkg_write, umodel


def find_model(buf):
    pp = pkg_write.parse_package(buf)
    best = None
    for i, e in enumerate(pp.exports):
        cls = pp.class_of_export(i)
        nm = pp.names[e["nm"]] if 0 <= e["nm"] < len(pp.names) else ""
        if (cls == "Model" or nm == "Model") and e["ssize"] > 0:
            if best is None or e["ssize"] > best[1]:
                best = (e["soff"], e["ssize"])
    return best


def dump(path):
    buf = open(path, "rb").read()
    off, size = find_model(buf)
    m = umodel.parse_model_body(buf, off, size)
    print(f"=== {path} ===")
    print(f"nodes={len(m.nodes)} surfs={len(m.surfs)} verts={len(m.verts)} "
          f"points={len(m.points)} leaves={len(m.leaves)} zones={len(m.zones)} "
          f"num_shared_sides={m.num_shared_sides}")
    print("leaves:", m.leaves)
    print("zones:", m.zones)
    print()
    print(" ni | plane(nx,ny,nz,w)                | zmask | nf | vpool surf front back plane | "
          "iColl iRend | iZone | nv | iLeaf")
    for ni, n in enumerate(m.nodes):
        px, py, pz, pw = n.plane
        print(f"{ni:3d} | ({px:6.2f},{py:6.2f},{pz:6.2f},{pw:9.2f}) | "
              f"{n.zone_mask:#06x} | {n.node_flags:#04x} | "
              f"{n.i_vert_pool:5d} {n.i_surf:4d} {n.i_front:5d} {n.i_back:4d} {n.i_plane:5d} | "
              f"{n.i_collision_bound:5d} {n.i_render_bound:5d} | "
              f"{n.i_zone[0]:2d},{n.i_zone[1]:2d} | {n.num_vertices:2d} | "
              f"({n.i_leaf[0]},{n.i_leaf[1]})")
    print()
    # surf planes
    print("surfs (normal, offset, brushpoly, actor):")
    for si, s in enumerate(m.surfs):
        nrm = m.vectors[s.v_normal]
        base = m.points[s.p_base]
        off_ = sum(nrm[k]*base[k] for k in range(3))
        print(f"  {si:2d}: n=({nrm[0]:5.2f},{nrm[1]:5.2f},{nrm[2]:5.2f}) off={off_:9.2f} "
              f"bpoly={s.i_brush_poly} actor={s.i_actor} pf={s.poly_flags:#x} zone={s.i_zone}")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        dump(p)
        print()
