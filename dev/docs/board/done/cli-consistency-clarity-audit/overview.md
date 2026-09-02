+++
priority = "p?"
kind = "unknown"
summary = "CLI consistency & clarity audit (unattended build #12, report-only)"
+++

# CLI consistency & clarity audit (unattended build #12, report-only)

— DELIVERED 2026-07-19.
Report `dev/docs/reviews/2026-07-19-cli-consistency-audit.md` (full verb inventory + 8 findings,
2 high / 3 medium / 3 low, each verified against `cli.py`/`dispatch.py`). NO behaviour changed.
Top: [H1] `brush poly set` lacks `-`/stdin (breaks the `poly find | poly set` pipe its own help
advertises); [H2] `actor move` is single-actor-only while `rotate`/`scale` take a set + `-`; [M1]
mutator summary destination inconsistent (some → stdout, rubric says stderr); [M2] `brush vertex
list`/`actor prop get`/`mover key list` lack `--json`; [M3] `brush build` has no `--prop` though
`actor build` does. Accepted fixes are filed as NEW inbox items (below) for Andrzej to triage —
this item shipped only the review. Completes the 2026-07-18 unattended build queue (items 1-12).
