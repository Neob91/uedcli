+++
priority = "p1"
kind = "unknown"
summary = "ANDRZEJ — the two `CLAUDE.md` files now give contradictory review-gate rules, and the new uedcli policy block has no ledger entry"
+++

# ANDRZEJ — the two `CLAUDE.md` files now give contradictory review-gate rules, and the new uedcli policy block has no ledger entry

Three reviewers in one round independently flagged
this; escalating rather than editing your own convention files. (a) **Direct contradiction, both
auto-loaded:** `Tools/uedcli/CLAUDE.md` opens "**EVERY change gets reviewed — there is no
trivial-change exemption**" with a 2/3/4 reviewer ladder, while the repo-root `CLAUDE.md` still
says "For any **non-trivial** change … fan out **two** … (A trivial change — a typo, a one-line doc
tweak — doesn't need the gate; use judgement.)" and is not scoped to exclude uedcli. An agent
working in `Tools/uedcli` reads both and gets opposite instructions on the exemption AND on the
headcount. Suggest the repo file say a per-tool file may impose a stricter gate. (b) **Dangling
citation:** the tool file cites "in one 2026-07-25 round the two reviewers overlapped on only two
of eight findings … — see `decisions.md`, 2026-07-25", but no `decisions.md` entry records that
round or that statistic; the rounds are described in `board/done.md`. Repoint it. (c) **No decision
entry exists for the gate policy at all** — the headcount ladder, context-vs-priming, the
observability test, batching, and the feature-branch/squash-merge rule all landed only in a
convention file, against that file's own rule that choices + rejected alternatives go in the
append-only ledger. (2026-07-25, round-4 cold reviews.)
