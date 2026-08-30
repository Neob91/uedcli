#!/usr/bin/env python3
"""Offline algorithm cross-check for `linecheck::line_clear` (the per-lumel shadow-ray BSP
line-of-sight test) against the "bits-only" bucket: `LightMap` records where grid/run/pan/scale all
match between native and the editor golden, but individual shadow bits still differ
(`native-light-apply-bake-where-it-stands-and`'s gap 2; `lumel_axes` was chased and REFUTED as the
cause -- see `lumel_axes_live_check.py` + the findings ledger -- leaving `line_clear` as the next
suspect).

Unlike the `lumel_axes` check, this needs NO live gdb capture: the editor's real per-call BSP Model
is not scratch state that gets thrown away -- it is exactly what `LIGHT APPLY` serializes into the
golden `.dx`'s `Engine.Model` export, and the golden's own stored shadow bits ARE the editor's real
`LineCheck` answer for every lumel. So the whole test is offline:

1. Re-implement `linecheck::line_clear` (and the exact per-lumel position walk from `light.rs::
   bake_surf`) faithfully in Python, f32-rounding every operation like `lumel_axes_live_check.py`
   already does for the axis-basis formula.
2. For each mismatching bit in the "bits-only" bucket, recompute the EXACT ray endpoints
   (`p`, `light.location`) from the golden's own surface/record data (base, u_dir/v_dir, pan, scale,
   self-shadow bias, PF_BrightCorners) -- the same inputs `bits_only_input_check.py` already showed
   are bit-identical between native and the golden for this bucket.
3. Run the Python `line_clear` port against the GOLDEN's own real BSP node tree (parsed straight out
   of golden.dx -- no live capture needed, it's already on disk) for those exact endpoints, and
   compare against the golden's own actual stored bit.
   - If they MATCH: the algorithm, as coded, reproduces the editor's real per-lumel decision when
     given the editor's real tree -- `line_clear` is NOT the bug, and the residual bit divergence is
     a downstream consequence of native's own (structurally exact, but not float-identical) BSP tree
     -- the already-tracked Points/geometry residual, not a new line_clear defect.
   - If they DIFFER: a genuine algorithm bug in `line_clear` (or the position walk) is confirmed and
     localized to a specific case.
4. Self-consistency control: run the SAME Python port against NATIVE's own tree/inputs and compare
   against NATIVE's own actual stored bit (the real Rust `line_clear`'s real output) -- this must
   match, or the Python port itself is buggy and step 3's conclusion is worthless.

Usage: line_clear_algorithm_check.py NATIVE.dx GOLDEN.dx TRUNK_PROJECT_DIR TRUNK_REL [--limit N]
  e.g.  line_clear_algorithm_check.py \\
            logs/light-spotcheck-wanchai-native.dx \\
            _scratch/wanchai-relight-2026-08-29/golden.dx \\
            dev/games .
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "2026-08-27-native-light-apply-parity/harness"))
from lightparity import _load, level_model, light_names, runs, planes  # noqa: E402

ROOT = Path(__file__).resolve().parents[5]

# ---- f32 helpers (mirrors light.rs / linecheck.rs exactly, one rounding per op) ----------------


def f32(x: float) -> float:
    return struct.unpack("f", struct.pack("f", x))[0]


def fadd(a, b):
    return f32(a + b)


def fsub(a, b):
    return f32(a - b)


def fmul(a, b):
    return f32(a * b)


def fdiv(a, b):
    if b == 0.0:
        return float("nan")
    return f32(a / b)


def vadd(a, b):
    return (fadd(a[0], b[0]), fadd(a[1], b[1]), fadd(a[2], b[2]))


def vscaled(v, s):
    return (fmul(v[0], s), fmul(v[1], s), fmul(v[2], s))


def vsub(a, b):
    return (fsub(a[0], b[0]), fsub(a[1], b[1]), fsub(a[2], b[2]))


def vdot(a, b):
    return fadd(fadd(fmul(a[0], b[0]), fmul(a[1], b[1])), fmul(a[2], b[2]))


def vcross(a, b):
    return (
        fsub(fmul(a[1], b[2]), fmul(a[2], b[1])),
        fsub(fmul(a[2], b[0]), fmul(a[0], b[2])),
        fsub(fmul(a[0], b[1]), fmul(a[1], b[0])),
    )


# ---- lumel_axes (already live-verified 80/80 bit-identical -- reused unchanged) ----------------


def lumel_axes_py(tu, tv, n):
    c0 = vcross(tv, n)
    det = vdot(tu, c0)
    if abs(det) < 1e-8:
        return None
    rdet = f32(1.0 / det)
    c1 = vcross(n, tu)
    u = vscaled(c0, rdet)
    v = vscaled(c1, rdet)
    return u, v


def bright_corners_step(scale: float, size: int) -> float:
    return f32(float(scale) - 0.5 / (size - 1))


# ---- linecheck::line_clear, ported verbatim -----------------------------------------------------

NF_NOT_CSG = 0x01
NF_NOT_VIS_BLOCKING = 0x04
NF_BRIGHT_CORNERS = 0x10
NF_IS_NEW = 0x20
VIS_EXTRA_FLAGS = NF_NOT_VIS_BLOCKING
VIS_BRIGHT_CORNERS = NF_NOT_VIS_BLOCKING | NF_BRIGHT_CORNERS
PF_BRIGHT_CORNERS = 0x00080000
MAX_DEPTH = 4096
FRONT, BACK = 1, 0

sys.setrecursionlimit(20000)


def plane_dot(p, v):
    s = fadd(fadd(fmul(p[0], v[0]), fmul(p[1], v[1])), fmul(p[2], v[2]))
    return fsub(s, p[3])


def lerp(a, b, t):
    return (
        fadd(a[0], fmul(fsub(b[0], a[0]), t)),
        fadd(a[1], fmul(fsub(b[1], a[1]), t)),
        fadd(a[2], fmul(fsub(b[2], a[2]), t)),
    )


def is_csg(node, extra_flags):
    return node.num_vertices > 0 and (
        node.node_flags & ((extra_flags & ~NF_BRIGHT_CORNERS) | NF_NOT_CSG | NF_IS_NEW)
    ) == 0


def child(node, side):
    return node.i_back if side == FRONT else node.i_front


def descend(model, child_i, side, parent_csg, a, b, depth, extra_flags, seen_empty):
    if child_i == -1:
        if not (side == BACK and parent_csg):
            seen_empty[0] = True
            return True
        return (not seen_empty[0]) and (extra_flags & NF_BRIGHT_CORNERS != 0)
    return seg_clear(model, child_i, a, b, depth + 1, extra_flags, seen_empty)


def seg_clear(model, inode, start, end, depth, extra_flags, seen_empty):
    if depth > MAX_DEPTH:
        return True
    node = model.nodes[inode]
    ds = plane_dot(node.plane, start)
    de = plane_dot(node.plane, end)
    csg = is_csg(node, extra_flags)
    if ds >= 0.0 and de >= 0.0:
        return descend(model, child(node, FRONT), FRONT, csg, start, end, depth, extra_flags, seen_empty)
    if ds < 0.0 and de < 0.0:
        return descend(model, child(node, BACK), BACK, csg, start, end, depth, extra_flags, seen_empty)
    t = fdiv(ds, fsub(ds, de))
    mid = lerp(start, end, t)
    if ds >= 0.0:
        return (descend(model, child(node, FRONT), FRONT, csg, start, mid, depth, extra_flags, seen_empty)
                and descend(model, child(node, BACK), BACK, csg, mid, end, depth, extra_flags, seen_empty))
    return (descend(model, child(node, BACK), BACK, csg, start, mid, depth, extra_flags, seen_empty)
            and descend(model, child(node, FRONT), FRONT, csg, mid, end, depth, extra_flags, seen_empty))


def line_clear_py(model, start, end, extra_flags):
    if not model.nodes:
        return True
    seen_empty = [False]
    return seg_clear(model, 0, start, end, 0, extra_flags, seen_empty)


# ---- surface bake geometry (light.rs::bake_surf, position-walk half only) -----------------------


def surf_for_record(model, k):
    for si, s in enumerate(model.surfs):
        if s.i_light_map == k:
            return si, s
    return None, None


def row_origins(model, s, rec, bright_corners):
    """(u_dir, v_dir, base, row_origin_at_v0u0, u_step, v_step) for one (surf, record)."""
    base = model.points[s.p_base]
    normal = model.vectors[s.v_normal]
    tu = model.vectors[s.v_texture_u]
    tv = model.vectors[s.v_texture_v]
    axes = lumel_axes_py(tu, tv, normal)
    if axes is None:
        return None
    u_dir, v_dir = axes
    pan_x, pan_y = rec.pan[0], rec.pan[1]
    row_origin = vadd(vadd(vadd(base, vscaled(normal, 4.0)), vscaled(u_dir, pan_x)), vscaled(v_dir, pan_y))
    if bright_corners:
        row_origin = vadd(vadd(row_origin, vscaled(v_dir, 0.25)), vscaled(u_dir, 0.25))
        step_u = bright_corners_step(rec.u_scale, rec.u_size)
        step_v = bright_corners_step(rec.v_scale, rec.v_size)
    else:
        step_u, step_v = rec.u_scale, rec.v_scale
    u_step = vscaled(u_dir, step_u)
    v_step = vscaled(v_dir, step_v)
    return row_origin, u_step, v_step


def lumel_position(row_origin, u_step, v_step, target_v, target_u):
    """Iteratively accumulate, exactly like the real per-lumel walk (not a fresh multiply -- the
    f32 rounding of repeated addition differs from a scaled multiply, per `light.rs`'s own doc
    comment on `lumel_axes`)."""
    p = row_origin
    for _ in range(target_v):
        p = vadd(p, v_step)
    for _ in range(target_u):
        p = vadd(p, u_step)
    return p


def bit_of(planebytes, row_bytes, v, u):
    byte = planebytes[v * row_bytes + (u // 8)]
    return (byte >> (u % 8)) & 1


def main() -> int:
    if len(sys.argv) < 5:
        print(__doc__)
        return 2
    native_path, golden_path = sys.argv[1], sys.argv[2]
    trunk_project, trunk_rel = sys.argv[3], sys.argv[4]
    limit = 30
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    repo = str(ROOT)
    upackage, umodel = _load(repo)
    npkg, nm = level_model(upackage, umodel, native_path)
    epkg, em = level_model(upackage, umodel, golden_path)
    nnames, enames = light_names(npkg, nm), light_names(epkg, em)
    nruns, eruns = runs(nm, nnames), runs(em, enames)

    # --- gather light locations/radii from the trunk (same source both native.dx and golden.dx were
    # built from, so their placed Location is the same value both sides raytraced against). ---
    import os
    os.environ.setdefault("UEDCLI_PROJECT", trunk_project)
    sys.path.insert(0, repo)
    from uedcli import config, trunk as trunk_mod
    from uedcli.classdefaults import ClassDefaults
    from uedcli.native.materialize import gather_lights
    from uedcli import packages
    sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
    from spike_classindex import class_index  # noqa: E402

    project = config.load_project(trunk_project)
    user_config = config.load_user_config()
    trunk_dir = Path(trunk_project) / trunk_rel if trunk_rel != "." else Path(trunk_project)
    level, _ranks = trunk_mod.read_level(trunk_dir)
    resolver = packages.schema_resolver(project, user_config)
    defaults = ClassDefaults(resolver)
    lights = {name: (loc, radius, special) for name, loc, radius, special in
               gather_lights(level, defaults=defaults)}
    print(f"[check] {len(lights)} participating lights in trunk")

    class LightInput:
        def __init__(self, loc, radius, special):
            self.location = tuple(f32(c) for c in loc)
            self.radius = radius
            self.special_lit = special

        def world_radius(self):
            return f32((f32(self.radius) + 1.0) * 25.0)

    common = min(len(nm.light_map), len(em.light_map))
    checked_records = 0
    total_mismatches = 0
    algo_agree_golden = algo_disagree_golden = 0
    algo_agree_native = algo_disagree_native = 0
    disagree_detail = []

    for k in range(common):
        a, b = nm.light_map[k], em.light_map[k]
        nr, er = nruns[k], eruns[k]
        if a.u_size != b.u_size or a.v_size != b.v_size or nr != er:
            continue
        if a.pan != b.pan or a.u_scale != b.u_scale or a.v_scale != b.v_scale:
            continue
        if nr == []:
            continue
        row_bytes = (a.u_size + 7) // 8
        pn = planes(nm, a, len(nr))
        pe = planes(em, b, len(er))
        if pn == pe:
            continue  # fully identical, not "bits-only"

        nsi, ns = surf_for_record(nm, k)
        esi, es = surf_for_record(em, k)
        if ns is None or es is None:
            continue
        checked_records += 1

        n_bright = bool(ns.poly_flags & PF_BRIGHT_CORNERS)
        e_bright = bool(es.poly_flags & PF_BRIGHT_CORNERS)
        n_geo = row_origins(nm, ns, a, n_bright)
        e_geo = row_origins(em, es, b, e_bright)
        if n_geo is None or e_geo is None:
            continue
        n_row_origin, n_ustep, n_vstep = n_geo
        e_row_origin, e_ustep, e_vstep = e_geo
        n_extra = VIS_BRIGHT_CORNERS if n_bright else VIS_EXTRA_FLAGS
        e_extra = VIS_BRIGHT_CORNERS if e_bright else VIS_EXTRA_FLAGS

        block = row_bytes * a.v_size
        for pos_in_run, lname in enumerate(nr):
            nblock = pn[pos_in_run * block:(pos_in_run + 1) * block]
            eblock = pe[pos_in_run * block:(pos_in_run + 1) * block]
            if nblock == eblock:
                continue
            li = lights.get(lname)
            if li is None:
                continue
            light = LightInput(*li)
            for v in range(a.v_size):
                for u in range(a.u_size):
                    nb = bit_of(nblock, row_bytes, v, u)
                    eb = bit_of(eblock, row_bytes, v, u)
                    if nb == eb:
                        continue
                    total_mismatches += 1
                    if total_mismatches > limit:
                        break

                    # --- test 1: python port on GOLDEN's own tree/inputs vs golden's real bit ---
                    p_golden = lumel_position(e_row_origin, e_ustep, e_vstep, v, u)
                    py_golden = line_clear_py(em, p_golden, light.location, e_extra)
                    golden_bit_from_py = 1 if py_golden else 0
                    if golden_bit_from_py == eb:
                        algo_agree_golden += 1
                    else:
                        algo_disagree_golden += 1

                    # --- self-consistency: python port on NATIVE's own tree/inputs vs native's real bit ---
                    p_native = lumel_position(n_row_origin, n_ustep, n_vstep, v, u)
                    py_native = line_clear_py(nm, p_native, light.location, n_extra)
                    native_bit_from_py = 1 if py_native else 0
                    if native_bit_from_py == nb:
                        algo_agree_native += 1
                    else:
                        algo_disagree_native += 1

                    if len(disagree_detail) < limit:
                        disagree_detail.append(dict(
                            record=k, light=lname, v=v, u=u,
                            native_bit=nb, golden_bit=eb,
                            py_on_golden_tree=golden_bit_from_py,
                            py_on_native_tree=native_bit_from_py,
                            p_golden=p_golden, p_native=p_native,
                            light_loc=light.location,
                        ))
                if total_mismatches > limit:
                    break
            if total_mismatches > limit:
                break
        if total_mismatches > limit:
            break

    print(f"\nchecked {checked_records} bits-only records, {total_mismatches} individual "
          f"mismatching lumel bits examined (limit {limit})")
    print(f"\nself-consistency (python port vs REAL native bit, on native's own tree/inputs):")
    print(f"  agree {algo_agree_native}  disagree {algo_disagree_native}"
          + ("  <-- python port has a bug, stop here" if algo_disagree_native else "  -- port verified faithful"))
    print(f"\nalgorithm test (python port vs REAL editor bit, on the EDITOR's own real tree/inputs):")
    print(f"  agree {algo_agree_golden}  disagree {algo_disagree_golden}")
    if algo_disagree_golden == 0 and algo_disagree_native == 0:
        print("\n==> line_clear reproduces the editor's real per-lumel decision EXACTLY when given "
              "the editor's real tree. NOT a line_clear bug -- the bit divergence is downstream of "
              "native's own (structurally-exact but not float-identical) BSP tree, i.e. the tracked "
              "Points/geometry residual, not a new algorithm defect.")
    elif algo_disagree_native:
        print("\n==> WARNING: the python port disagrees with native's OWN real output on native's OWN "
              "tree -- the port itself has a bug; the golden-tree test above is not yet trustworthy.")
    else:
        print(f"\n==> line_clear DISAGREES with the editor's real bit {algo_disagree_golden} time(s) "
              "even when given the editor's own real tree and real ray endpoints -- a genuine "
              "algorithm bug, not a geometry residual. See detail below.")

    if disagree_detail:
        print("\nfirst mismatches (detail):")
        for d in disagree_detail[:limit]:
            print(f"  rec={d['record']} light={d['light']} v={d['v']} u={d['u']} "
                  f"native_bit={d['native_bit']} golden_bit={d['golden_bit']} "
                  f"py(golden_tree)={d['py_on_golden_tree']} py(native_tree)={d['py_on_native_tree']}")
            print(f"      p_golden={d['p_golden']} p_native={d['p_native']} light_loc={d['light_loc']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
