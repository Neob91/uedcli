#!/usr/bin/env python3
"""WanChai N=201, world Model2 LightMap[354] (surf 616, Brush1164): find every light candidate
that passes the special_lit/backface/plane-distance gather filters (`light::bake`'s `gathered()`),
using native's OWN `UEDCLI_VISGATE_DUMP=1` light listing as the light-position source.

Usage: run native's build with UEDCLI_VISGATE_DUMP=1 (stderr) into a log, then:
    lm354_candidates.py <visgate_dump.log> <p_base_x,y,z> <v_normal_x,y,z>
"""
import re
import sys


def main() -> int:
    log_path, base_s, normal_s = sys.argv[1], sys.argv[2], sys.argv[3]
    base = tuple(float(x) for x in base_s.split(","))
    normal = tuple(float(x) for x in normal_s.split(","))

    def dot(a, b):
        return sum(x * y for x, y in zip(a, b))

    def sub(a, b):
        return tuple(x - y for x, y in zip(a, b))

    pat = re.compile(
        r"VISGATE_LIGHT li=(\d+) loc=\[([-\d.]+),([-\d.]+),([-\d.]+)\] radius=(\d+) special=(true|false)"
    )
    candidates = []
    with open(log_path) as f:
        for line in f:
            m = pat.match(line)
            if not m:
                continue
            li = int(m.group(1))
            loc = tuple(float(m.group(i)) for i in (2, 3, 4))
            radius = int(m.group(5))
            special = m.group(6) == "true"
            wr = (radius + 1) * 25.0
            pd = dot(sub(loc, base), normal)
            front = pd >= -1.0
            in_radius = abs(pd) <= wr
            if (not special) and front and in_radius:
                candidates.append((li, loc, pd, wr))
    print(f"{len(candidates)} candidates (special_lit match + front + plane-distance in radius):")
    for li, loc, pd, wr in candidates:
        print(f"  li={li} loc={loc} planedot={pd:.3f} wr={wr:.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
