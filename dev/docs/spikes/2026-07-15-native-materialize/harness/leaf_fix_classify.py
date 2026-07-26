"""Prototype: apply the collision fix to a parsed level Model and show it reproduces
DXOnly's node/leaf/flag/zone pattern.

Fix (single-zone convex room):
  For every final BSP node (all are CSG surface nodes here):
    1. SWAP i_front <-> i_back so the POSITIVE (front) child lands in the engine's
       iChild[1] (+0x24) slot and the NEGATIVE (back) child in iChild[0] (+0x20).
       (Engine convention proven from PointRegion/LineCheck: positive halfspace ->
        iChild[1].)  Our build puts the positive child in i_front(+0x20); the engine
       reads +0x20 as the BACK child -> descent inverted -> floor unreachable.
    2. iLeaf: back/solid side (slot 0) = -1 always; front/empty side (slot 1) = the
       single interior leaf (0) when that child is terminal (-1), else -1.
    3. Clear NF_IsNew (0x20) from NodeFlags so FBspNode::IsCsg() treats the wall as a
       solid CSG splitter (else collision passes through).
    4. iZone = (0,1): back=solid=zone0, front=interior=zone1.  Bounds = -1.
"""
import sys
from uedcli.native import pkg_write, umodel

NF_ISNEW = 0x20


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


def load(path):
    buf = open(path, "rb").read()
    off, size = find_model(buf)
    return umodel.parse_model_body(buf, off, size)


def apply_fix(m, empty_leaf=0):
    for n in m.nodes:
        pos_child = n.i_front          # our build: positive/front child
        neg_child = n.i_back           # our build: negative/back child
        # 1. relocate to engine slots: iChild[0]=+0x20=BACK, iChild[1]=+0x24=FRONT
        n.i_front = neg_child          # -> serialized +0x20 (engine iChild[0]=back)
        n.i_back = pos_child           # -> serialized +0x24 (engine iChild[1]=front)
        # 2. iLeaf pairs with iChild slot: [0]=back/solid, [1]=front/empty
        front_terminal = (pos_child == -1)
        n.i_leaf = (-1, empty_leaf if front_terminal else -1)
        # 3. clear NF_IsNew
        n.node_flags &= ~NF_ISNEW
        # 4. zones + bounds
        n.i_zone = (0, 1)
        n.i_collision_bound = -1
        n.i_render_bound = -1
    return m


def node_sig(m):
    """(plane_normal_rounded, w_rounded, iChild0, iChild1, nodeflags, iLeaf, iZone)"""
    out = []
    for n in m.nodes:
        px, py, pz, pw = n.plane
        out.append((round(px), round(py), round(pz), round(pw),
                    n.i_front, n.i_back, n.node_flags, tuple(n.i_leaf), tuple(n.i_zone)))
    return out


def show(tag, m):
    print(f"--- {tag} ---")
    print(" ni | normal        w    | iChild0 iChild1 | nf | iLeaf  | iZone")
    for ni, n in enumerate(m.nodes):
        px, py, pz, pw = n.plane
        print(f"{ni:3d} | ({px:4.0f},{py:4.0f},{pz:4.0f}) {pw:6.0f} | "
              f"{n.i_front:7d} {n.i_back:7d} | {n.node_flags:#04x} | "
              f"{str(tuple(n.i_leaf)):7s}| {tuple(n.i_zone)}")


if __name__ == "__main__":
    DX = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/DXOnly.dx"
    NC = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/NativeCSG.dx"
    dxonly = load(DX)
    native = load(NC)
    show("DXOnly (known-good)", dxonly)
    print()
    show("NativeCSG (BEFORE fix)", native)
    print()
    apply_fix(native)
    show("NativeCSG (AFTER fix)", native)
    print()

    # Structural comparison (ignore plane winding/order differences; compare the
    # topology invariant that matters: does each node's front(iChild1) recurse toward
    # interior and terminate at exactly one interior leaf; solid terminals -1).
    def invariants(m):
        term_front_leaf = sum(1 for n in m.nodes if n.i_back == -1 and n.i_leaf[1] == 0)
        term_front_solid = sum(1 for n in m.nodes if n.i_back == -1 and n.i_leaf[1] == -1)
        back_leafed = sum(1 for n in m.nodes if n.i_leaf[0] != -1)
        isnew = sum(1 for n in m.nodes if n.node_flags & NF_ISNEW)
        return dict(interior_leaf_terminals=term_front_leaf,
                    front_solid_terminals=term_front_solid,
                    back_slots_with_leaf=back_leafed,
                    nodes_with_NF_IsNew=isnew)

    print("DXOnly invariants :", invariants(dxonly))
    print("Native AFTER fix  :", invariants(native))
