+++
priority = "p2"
kind = "debug"
summary = "Superseded, folded into `native-light-apply-bake-where-it-stands-and`. SHIPPED (commit `9827f07`, the threaded-state `line_clear` port) and re-verified clean through round 10 (the 203-case apparent regression traced to a measurement artifact, not a real defect). Full 10-round writeup retained in git history and `dev/docs/native-materialize-findings.md`; status folded into `native-light-apply-bake-where-it-stands-and`."
+++

# line_clear shadow-ray algorithm gap: found real editor function, not fully decoded

Superseded, folded into `native-light-apply-bake-where-it-stands-and`.

SHIPPED (commit `9827f07`, the threaded-state `line_clear` port) and re-verified clean through round 10 (the 203-case apparent regression traced to a measurement artifact, not a real defect). Full 10-round writeup retained in git history and `dev/docs/native-materialize-findings.md`; status folded into `native-light-apply-bake-where-it-stands-and`.

**Round 11 (2026-08-31, after this item's retirement): INCONCLUSIVE, not a reopening.** Attempted to
audit whether round 8's own 262/262 ship-decision evidence has the same golden-tree-timing artifact
round 10 found in the opposite direction. Built real offline tooling
(`round11_fixbucket_brightcorners_audit.py`, doesn't need docker/gdb) but never ran it to completion
-- stalled twice, concluded by the coordinating session after two nudges with no result either way.
This does not reopen the ship decision (round 10's evidence stands); it's a real, still-open
verification gap. Full detail: `dev/docs/native-materialize-findings.md`, search "Round 11".
