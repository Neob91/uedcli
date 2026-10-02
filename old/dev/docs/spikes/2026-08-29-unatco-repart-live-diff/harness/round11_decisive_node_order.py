#!/usr/bin/env python3
r"""Round 11 (follow-up): for each fix-bucket candidate that `round11_fixbucket_brightcorners_audit.py`
flagged as sensitive to `NF_BrightCorners`, find the DECISIVE node (the one visited node whose flag,
restored alone against an otherwise-cleared tree, reproduces the original v2 answer) and its OWNING
surface's own LightMap record index, to test the "processed earlier in the bake -> already stamped"
ordering hypothesis that round 10's node-5394 case rested on (record 2296's own surface < node 5394's
owning surface's record, in round 10's language "processed after").

If a candidate's decisive node's OWNING surface record index is LOWER than the ray's own record
(plausibly already processed/stamped by the time this ray was cast, under an index-order-is-
processing-order assumption), the original golden-tree evaluation is plausible as genuinely correct,
not clearly an artifact. If it's HIGHER (owning surface processed later, mirroring round 10's own
confirmed case exactly), it's a strong artifact candidate.

This is explicitly NOT a proof (record-index order is not confirmed to equal internal bake processing
order for the general case -- round 10 flagged that as "presumably", undecoded) -- it is the same
inference round 10's own writeup drew informally, made systematic and applied to the full fix bucket.

Usage: round11_decisive_node_order.py FIXBUCKET.jsonl GOLDEN.dx
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "2026-08-27-native-light-apply-parity/harness"))
from lightparity import _load, level_model  # noqa: E402
import line_clear_v2_algorithm_check as v2mod  # noqa: E402

ROOT = HERE.parents[4]
PF_BRIGHT_CORNERS = 0x00080000
NF_BRIGHT_CORNERS = 0x10


def traced_seg_clear_v2(model, inode, p1, p2, edi, extra_flags, seen_empty_global, visited, depth=0):
    """Copy of v2mod.seg_clear_v2 that also records every visited node index."""
    while True:
        if depth > v2mod.MAX_DEPTH:
            return 1
        if inode == -1:
            return v2mod.terminal(edi, extra_flags, seen_empty_global)
        visited.append(inode)
        node = model.nodes[inode]
        d1 = v2mod.plane_dot(node.plane, p1)
        d2 = v2mod.plane_dot(node.plane, p2)
        if d1 > -v2mod.EPS and d2 > -v2mod.EPS:
            csg = v2mod.is_csg(node, extra_flags, strip_bright_corners=True)
            inode = v2mod.child(node, v2mod.FRONT)
            edi = (edi | 1) if csg else (edi | 0)
            depth += 1
            continue
        if d1 < v2mod.EPS and d2 < v2mod.EPS:
            csg = v2mod.is_csg(node, extra_flags, strip_bright_corners=True)
            inode = v2mod.child(node, v2mod.BACK)
            edi = (edi & 0) if csg else (edi & 1)
            depth += 1
            continue
        t = v2mod.fdiv(d2, v2mod.fsub(d1, d2))
        mid = v2mod.vadd(p2, v2mod.vscaled(v2mod.vsub(p2, p1), t))
        near_side = v2mod.FRONT if d2 > 0.0 else v2mod.BACK
        near_child = v2mod.child(node, near_side)
        numverts_ok = node.num_vertices > 0
        csg_nostrip = numverts_ok and (node.node_flags & (extra_flags | v2mod.NF_NOT_CSG | v2mod.NF_IS_NEW)) == 0
        if near_side == v2mod.FRONT:
            near_state = 1 if edi != 0 else (1 if (numverts_ok and csg_nostrip) else 0)
        else:
            if edi == 0:
                near_state = 0
            else:
                near_state = 1 if not numverts_ok else (0 if csg_nostrip else 1)
        near_result = traced_seg_clear_v2(model, near_child, mid, p2, near_state, extra_flags,
                                           seen_empty_global, visited, depth + 1)
        if near_result == 0:
            return 0
        far_side = v2mod.BACK if near_side == v2mod.FRONT else v2mod.FRONT
        far_child = v2mod.child(node, far_side)
        numverts_ok = node.num_vertices > 0
        csg_nostrip = numverts_ok and (node.node_flags & (extra_flags | v2mod.NF_NOT_CSG | v2mod.NF_IS_NEW)) == 0
        if near_side == v2mod.FRONT:
            if edi == 0:
                edi = 0
            else:
                edi = 1 if not numverts_ok else (0 if csg_nostrip else 1)
        else:
            if edi != 0:
                edi = 1
            else:
                edi = 0 if not numverts_ok else (1 if csg_nostrip else 0)
        inode = far_child
        p2 = mid
        depth += 1
        continue


def line_clear_v2_traced(model, start, end, extra_flags):
    visited = []
    seen_empty_global = [0]
    result = traced_seg_clear_v2(model, 0, end, start, 0, extra_flags, seen_empty_global, visited)
    return (result != 0), visited


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    dump_path, golden_path = sys.argv[1], sys.argv[2]

    repo = str(ROOT)
    upackage, umodel = _load(repo)
    epkg, em = level_model(upackage, umodel, golden_path)

    cases = [json.loads(line) for line in Path(dump_path).read_text().splitlines() if line.strip()]

    orig_flags = [n.node_flags for n in em.nodes]

    earlier = later = same = no_owner = no_decisive = 0
    rows = []
    for c in cases:
        esi, es = v2mod.surf_for_record(em, c["record"])
        if es is None or not (es.poly_flags & PF_BRIGHT_CORNERS):
            continue
        p, loc = tuple(c["p"]), tuple(c["loc"])
        e_extra = v2mod.VIS_BRIGHT_CORNERS
        # original (unmodified) trace
        result_orig, visited = line_clear_v2_traced(em, p, loc, e_extra)
        r2_orig = 1 if result_orig else 0
        assert r2_orig == c["v2"], f"trace mismatch rec={c['record']}"

        flagged_visited = [i for i in visited if orig_flags[i] & NF_BRIGHT_CORNERS]
        if not flagged_visited:
            no_decisive += 1
            continue

        decisive = None
        for i in flagged_visited:
            for n in em.nodes:
                n.node_flags &= ~NF_BRIGHT_CORNERS
            em.nodes[i].node_flags = orig_flags[i]  # restore just this one
            result_probe, _ = line_clear_v2_traced(em, p, loc, e_extra)
            r2_probe = 1 if result_probe else 0
            for j, n in enumerate(em.nodes):
                n.node_flags = orig_flags[j]
            if r2_probe == c["v2"]:
                decisive = i
                break
        if decisive is None:
            no_decisive += 1
            continue

        owner_surf_idx = em.nodes[decisive].i_surf
        if owner_surf_idx < 0 or owner_surf_idx >= len(em.surfs):
            no_owner += 1
            continue
        owner_surf = em.surfs[owner_surf_idx]
        owner_record = owner_surf.i_light_map
        if owner_record < 0:
            no_owner += 1
            continue
        rel = "SAME" if owner_record == c["record"] else ("EARLIER" if owner_record < c["record"] else "LATER")
        if rel == "EARLIER":
            earlier += 1
        elif rel == "LATER":
            later += 1
        else:
            same += 1
        rows.append((c["record"], c["light"], c["v"], c["u"], decisive, owner_surf_idx, owner_record, rel))

    print(f"{'rec':>6} {'light':>10} {'v':>3} {'u':>3} {'node':>6} {'owner_surf':>10} {'owner_rec':>9}  rel")
    for r in rows:
        print(f"{r[0]:6d} {r[1]:>10} {r[2]:3d} {r[3]:3d} {r[4]:6d} {r[5]:10d} {r[6]:9d}  {r[7]}")

    print(f"\n[order] decisive-node owning-surface record EARLIER than ray's own record: {earlier}")
    print(f"[order] decisive-node owning-surface record LATER than ray's own record: {later}")
    print(f"[order] decisive-node owning-surface record SAME as ray's own record: {same}")
    print(f"[order] no single-node-restore reproduced the original answer (multi-node/ambiguous): {no_decisive}")
    print(f"[order] decisive node has no owning-surface LightMap record (unlit surf/no owner): {no_owner}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
