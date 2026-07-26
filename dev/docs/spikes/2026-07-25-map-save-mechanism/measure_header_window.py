#!/usr/bin/env python3
"""Measure the BLIND WINDOW of `driver.package_header_problem` over every real package on the
composed search path — i.e. how late a truncation can happen and still pass the header check.

For each package: the header declares, per object table, a (count, offset) pair. The check requires
every offset to lie inside the file AND each table to have room for `count` entries at their minimum
encoded size. `required_end / size` is therefore the fraction of the file the check can vouch for;
`1 - that` is the blind tail. Reported against the weaker offsets-only rule for comparison.

Run:  python3 measure_header_window.py         (from Tools/uedcli, with a project + games config)

Feeds the numbers quoted in `driver.package_header_problem`, `architecture.md` "Editor driver" and
`decisions.md` 2026-07-25 11:31 UTC. Re-run it before re-quoting them.
"""
import os
import statistics
import struct
import sys
from collections import Counter

sys.path.insert(0, os.getcwd())

from uedcli import config, driver                                          # noqa: E402

# Must mirror driver.package_header_problem's table order + per-entry minimums.
PER_ENTRY = {"name": 5, "export": 12, "import": 7}


def main() -> int:
    project = config.resolve_project(env_project=os.environ.get("UEDCLI_PROJECT"), cwd=os.getcwd())
    user_config = config.load_user_config()
    if user_config is None:
        raise SystemExit("no ~/.uedcli/config.toml — cannot resolve the composed search path")

    rows = []
    for path, _prov in config.composed_search_files(project, user_config):
        try:
            blob = open(path, "rb").read()
        except OSError:
            continue
        if len(blob) < driver.PKG_HEADER_BYTES:
            continue
        magic, ver, _flags, nc, no, ec, eo, ic, io = struct.unpack_from("<9I", blob, 0)
        if magic != driver.PKG_MAGIC:
            continue
        size = len(blob)
        required = max(no + PER_ENTRY["name"] * nc,
                       eo + PER_ENTRY["export"] * ec,
                       io + PER_ENTRY["import"] * ic)
        offsets_only = max(no, eo, io) + 1
        rows.append((os.path.splitext(path)[1].lower(), required / size, offsets_only / size,
                     size - required, ver & 0xFFFF, os.path.basename(path)))
        assert driver.package_header_problem(blob[:driver.PKG_HEADER_BYTES], size) is None, path

    print(f"{len(rows)} packages on the composed path: "
          f"{dict(Counter(r[0] for r in rows))}")
    print(f"package versions: {dict(Counter(r[4] for r in rows))}")
    for ext in sorted({r[0] for r in rows}):
        g = [r for r in rows if r[0] == ext]
        print(f"  {ext:5s} n={len(g):3d}  room rule {min(r[1] for r in g):.3%}–"
              f"{max(r[1] for r in g):.3%} (median {statistics.median(r[1] for r in g):.3%})"
              f"   offsets-only {min(r[2] for r in g):.3%}–{max(r[2] for r in g):.3%} "
              f"(median {statistics.median(r[2] for r in g):.3%})")
    tightest = sorted(rows, key=lambda r: r[3])[:3]
    print("tightest slack (bytes between the required end and EOF — the safety margin of the "
          "per-entry minimums):")
    for r in tightest:
        print(f"   {r[3]:6d}  {r[5]}")
    print("every package passes package_header_problem: yes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
