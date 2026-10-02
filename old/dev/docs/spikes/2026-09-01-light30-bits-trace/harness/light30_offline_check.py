#!/usr/bin/env python3
"""Offline (no docker) check: does the CURRENT shipped `line_clear` v2 port
(`line_clear_v2_algorithm_check.py`, byte-for-byte the same algorithm as
`uedcli-native/src/linecheck.rs`) already disagree with golden's own real per-lumel bit for a named
light, using GOLDEN's OWN real BSP tree as the oracle (no live capture needed for this part -- `LIGHT
APPLY` never rebuilds BSP, so the tree serialized into the lit `.dx` is what the real editor's shadow
ray actually walked)?

This answers the FIRST branch of the `lighting-bits-only-divergence-localizes-to` round-2026-09-01
task before spending a live gdb session: if v2 already disagrees with golden for Light30's own bad
lumels the same way it disagrees for the old (unlocalized) bucket, this is the SAME already-analyzed
`line_clear` residual, just narrower -- not a new mechanism. If v2 AGREES with golden here, the bug
must be upstream of `line_clear` (a wrong extra_flags/light-location/grid input specific to certain
lights), and only THEN is a live trace of the surrounding illuminateSurf call warranted.

Usage: light30_offline_check.py GOLDEN.dx TRUNK_PROJECT_DIR TRUNK_REL --light NAME [--trace]
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = HERE.parents[1] / "2026-08-29-unatco-repart-live-diff/harness"
LIGHTH = HERE.parents[1] / "2026-08-27-native-light-apply-parity/harness"
sys.path.insert(0, str(OLD))
sys.path.insert(0, str(LIGHTH))
sys.path.insert(0, str(HERE.parents[4]))

import line_clear_v2_algorithm_check as V2  # noqa: E402
from lightparity import level_model, light_names, runs, planes, _load  # noqa: E402


def seg_clear_v2_traced(model, inode, p1, p2, edi, extra_flags, seen_empty_global, depth, log):
    while True:
        if depth > V2.MAX_DEPTH:
            log.append(f"  d{depth}: MAX_DEPTH -> return CLEAR(1)")
            return 1
        if inode == -1:
            r = V2.terminal(edi, extra_flags, seen_empty_global)
            log.append(f"  d{depth}: TERMINAL edi={edi} seen_empty={seen_empty_global[0]} -> {r}")
            return r
        node = model.nodes[inode]
        d1 = V2.plane_dot(node.plane, p1)
        d2 = V2.plane_dot(node.plane, p2)
        log.append(f"  d{depth}: node={inode} flags=0x{node.node_flags:02x} nv={node.num_vertices} "
                   f"d1={d1:.6g} d2={d2:.6g} edi_in={edi}")
        if d1 > -V2.EPS and d2 > -V2.EPS:
            csg = V2.is_csg(node, extra_flags, strip_bright_corners=True)
            inode = V2.child(node, V2.FRONT)
            edi = (edi | 1) if csg else (edi | 0)
            log.append(f"       WHOLE-FRONT csg={csg} -> child={inode} edi_out={edi}")
            depth += 1
            continue
        if d1 < V2.EPS and d2 < V2.EPS:
            csg = V2.is_csg(node, extra_flags, strip_bright_corners=True)
            inode = V2.child(node, V2.BACK)
            edi = (edi & 0) if csg else (edi & 1)
            log.append(f"       WHOLE-BACK csg={csg} -> child={inode} edi_out={edi}")
            depth += 1
            continue
        t = V2.fdiv(d2, V2.fsub(d1, d2))
        mid = V2.vadd(p2, V2.vscaled(V2.vsub(p2, p1), t))
        near_side = V2.FRONT if d2 > 0.0 else V2.BACK
        near_child = V2.child(node, near_side)
        numverts_ok = node.num_vertices > 0
        csg_nostrip = numverts_ok and (node.node_flags & (extra_flags | V2.NF_NOT_CSG | V2.NF_IS_NEW)) == 0
        if near_side == V2.FRONT:
            near_state = 1 if edi != 0 else (1 if (numverts_ok and csg_nostrip) else 0)
        else:
            if edi == 0:
                near_state = 0
            else:
                near_state = 1 if not numverts_ok else (0 if csg_nostrip else 1)
        log.append(f"       CROSSING near_side={'FRONT' if near_side else 'BACK'} t={t:.6g} "
                   f"near_child={near_child} near_state={near_state}")
        near_result = seg_clear_v2_traced(model, near_child, mid, p2, near_state, extra_flags,
                                          seen_empty_global, depth + 1, log)
        if near_result == 0:
            log.append(f"  d{depth}: near call returned BLOCKED -> short-circuit BLOCKED")
            return 0
        far_side = V2.BACK if near_side == V2.FRONT else V2.FRONT
        far_child = V2.child(node, far_side)
        numverts_ok = node.num_vertices > 0
        csg_nostrip = numverts_ok and (node.node_flags & (extra_flags | V2.NF_NOT_CSG | V2.NF_IS_NEW)) == 0
        if near_side == V2.FRONT:
            edi = 0 if edi == 0 else (1 if not numverts_ok else (0 if csg_nostrip else 1))
        else:
            edi = 1 if edi != 0 else (0 if not numverts_ok else (1 if csg_nostrip else 0))
        log.append(f"       FAR continuation side={'BACK' if near_side == V2.FRONT else 'FRONT'} "
                   f"far_child={far_child} edi_out={edi}")
        inode = far_child
        p2 = mid
        depth += 1


def line_clear_v2_traced(model, start, end, extra_flags):
    log = []
    if not model.nodes:
        return True, log
    seen_empty_global = [0]
    result = seg_clear_v2_traced(model, 0, end, start, 0, extra_flags, seen_empty_global, 0, log)
    return result != 0, log


def main() -> int:
    golden_path = sys.argv[1]
    trunk_project, trunk_rel = sys.argv[2], sys.argv[3]
    target_light = None
    do_trace = "--trace" in sys.argv
    for i, a in enumerate(sys.argv):
        if a == "--light":
            target_light = sys.argv[i + 1]
    if target_light is None:
        print(__doc__)
        return 2

    repo = str(HERE.parents[4])
    upackage, umodel = _load(repo)
    epkg, em = level_model(upackage, umodel, golden_path)
    enames = light_names(epkg, em)
    eruns = runs(em, enames)

    import os
    os.environ.setdefault("UEDCLI_PROJECT", trunk_project)
    sys.path.insert(0, repo)
    from uedcli import config, trunk as trunk_mod
    from uedcli.classdefaults import ClassDefaults
    from uedcli.native.materialize import gather_lights
    from uedcli import packages

    project = config.load_project(trunk_project)
    user_config = config.load_user_config()
    trunk_dir = Path(trunk_project) / trunk_rel if trunk_rel != "." else Path(trunk_project)
    level, _ranks = trunk_mod.read_level(trunk_dir)
    resolver = packages.schema_resolver(project, user_config)
    defaults = ClassDefaults(resolver)
    lights = {name: (loc, radius, special) for name, loc, radius, special in
              gather_lights(level, defaults=defaults)}
    if target_light not in lights:
        print(f"[light30check] {target_light} not in participating lights ({len(lights)} total)")
        return 2
    loc, radius, special = lights[target_light]
    light_loc = tuple(V2.f32(c) for c in loc)
    world_radius = (radius + 1) * 25.0
    wr2 = world_radius * world_radius
    print(f"[light30check] {target_light} location={light_loc} radius_byte={radius} "
          f"world_radius={world_radius}")

    total = agree = skipped_out_of_range = 0
    mismatches = []
    for k in range(len(em.light_map)):
        er = eruns[k]
        if target_light not in er:
            continue
        b = em.light_map[k]
        esi, es = V2.surf_for_record(em, k)
        e_bright = bool(es.poly_flags & V2.PF_BRIGHT_CORNERS)
        e_geo = V2.row_origins(em, es, b, e_bright)
        if e_geo is None:
            continue
        e_row_origin, e_ustep, e_vstep = e_geo
        e_extra = V2.VIS_BRIGHT_CORNERS if e_bright else V2.VIS_EXTRA_FLAGS
        row_bytes = (b.u_size + 7) // 8
        pe = planes(em, b, len(er))
        block = row_bytes * b.v_size
        pos_in_run = er.index(target_light)
        eblock = pe[pos_in_run * block:(pos_in_run + 1) * block]
        for v in range(b.v_size):
            for u in range(b.u_size):
                eb = V2.bit_of(eblock, row_bytes, v, u)
                p = V2.lumel_position(e_row_origin, e_ustep, e_vstep, v, u)
                dvec = V2.vsub(p, light_loc)
                dist2 = V2.vdot(dvec, dvec)
                if dist2 >= wr2:
                    # `light.rs`'s own per-lumel `d.dot(&d) < wr2` gate: native never calls
                    # `line_clear` here at all, and the bit simply stays unset (0). Golden should
                    # agree (out of the light's world radius); count separately, don't feed
                    # `line_clear` an input native's own pipeline would never construct.
                    skipped_out_of_range += 1
                    if eb != 0:
                        mismatches.append(dict(record=k, isurf=esi, v=v, u=u, golden=eb, py=None,
                                               lumel_pos=p, bright=e_bright, extra=e_extra,
                                               note="OUT-OF-RANGE but golden says lit -- separate bug"))
                    continue
                py = V2.line_clear_v2(em, p, light_loc, e_extra)
                py_bit = 1 if py else 0
                total += 1
                if py_bit == eb:
                    agree += 1
                else:
                    mismatches.append(dict(record=k, isurf=esi, v=v, u=u, golden=eb, py=py_bit,
                                           lumel_pos=p, bright=e_bright, extra=e_extra))

    print(f"[light30check] {target_light}: {total} in-range lumel bits checked "
          f"({skipped_out_of_range} out-of-range skipped), {agree} agree with golden "
          f"({100*agree/max(total,1):.2f}%), {len(mismatches)} disagree")
    for m in mismatches[:30]:
        print(f"  rec={m['record']} isurf={m['isurf']} v={m['v']} u={m['u']} golden={m['golden']} "
              f"py={m['py']} bright_corners={m['bright']} extra_flags=0x{m['extra']:x} "
              f"lumel_pos={m['lumel_pos']} {m.get('note', '')}")

    if do_trace and mismatches:
        m = mismatches[0]
        print(f"\n[light30check] full trace for rec={m['record']} isurf={m['isurf']} "
              f"v={m['v']} u={m['u']} (golden={m['golden']} py={m['py']}):")
        result, log = line_clear_v2_traced(em, m["lumel_pos"], light_loc, m["extra"])
        for line in log:
            print(line)
        print(f"  FINAL: {result} (golden bit was {m['golden']})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
