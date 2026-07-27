+++
priority = "p?"
kind = "unknown"
summary = "The `--run` seed had no source under \"`--run` orders the chain itself\""
+++

# The `--run` seed had no source under "`--run` orders the chain itself"

Raised independently by all three round-1 spec reviewers. Resolved by the owner: the order faces are
passed in has NO bearing on the result — a PRE-WALK derives the root too (the lower-poly-index end of
an open run; the lowest index on a closed run), which is stronger than the reviewers' proposed
"root = first input token". The pre-walk also detects branching. No `--seam` flag. Folded into
`specs/2026-07-26-poly-surface-verbs.md` **§2.4.1** (the eight-step pre-walk); nothing outstanding.
This entry is the *resolution record* — the ruling's own proposed text is parked verbatim in the
`[OWNER — confirm]` item above.
