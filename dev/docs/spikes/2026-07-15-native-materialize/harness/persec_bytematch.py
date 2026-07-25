#!/usr/bin/env python3
"""Per-section POSITIONAL byte-match of two .dx level `UModel` bodies — the "compiled parity %".

`ground_truth_bytediff.py` reports two extremes: raw whole-body positional match (collapses to a
low number the moment the first section differs in LENGTH, because everything downstream shifts) and
"% of body in FULLY byte-identical sections" (a harsh all-or-nothing floor). Neither is the headline
number the native-parity work has tracked for the castle.

This tool computes the middle, useful metric: it ALIGNS the two bodies section-by-section (each
section walked independently, so a length difference in one section does NOT desync the next) and
counts positionally-matching bytes WITHIN each aligned section, weighting by the longer side. The
whole-body roll-up of that is the **"compiled parity %"** — e.g. the castle's long-standing ~58%
headline is exactly this number (native vs Test_Castle.dx = 58.07%; native vs the UED batch golden =
58.08% — see sections/90-castle-ued-rebaseline.md).

Usage:
  persec_bytematch.py <A.dx> <B.dx> [<label>]
Defaults to native-castle vs UED-golden and native-castle vs shipped when run with no args.
"""
import sys
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))

import ground_truth_bytediff as G  # noqa: E402


def per(a_path: str, b_path: str, label: str) -> float:
    ab, _, _ = G.load_model_body(a_path)
    bb, _, _ = G.load_model_body(b_path)
    asec, _ = G.walk_sections(ab)
    bsec, _ = G.walk_sections(bb)
    bmap = {s["name"]: s for s in bsec}
    tot = match = 0
    print(f"--- {label} : per-section POSITIONAL byte match ---")
    for s in asec:
        n = s["name"]
        e = bmap[n]
        a = ab[s["start"]:s["end"]]
        b = bb[e["start"]:e["end"]]
        m = sum(1 for i in range(min(len(a), len(b))) if a[i] == b[i])
        L = max(len(a), len(b))
        tot += L
        match += m
        print(f"  {n:<28} {m:>7}/{L:<7} {100.0*m/L if L else 100:6.1f}%")
    pct = 100.0 * match / tot if tot else 100.0
    print(f"  {'WHOLE-BODY weighted (compiled %)':<32} {match}/{tot}  {pct:.2f}%\n")
    return pct


def main() -> int:
    if len(sys.argv) >= 3:
        per(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "A vs B")
        return 0
    S = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch"
    per(f"{S}/gtruth/NativeCastle.dx", f"{S}/uedgolden/UEDGolden_castle_r1.dx", "native vs UED GOLDEN")
    per(f"{S}/gtruth/NativeCastle.dx", "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx",
        "native vs SHIPPED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
