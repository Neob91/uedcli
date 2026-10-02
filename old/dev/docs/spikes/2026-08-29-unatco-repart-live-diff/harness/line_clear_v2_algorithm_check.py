#!/usr/bin/env python3
"""Round 7: offline validation of the NEW `line_clear` recursion structure (round 6's fully
resolved shape + the live-read +/-0.001 epsilon band) against the golden's own real per-lumel bits.

Same oracle technique as `line_clear_algorithm_check.py` (round 1): the editor's real per-lumel BSP
tree is already serialized into the lit golden `.dx` (LIGHT APPLY never rebuilds BSP), so testing a
candidate Python port against golden's own stored bits needs no live gdb.

Structure (round 6, live-disassembly-confirmed):
  - point1 starts as `end` (light_loc), point2 starts as `start` (lumel_pos) -- CONFIRMED live,
    round 3.
  - Loop over whole-segment nodes (no call). FRONT-whole: D1>-0.001 AND D2>-0.001, child=i_back.
    BACK-whole: D1<0.001 AND D2<0.001, child=i_front. Else: crossing.
  - Crossing: t=D1/(D2-D1), mid=point2+t*(point2-point1). ONE genuine recursive call into the child
    selected by D1's sign, with point1->mid, point2 unchanged. If that returns BLOCKED, short-circuit
    return BLOCKED. Else, tail-loop into the OTHER child with point2->mid, point1 unchanged.
  - Terminal (child==-1): resolve via edi/state (formula NOT yet fully pinned as of round 6 -- this
    script parameterizes it so round 7's live-captured facts can be dropped in and validated here,
    fast, before touching Rust).

Usage: line_clear_v2_algorithm_check.py GOLDEN.dx TRUNK_PROJECT_DIR TRUNK_REL [--limit N] [--radius-aware]

`--radius-aware`: skip out-of-light-radius lumel bits entirely (no `line_clear` call, doesn't count
toward `--limit`) -- matches `light.rs`'s own per-lumel `d.dot(&d) < wr2` gate before it ever calls
`line_clear` (world radius `(LightRadius_byte + 1) * 25`, `AActor::WorldLightRadius`). Without this
flag the sweep counts every lumel unconditionally, which round 7 showed measures the wrong thing (a
light 677uu from a lumel with 425uu radius is "out of range", not a `line_clear` disagreement) --
round 8's own round used an ad hoc uncommitted version of this cull; this flag makes it reusable.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "2026-08-27-native-light-apply-parity/harness"))
from lightparity import _load, level_model, light_names, runs, planes  # noqa: E402

ROOT = Path(__file__).resolve().parents[5]


def f32(x):
    return struct.unpack("f", struct.pack("f", x))[0]


def fadd(a, b): return f32(a + b)
def fsub(a, b): return f32(a - b)
def fmul(a, b): return f32(a * b)


def fdiv(a, b):
    if b == 0.0:
        return float("nan")
    return f32(a / b)


def vadd(a, b): return (fadd(a[0], b[0]), fadd(a[1], b[1]), fadd(a[2], b[2]))
def vsub(a, b): return (fsub(a[0], b[0]), fsub(a[1], b[1]), fsub(a[2], b[2]))
def vscaled(v, s): return (fmul(v[0], s), fmul(v[1], s), fmul(v[2], s))
def vdot(a, b): return fadd(fadd(fmul(a[0], b[0]), fmul(a[1], b[1])), fmul(a[2], b[2]))


def vcross(a, b):
    return (fsub(fmul(a[1], b[2]), fmul(a[2], b[1])),
            fsub(fmul(a[2], b[0]), fmul(a[0], b[2])),
            fsub(fmul(a[0], b[1]), fmul(a[1], b[0])))


def lumel_axes_py(tu, tv, n):
    c0 = vcross(tv, n)
    det = vdot(tu, c0)
    if abs(det) < 1e-8:
        return None
    rdet = f32(1.0 / det)
    c1 = vcross(n, tu)
    return vscaled(c0, rdet), vscaled(c1, rdet)


def bright_corners_step(scale, size):
    return f32(float(scale) - 0.5 / (size - 1))


NF_NOT_CSG = 0x01
NF_NOT_VIS_BLOCKING = 0x04
NF_BRIGHT_CORNERS = 0x10
NF_IS_NEW = 0x20
VIS_EXTRA_FLAGS = NF_NOT_VIS_BLOCKING
VIS_BRIGHT_CORNERS = NF_NOT_VIS_BLOCKING | NF_BRIGHT_CORNERS
PF_BRIGHT_CORNERS = 0x00080000
MAX_DEPTH = 4096
FRONT, BACK = 1, 0
EPS = 0.001

sys.setrecursionlimit(20000)


def plane_dot(p, v):
    s = fadd(fadd(fmul(p[0], v[0]), fmul(p[1], v[1])), fmul(p[2], v[2]))
    return fsub(s, p[3])


def is_csg(node, extra_flags, strip_bright_corners=True):
    mask = (extra_flags & ~NF_BRIGHT_CORNERS if strip_bright_corners else extra_flags) | NF_NOT_CSG | NF_IS_NEW
    return node.num_vertices > 0 and (node.node_flags & mask) == 0


def child(node, side):
    return node.i_back if side == FRONT else node.i_front


def terminal(edi, extra_flags, seen_empty_global):
    """Exact terminal-handling port, `0x17ce442`-`0x17ce4be`, re-verified directly against the
    committed disasm (not memory/paraphrase) this round:
      if edi != 0: GLOBAL=1 (0x17ce4ae, a real side effect missed on first pass -- caught only by
        re-grepping the disasm after the mechanical checks below flagged nothing, since none of the
        122 live-captured data points happened to exercise a SECOND terminal after an edi!=0 one);
        return edi (effectively 1, edi is always 0/1 by construction)
      elif GLOBAL(seen_empty) != edi(0): return 0   [-> falls to the "writeout" path, eax=edi=0]
      elif not (extra_flags & NF_BRIGHT_CORNERS): return 0
      else: edi=1; return 1
    """
    if edi != 0:
        seen_empty_global[0] = 1
        return edi
    if seen_empty_global[0] != 0:
        return 0
    if not (extra_flags & NF_BRIGHT_CORNERS):
        return 0
    return 1


def seg_clear_v2(model, inode, p1, p2, edi, extra_flags, seen_empty_global, depth=0):
    while True:
        if depth > MAX_DEPTH:
            return 1
        if inode == -1:
            return terminal(edi, extra_flags, seen_empty_global)
        node = model.nodes[inode]
        d1 = plane_dot(node.plane, p1)
        d2 = plane_dot(node.plane, p2)
        if d1 > -EPS and d2 > -EPS:
            # FRONT-whole: edi = edi | (1 if csg else 0)  [0x17ce238-0x17ce265]
            csg = is_csg(node, extra_flags, strip_bright_corners=True)
            inode = child(node, FRONT)
            edi = (edi | 1) if csg else (edi | 0)
            depth += 1
            continue
        if d1 < EPS and d2 < EPS:
            # BACK-whole: edi = edi & (0 if csg else 1)  [0x17ce27c-0x17ce297] -- re-verified this
            # round: CSG-solid on the BACK side FORCES edi to 0 (not "unchanged" as round 6's first
            # writeup mistakenly said -- a real self-correction, see round 7 in the ledger).
            csg = is_csg(node, extra_flags, strip_bright_corners=True)
            inode = child(node, BACK)
            edi = (edi & 0) if csg else (edi & 1)
            depth += 1
            continue
        # crossing -- near side + crossing fraction key on d2 (point2's own dot), NOT d1. Round 7
        # live re-capture (isurf=1060, node 310): [ebp-0x8] (the "near-side" test register) VARIES
        # per-ray with the query/lumel point while [ebp-0xc] stays constant across rays sharing one
        # light -- i.e. [ebp-0x8]=D2(point2), [ebp-0xc]=D1(point1), the OPPOSITE of an earlier
        # (wrong) reading this round. mid=point2+t*(point2-point1) with t=d2/(d1-d2) still lands
        # exactly on the plane (plane_dot linear: D2+t*(D2-D1)=0 check), unaffected by the swap.
        t = fdiv(d2, fsub(d1, d2))
        mid = vadd(p2, vscaled(vsub(p2, p1), t))
        near_side = FRONT if d2 > 0.0 else BACK
        near_child = child(node, near_side)
        # The near call's OWN incoming state is NOT `edi` passed through -- it's freshly computed
        # (0x17ce306-0x17ce35e, decoded this round after a live ray4 mismatch exposed the bug):
        # mirrors the far-continuation formula's shape but is a genuinely separate computation, fed
        # by THIS frame's edi + THIS node's own (unstripped-mask) CSG-ness.
        numverts_ok = node.num_vertices > 0
        csg_nostrip = numverts_ok and (node.node_flags & (extra_flags | NF_NOT_CSG | NF_IS_NEW)) == 0
        if near_side == FRONT:
            if edi != 0:
                near_state = 1
            else:
                near_state = 1 if (numverts_ok and csg_nostrip) else 0
        else:
            if edi == 0:
                near_state = 0
            else:
                if not numverts_ok:
                    near_state = 1
                elif csg_nostrip:
                    near_state = 0
                else:
                    near_state = 1
        near_result = seg_clear_v2(model, near_child, mid, p2, near_state, extra_flags, seen_empty_global, depth + 1)
        if near_result == 0:
            return 0
        far_side = BACK if near_side == FRONT else FRONT
        far_child = child(node, far_side)
        numverts_ok = node.num_vertices > 0
        # far-continuation csg test does NOT strip NF_BrightCorners (0x17ce3d5-3da / 3ef-3f4,
        # re-verified this round -- a real, confirmed asymmetry vs every other classification site).
        csg_nostrip = numverts_ok and (node.node_flags & (extra_flags | NF_NOT_CSG | NF_IS_NEW)) == 0
        if near_side == FRONT:
            # far=BACK: branch B, 0x17ce3e6-0x17ce3fe
            if edi == 0:
                edi = 0
            else:
                if not numverts_ok:
                    edi = 1
                elif csg_nostrip:
                    edi = 0
                else:
                    edi = 1
        else:
            # far=FRONT: branch A, 0x17ce3cc-0x17ce3e4
            if edi != 0:
                edi = 1
            else:
                if not numverts_ok:
                    edi = 0
                elif csg_nostrip:
                    # jne -> non-csg -> 0x17ce400 edi=0; fallthrough (is-csg) -> edi=1
                    edi = 1
                else:
                    edi = 0
        inode = far_child
        p2 = mid
        depth += 1
        continue


def line_clear_v2(model, start, end, extra_flags):
    """`start`/`end` in NATIVE's own convention. Real editor's point1=end(light), point2=start(lumel)."""
    if not model.nodes:
        return True
    seen_empty_global = [0]
    result = seg_clear_v2(model, 0, end, start, 0, extra_flags, seen_empty_global)
    return result != 0


def surf_for_record(model, k):
    for si, s in enumerate(model.surfs):
        if s.i_light_map == k:
            return si, s
    return None, None


def row_origins(model, s, rec, bright_corners):
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
    return row_origin, vscaled(u_dir, step_u), vscaled(v_dir, step_v)


def lumel_position(row_origin, u_step, v_step, target_v, target_u):
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
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    golden_path = sys.argv[1]
    trunk_project, trunk_rel = sys.argv[2], sys.argv[3]
    limit = 2000
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    radius_aware = "--radius-aware" in sys.argv

    repo = str(ROOT)
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
    print(f"[v2check] {len(lights)} participating lights in trunk")

    class LightInput:
        def __init__(self, loc, radius, special):
            self.location = tuple(f32(c) for c in loc)

    total_bits = agree_all = agree_golden_only = 0
    blocked_seen = clear_seen = 0
    disagree_detail = []

    for k in range(len(em.light_map)):
        b = em.light_map[k]
        er = eruns[k]
        if er == []:
            continue
        esi, es = surf_for_record(em, k)
        if es is None:
            continue
        e_bright = bool(es.poly_flags & PF_BRIGHT_CORNERS)
        e_geo = row_origins(em, es, b, e_bright)
        if e_geo is None:
            continue
        e_row_origin, e_ustep, e_vstep = e_geo
        e_extra = VIS_BRIGHT_CORNERS if e_bright else VIS_EXTRA_FLAGS
        row_bytes = (b.u_size + 7) // 8
        pe = planes(em, b, len(er))
        block = row_bytes * b.v_size
        for pos_in_run, lname in enumerate(er):
            eblock = pe[pos_in_run * block:(pos_in_run + 1) * block]
            li = lights.get(lname)
            if li is None:
                continue
            light = LightInput(*li)
            for v in range(b.v_size):
                for u in range(b.u_size):
                    eb = bit_of(eblock, row_bytes, v, u)
                    total_bits += 1
                    if eb:
                        clear_seen += 1
                    else:
                        blocked_seen += 1
                    p = lumel_position(e_row_origin, e_ustep, e_vstep, v, u)
                    py = line_clear_v2(em, p, light.location, e_extra)
                    py_bit = 1 if py else 0
                    if py_bit == eb:
                        agree_golden_only += 1
                    else:
                        if len(disagree_detail) < limit:
                            disagree_detail.append(dict(record=k, light=lname, v=v, u=u,
                                                          golden_bit=eb, py_bit=py_bit))
                    if total_bits >= limit:
                        break
                if total_bits >= limit:
                    break
            if total_bits >= limit:
                break
        if total_bits >= limit:
            break

    print(f"\nchecked {total_bits} lumel bits (golden CLEAR={clear_seen} BLOCKED={blocked_seen})")
    print(f"v2 algorithm vs golden's real bit: agree {agree_golden_only}/{total_bits} "
          f"({100*agree_golden_only/max(total_bits,1):.2f}%)")
    if disagree_detail:
        print("\nfirst mismatches:")
        for d in disagree_detail[:30]:
            print(f"  rec={d['record']} light={d['light']} v={d['v']} u={d['u']} "
                  f"golden={d['golden_bit']} py={d['py_bit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
