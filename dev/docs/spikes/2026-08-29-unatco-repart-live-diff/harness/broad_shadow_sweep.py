#!/usr/bin/env python3
r"""Round 9: complete/extend round 8's radius-aware broad shadow-bit sweep (its own named next
step 2) -- v1 (`line_clear_py`, pre-round-8) vs v2 (`line_clear_v2`, shipped `9827f07`) vs the
golden's real stored bit, over ALL in-range lumel bits of a level (not the narrower real-mismatch
bucket `line-clear-shadow-ray-algorithm-gap-found-real` round 8 already covered 262/262 on).

Radius-aware: skip a lumel bit entirely (no algorithm call, doesn't count) when it is out of the
light's world radius -- mirrors `light.rs::bake_surf`'s own `d.dot(&d) < wr2` gate before it ever
calls `line_clear`. Round 7's original broad sweep skipped this and mismeasured (a 677uu lumel vs a
425uu-radius light read as a `line_clear` disagreement when it was just out of range).

Reuses the two existing single-purpose ports as libraries (`line_clear_algorithm_check.py`'s
`line_clear_py` = v1, `line_clear_v2_algorithm_check.py`'s `line_clear_v2` = v2) rather than a third
copy of the state machine -- both already f32-round every op and are independently verified against
golden/native self-consistency in their own rounds.

Usage: broad_shadow_sweep.py GOLDEN.dx TRUNK_PROJECT_DIR TRUNK_REL [--target N] [--timeout SECONDS]
  [--dump-v1-only PATH]
  e.g. broad_shadow_sweep.py _scratch/wanchai-relight-2026-08-29/golden.dx dev/games .

Round 10: added `--dump-v1-only PATH` -- writes EVERY v1-only-correct (v1 right, v2 wrong) case as
one JSON line to PATH, not just the first-20 printed sample the original script capped at.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "2026-08-27-native-light-apply-parity/harness"))
from lightparity import _load, level_model, light_names, runs, planes  # noqa: E402
import line_clear_algorithm_check as v1mod  # noqa: E402
import line_clear_v2_algorithm_check as v2mod  # noqa: E402

ROOT = HERE.parents[4]


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    golden_path, trunk_project, trunk_rel = sys.argv[1], sys.argv[2], sys.argv[3]
    target = 2_000_000
    if "--target" in sys.argv:
        target = int(sys.argv[sys.argv.index("--target") + 1])
    timeout_s = None
    if "--timeout" in sys.argv:
        timeout_s = float(sys.argv[sys.argv.index("--timeout") + 1])
    dump_path = None
    if "--dump-v1-only" in sys.argv:
        dump_path = Path(sys.argv[sys.argv.index("--dump-v1-only") + 1])
        dump_f = dump_path.open("w")
    else:
        dump_f = None

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
    print(f"[broadsweep] {len(lights)} participating lights; target={target} in-range bits", flush=True)

    def world_radius(radius_byte: int) -> float:
        return (radius_byte + 1) * 25.0

    checked = v1_agree = v2_agree = both_agree = 0
    v1_only_correct = v2_only_correct = 0
    v1v2_disagree_examples = []
    start_t = time.monotonic()
    stopped_early = False

    for k in range(len(em.light_map)):
        b = em.light_map[k]
        er = eruns[k]
        if er == []:
            continue
        esi, es = v2mod.surf_for_record(em, k)
        if es is None:
            continue
        e_bright = bool(es.poly_flags & v2mod.PF_BRIGHT_CORNERS)
        e_geo = v2mod.row_origins(em, es, b, e_bright)
        if e_geo is None:
            continue
        e_row_origin, e_ustep, e_vstep = e_geo
        e_extra = v2mod.VIS_BRIGHT_CORNERS if e_bright else v2mod.VIS_EXTRA_FLAGS
        row_bytes = (b.u_size + 7) // 8
        pe = planes(em, b, len(er))
        block = row_bytes * b.v_size
        for pos_in_run, lname in enumerate(er):
            eblock = pe[pos_in_run * block:(pos_in_run + 1) * block]
            li = lights.get(lname)
            if li is None:
                continue
            loc, radius_byte, _special = li
            loc = tuple(v2mod.f32(c) for c in loc)
            wr2 = world_radius(radius_byte) ** 2
            for v in range(b.v_size):
                for u in range(b.u_size):
                    eb = v2mod.bit_of(eblock, row_bytes, v, u)
                    p = v2mod.lumel_position(e_row_origin, e_ustep, e_vstep, v, u)
                    dx, dy, dz = p[0] - loc[0], p[1] - loc[1], p[2] - loc[2]
                    if dx * dx + dy * dy + dz * dz >= wr2:
                        continue  # out of radius -- light.rs never calls line_clear for this bit
                    checked += 1
                    r1 = 1 if v1mod.line_clear_py(em, p, loc, e_extra) else 0
                    r2 = 1 if v2mod.line_clear_v2(em, p, loc, e_extra) else 0
                    if r1 == eb:
                        v1_agree += 1
                    if r2 == eb:
                        v2_agree += 1
                    if r1 == r2:
                        both_agree += 1
                    else:
                        if r1 == eb and r2 != eb:
                            v1_only_correct += 1
                            if dump_f is not None:
                                dump_f.write(json.dumps(
                                    dict(record=k, light=lname, v=v, u=u, golden=eb, v1=r1, v2=r2,
                                         p=list(p), loc=list(loc))) + "\n")
                                dump_f.flush()
                        if r2 == eb and r1 != eb:
                            v2_only_correct += 1
                        if len(v1v2_disagree_examples) < 20:
                            v1v2_disagree_examples.append(
                                dict(record=k, light=lname, v=v, u=u, golden=eb, v1=r1, v2=r2))
                    if checked % 100000 == 0:
                        elapsed = time.monotonic() - start_t
                        print(f"[broadsweep] {checked} checked ({elapsed:.0f}s) "
                              f"v1={v1_agree}/{checked} v2={v2_agree}/{checked} "
                              f"v1==v2 {both_agree}/{checked}", flush=True)
                    if checked >= target:
                        stopped_early = True
                        break
                    if timeout_s is not None and (time.monotonic() - start_t) > timeout_s:
                        stopped_early = True
                        break
                if checked >= target or stopped_early:
                    break
            if checked >= target or stopped_early:
                break
        if checked >= target or stopped_early:
            break

    if dump_f is not None:
        dump_f.close()
        print(f"[broadsweep] wrote {v1_only_correct} v1-only-correct cases to {dump_path}", flush=True)

    elapsed = time.monotonic() - start_t
    print(f"\n[broadsweep] DONE reason={'target/timeout' if stopped_early else 'exhausted level'} "
          f"checked={checked} elapsed={elapsed:.0f}s")
    print(f"  v1 vs golden: {v1_agree}/{checked} ({100*v1_agree/max(checked,1):.4f}%)")
    print(f"  v2 vs golden: {v2_agree}/{checked} ({100*v2_agree/max(checked,1):.4f}%)")
    print(f"  v1==v2 agreement: {both_agree}/{checked} ({100*both_agree/max(checked,1):.4f}%)")
    print(f"  v1-only-correct (v2 regression candidates): {v1_only_correct}")
    print(f"  v2-only-correct (v1 was wrong, v2 fixed): {v2_only_correct}")
    if v1v2_disagree_examples:
        print("\n  first v1/v2 disagreements:")
        for d in v1v2_disagree_examples:
            print(f"    {d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
