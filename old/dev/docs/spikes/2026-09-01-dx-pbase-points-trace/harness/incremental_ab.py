"""Offline structural A/B: UEDCLI_BSPCSG_INCREMENTAL_POINTS on vs off per level (no golden needed).

The flag must only permute Points (and thus p_base/i_vertex INDEX VALUES) — node/surf/leaf structure
and every non-point-index field must be identical, all point refs valid, both builds must succeed.
Round 13's UNATCO crash is exactly the failure mode this checks for.
"""
import os
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1] / "dev/docs/spikes/2026-08-31-native-parity-report/harness"
sys.path.insert(0, str(HARNESS))

import parity_compare as pc

TRUNK_ROOT = Path("/workspace/uedcli/.claude/worktrees/uedcli-parity-trunk-cache")
LEVELS = sys.argv[1].split(",")


def build(trunk, flag):
    if flag:
        os.environ["UEDCLI_BSPCSG_INCREMENTAL_POINTS"] = "1"
    else:
        os.environ.pop("UEDCLI_BSPCSG_INCREMENTAL_POINTS", None)
    try:
        model, _ = pc.build_native_model(trunk)
        return model, None
    except Exception as e:  # noqa: BLE001 — report, don't crash the sweep
        return None, f"{type(e).__name__}: {e}"


def node_key(n):
    return (n.plane, n.i_surf, n.i_front, n.i_back, n.i_plane, n.num_vertices, n.node_flags,
            getattr(n, "i_leaf", None), getattr(n, "i_zone", None))


def surf_key(s):
    d = dict(vars(s)) if hasattr(s, "__dict__") else {f: getattr(s, f) for f in s._fields}
    d.pop("p_base", None)
    return tuple(sorted(d.items()))


for lv in LEVELS:
    trunks = list(TRUNK_ROOT.glob(f"*/trunk/maps/{lv}"))
    if not trunks:
        print(f"{lv}: NO TRUNK")
        continue
    trunk = trunks[0]
    off, err_off = build(trunk, False)
    on, err_on = build(trunk, True)
    if err_off or err_on:
        print(f"{lv}: BUILD FAIL off={err_off} on={err_on}")
        continue
    probs = []
    if len(off.nodes) != len(on.nodes):
        probs.append(f"nodes {len(off.nodes)}!={len(on.nodes)}")
    else:
        for i, (a, b) in enumerate(zip(off.nodes, on.nodes)):
            if node_key(a) != node_key(b):
                probs.append(f"node[{i}] off={node_key(a)} on={node_key(b)}")
    if len(off.surfs) != len(on.surfs):
        probs.append(f"surfs {len(off.surfs)}!={len(on.surfs)}")
    else:
        bad = sum(1 for a, b in zip(off.surfs, on.surfs) if surf_key(a) != surf_key(b))
        if bad:
            probs.append(f"surf non-p_base fields differ at {bad} idx")
    if len(off.leaves) != len(on.leaves):
        probs.append(f"leaves {len(off.leaves)}!={len(on.leaves)}")
    if len(off.verts) != len(on.verts):
        probs.append(f"verts {len(off.verts)}!={len(on.verts)}")
    # ref validity on the flag-on build — categorize: a dangling p_base or LIVE-ring vert is fatal;
    # a dangling ORPHAN vert is the editor's own stale-orphan semantics (golden carries them too).
    np_on = len(on.points)
    live = [False] * len(on.verts)
    for n in on.nodes:
        for k in range(n.num_vertices):
            live[n.i_vert_pool + k] = True
    bad_pbase = sum(1 for s in on.surfs if not (0 <= s.p_base < np_on))
    bad_live = sum(1 for vi, v in enumerate(on.verts)
                   if live[vi] and not (0 <= v.i_vertex < np_on))
    stale_orphan = sum(1 for vi, v in enumerate(on.verts)
                       if not live[vi] and not (0 <= v.i_vertex < np_on))
    if bad_pbase or bad_live:
        probs.append(f"FATAL dangling: p_base={bad_pbase} live-ring={bad_live}")
    note = f" stale-orphan-refs={stale_orphan}" if stale_orphan else ""
    pb_diff = sum(1 for a, b in zip(off.surfs, on.surfs) if a.p_base != b.p_base) \
        if len(off.surfs) == len(on.surfs) else -1
    status = "OK" if not probs else "PROBLEM: " + "; ".join(probs)
    print(f"{lv}: {status} | points off={len(off.points)} on={len(on.points)} "
          f"verts off={len(off.verts)} on={len(on.verts)} p_base idx-changed={pb_diff}{note}")
