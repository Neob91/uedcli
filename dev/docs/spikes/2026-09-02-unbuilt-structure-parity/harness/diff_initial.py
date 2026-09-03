#!/usr/bin/env python3
"""Diff a saveorder_oracle.py dump's ACTUAL pre-sort orders against the generative
model's predicted initial orders, and localize where the model diverges.

Usage: diff_initial.py <dump> <traced.dx-or-golden.dx> <trunk-dir> <boot-dump>

<boot-dump> supplies the fixed editor-boot name/object prefix (the toysmall trace);
<dump> is the level's own trace being diffed.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))

from uedcli.upackage import load_package        # noqa: E402
import predict_tables as PT                     # noqa: E402
import predict_unatco as PU                     # noqa: E402


def parse_pre(dump: Path) -> tuple[list[tuple[str, int]], list[tuple[str, int, str, str]]]:
    """(NMAP_PRE [(text, count)], IMAP_PRE [(name, count, class, outer)])."""
    names, imps = [], []
    for line in dump.read_text().splitlines():
        p = line.split()
        if not p:
            continue
        if p[0] == "NMAP_PRE":
            names.append((" ".join(p[4:]), int(p[3])))     # name text may contain spaces
        elif p[0] == "IMAP_PRE":
            imps.append((p[6], int(p[5]), p[7], p[8]))
    return names, imps


def seq_divergence(label: str, pred: list[str], true: list[str], *, show: int = 25) -> None:
    if pred == true:
        print(f"{label}: IDENTICAL ({len(true)} entries)")
        return
    sp, st = set(pred), set(true)
    if sp != st:
        print(f"{label}: SET differs — model-only {sorted(sp - st)[:10]}, "
              f"trace-only {sorted(st - sp)[:10]}")
        pred = [x for x in pred if x in st]
        true = [x for x in true if x in sp]
    tpos = {x: i for i, x in enumerate(true)}
    # longest prefix match, then show the first divergent region
    k = 0
    while k < len(pred) and pred[k] == true[k]:
        k += 1
    print(f"{label}: {sum(1 for i in range(min(len(pred), len(true))) if pred[i] != true[i])}"
          f"/{len(true)} positions differ; first at {k}")
    for i in range(k, min(k + show, len(pred))):
        print(f"  pos {i}: pred={pred[i]:<40s} true={true[i]}")
    # elements far from their predicted position
    far = sorted(((abs(tpos[x] - i), i, tpos[x], x) for i, x in enumerate(pred)),
                 reverse=True)[:15]
    print("  largest displacements (|d|, pred_pos, true_pos, elem):")
    for d, i, j, x in far:
        if d:
            print(f"    {d:6d} {i:6d} {j:6d} {x}")


def main() -> int:
    dump, dx, trunkd, bootdump = Path(sys.argv[1]), sys.argv[2], sys.argv[3], Path(sys.argv[4])
    pkg = load_package(dx)
    tagged = set(pkg.names)
    true_names, true_imps = parse_pre(dump)

    # --- model initial names ---
    files = PU.load_order_files(trunkd)
    startup = PT.startup_names(bootdump)
    seen = set(startup)
    pkg_names = [n for n in PU.package_name_seq(files) if not (n in seen or seen.add(n))]
    from uedcli import trunk as tm
    from uedcli.emit import emit_map
    from uedcli.materialize import levelinfo_first_order
    lvl, _ = tm.read_level(Path(trunkd))
    cl = {n: lvl.actors[n].cls for n in lvl.order}
    hb = {n: lvl.actors[n].brush is not None for n in lvl.order}
    order = levelinfo_first_order(lvl.order, cl, hb)
    t3d = emit_map([lvl.actors[n] for n in order])
    events = [n for n in PU.t3d_name_events(t3d, PU.name_value_set(pkg), pkg)
              if n not in seen]
    pred_names = ([n for n in startup if n in tagged]
                  + [n for n in pkg_names if n in tagged]
                  + [n for n in events if n in tagged])
    seq_divergence("NAMES", pred_names, [t for t, _ in true_names])

    # --- model initial imports ---
    obj_dump = PT.startup_object_order(bootdump)
    load_seq = {p: i for i, p in enumerate(PU.package_object_seq(files))}
    idents = PU.golden_import_paths(pkg)
    keys = []
    for j, (path, name) in enumerate(idents):
        if path in load_seq:
            keys.append((1, load_seq[path]))
        elif name in obj_dump:
            keys.append((0, obj_dump[name]))
        else:
            keys.append((2, j))
    pred_imp = [idents[j][0] for j in sorted(range(len(idents)), key=lambda j: keys[j])]
    # trace identities: name + outer chain isn't dumped as a path; rebuild via golden match
    # (name, class, outer) triples are unique enough in practice; fall back to name.
    bypath = {}
    for j, (path, name) in enumerate(idents):
        cn = pkg.names[pkg.imports[j][1]]
        outer = pkg.imports[j][2]
        on = pkg.names[pkg.imports[-outer - 1][3]] if outer < 0 else "-"
        bypath.setdefault((name.lower(), cn.lower(), on.lower()), []).append(path)
    true_paths = []
    for name, _cnt, cn, on in true_imps:
        cand = bypath.get((name.lower(), cn.lower(), on.lower()))
        true_paths.append(cand[0] if cand and len(cand) == 1 else f"?{name}")
    seq_divergence("IMPORTS", pred_imp, true_paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
