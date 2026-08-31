#!/usr/bin/env python3
r"""Round 11: audit round 8's original "262/262 fixed" ship-decision evidence for the SAME
`NF_BrightCorners` golden-tree-timing artifact round 10 found on the regression side (203 cases,
`line-clear-shadow-ray-algorithm-gap-found-real` round 10).

Round 10 established the artifact mechanism precisely: the per-node `NF_BrightCorners` (0x10) bit
in `is_csg`'s near/far "unstripped" mask (`csg_nostrip` in `line_clear_v2_algorithm_check.py`) can
only ever change a ray's outcome when the RAY'S OWN SURFACE is itself `PF_BrightCorners`-flagged --
`extra_flags` (derived from the surface) is what gates whether bit 0x10 is even part of the AND mask
at all (`VIS_BRIGHT_CORNERS = NF_NOT_VIS_BLOCKING | NF_BRIGHT_CORNERS` vs plain `VIS_EXTRA_FLAGS`).
So this script's filter is exact, not a heuristic: a v1-wrong/v2-correct "fix" case can ONLY be a
candidate for the same artifact if `es.poly_flags & PF_BrightCorners`.

For any candidate found, walks the ray through golden's tree with `NF_BrightCorners` on every node
FORCED to 0 (round 10's live-confirmed proxy for "what the real editor's walker actually saw at cast
time" -- native's own model never sets this bit, and round 10 live-verified this matches the real
editor's at-cast-time NodeFlags exactly for its own 203-case population) and re-evaluates v1/v2 vs
golden's real bit under that forced-clear tree. If the fix still holds (v2 still correct), it's NOT
an artifact. If it evaporates (v2 becomes wrong, or the case stops distinguishing v1 from v2), it IS
a candidate for the same artifact and needs a live recheck (`linecheck_nearstate_recheck.py`-style)
to confirm.

Usage: round11_fixbucket_brightcorners_audit.py FIXBUCKET.jsonl GOLDEN.dx
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "2026-08-27-native-light-apply-parity/harness"))
from lightparity import _load, level_model  # noqa: E402
import line_clear_algorithm_check as v1mod  # noqa: E402
import line_clear_v2_algorithm_check as v2mod  # noqa: E402

ROOT = HERE.parents[4]
PF_BRIGHT_CORNERS = 0x00080000
NF_BRIGHT_CORNERS = 0x10


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    dump_path, golden_path = sys.argv[1], sys.argv[2]

    repo = str(ROOT)
    upackage, umodel = _load(repo)
    epkg, em = level_model(upackage, umodel, golden_path)

    cases = [json.loads(line) for line in Path(dump_path).read_text().splitlines() if line.strip()]
    print(f"[audit] {len(cases)} fix-bucket (v1-wrong/v2-correct) cases loaded from {dump_path}")

    candidates = []
    for c in cases:
        esi, es = v2mod.surf_for_record(em, c["record"])
        if es is None:
            continue
        e_bright = bool(es.poly_flags & PF_BRIGHT_CORNERS)
        if e_bright:
            candidates.append((c, esi, es))

    print(f"[audit] {len(candidates)}/{len(cases)} cases are on a PF_BrightCorners-flagged surface "
          f"(the ONLY population where NF_BrightCorners can affect the outcome at all -- see "
          f"docstring for why this filter is exact, not a heuristic)")

    if not candidates:
        print("[audit] RESULT: zero candidates -- round 8's fix bucket does not touch this "
              "mechanism at all. Clean negative result.")
        return 0

    # For any candidate, re-verify under a forced-NF_BrightCorners-clear golden tree (round 10's
    # live-confirmed at-cast-time proxy).
    orig_flags = {}
    for node in em.nodes:
        orig_flags[id(node)] = node.node_flags

    def clear_bright_corners():
        for node in em.nodes:
            node.node_flags &= ~NF_BRIGHT_CORNERS

    def restore_flags():
        for node in em.nodes:
            node.node_flags = orig_flags[id(node)]

    still_artifact = []
    clear_bright_corners()
    for c, esi, es in candidates:
        p = tuple(c["p"])
        loc = tuple(c["loc"])
        e_bright = True
        e_extra = v2mod.VIS_BRIGHT_CORNERS if e_bright else v2mod.VIS_EXTRA_FLAGS
        r1 = 1 if v1mod.line_clear_py(em, p, loc, e_extra) else 0
        r2 = 1 if v2mod.line_clear_v2(em, p, loc, e_extra) else 0
        eb = c["golden"]
        holds = (r2 == eb)
        print(f"  rec={c['record']} light={c['light']} v={c['v']} u={c['u']} golden={eb} "
              f"orig(v1={c['v1']},v2={c['v2']}) forced-clear(v1={r1},v2={r2}) "
              f"{'FIX HOLDS' if holds else 'FIX EVAPORATES -- ARTIFACT CANDIDATE'}")
        if not holds:
            still_artifact.append(c)
    restore_flags()

    print(f"\n[audit] SUMMARY: {len(candidates)} candidate cases (BrightCorners-flagged surface), "
          f"{len(candidates) - len(still_artifact)} still hold under forced-clear (real fixes), "
          f"{len(still_artifact)} evaporate (artifact candidates, need live recheck)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
