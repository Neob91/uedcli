+++
priority = "p3"
kind = "chore"
summary = "`brush stats` — per-map poly/vertex complexity histogram (2026-07-24)"
+++

# `brush stats` — per-map poly/vertex complexity histogram (2026-07-24)

Minor: aggregate
per-brush poly/vertex counts across a level (the complexity-budget number for the corpus study,
`specs/2026-07-24-corpus-brush-idioms.md` §7 gap 5). Scriptable today from `brush poly list` + `model.py`;
a dedicated verb is a nice-to-have, not a blocker. Consider folding into `brush identify` output.
