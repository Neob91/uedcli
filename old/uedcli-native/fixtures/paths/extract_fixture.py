#!/usr/bin/env python3
"""Extract a built map's path graph into the `cargo test` fixture format (`paths.rs` goldens).

    extract_fixture.py <map.dx> > <name>.txt

Roster = the `Actors` array filtered to NavigationPoint-family exports (holes skipped), nav index =
position in that roster. `spec` lines are `ReachSpecs` in array (= creation) order with `Start`/`End`
remapped to nav indices; `nav` lines carry the on-disk `Paths`/`upstreamPaths`/`PrunedPaths` (spec
indices) and `VisNoReachPaths` (nav indices), -1 = empty. Parsers: the spike's `retail_stats.py`.
"""
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[3] / "dev/docs/spikes/2026-09-05-pathing-build-re/harness"
sys.path.insert(0, str(HARNESS))
from retail_stats import export_fqcn, is_nav_class, load_package, parse_level, parse_nav  # noqa: E402


def main(path: str) -> None:
    pkg = load_package(path)
    refs, specs = parse_level(pkg)
    navs = {i + 1: parse_nav(pkg, i) for i in range(len(pkg.exports))
            if not export_fqcn(pkg, i).startswith("MyLevel.") and is_nav_class(export_fqcn(pkg, i))}
    roster = [r for r in refs if r in navs]
    idx = {r: n for n, r in enumerate(roster)}
    print(f"# {Path(path).name} navs {len(roster)} specs {len(specs)}")
    for n, r in enumerate(roster):
        nav = navs[r]
        arr = lambda d, m: " ".join(str(m(d.get(i, -1))) for i in range(16))  # noqa: E731
        vnr = arr(nav.visnoreach, lambda v: idx.get(v, -1) if v > 0 else -1)
        x, y, z = nav.loc
        print(f"nav {n} {nav.name} {nav.cls} loc {x!r} {y!r} {z!r} P {arr(nav.paths, int)} "
              f"U {arr(nav.upstream, int)} PR {arr(nav.pruned, int)} VNR {vnr}")
    for d, s, t, r, h, f, pr in specs:
        print(f"spec {d} {idx.get(s, -1)} {idx.get(t, -1)} {r} {h} {f} {pr}")


if __name__ == "__main__":
    main(sys.argv[1])
