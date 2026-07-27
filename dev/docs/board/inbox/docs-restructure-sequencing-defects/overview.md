+++
priority = "p2"
kind = "chore"
summary = "Docs restructure: sequencing defects"
+++

# Docs restructure: sequencing defects

Ledger entries D1–D5 were scheduled
*last*, i.e. after the step that deletes a doc — if interrupted, the only record of why is an
ephemeral spec; they must land first. Step 6 also writes to `decisions.md`, which C1 has by then
replaced. Part A was expected to land a code-cli-conventions rules file citing `direction.md` before Part B
deletes it. And per `CLAUDE.md`, specced pipeline work needs a **plan round** — the spec went
spec-gate → build-gates with no plan doc.
