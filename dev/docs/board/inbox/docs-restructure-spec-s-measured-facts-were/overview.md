+++
priority = "p1"
kind = "chore"
summary = "Docs restructure: spec's measured facts were wrong — corrected"
+++

# Docs restructure: spec's measured facts were wrong — corrected

`direction.md`
citers 10 → **45** (incl. 5 `.py`); `decisions.md` citers 120 → **171** (45 `.py`, 3 `.sh`,
`pyproject.toml`); ledger entries 229 → **227** (`## Format` + a template heading inside a fenced
code block). The spec's C1 verification used the same naive `^## ` matcher that produced the bad
count, so a splitter built to it would split inside the fence and self-certify green. Any redo
must anchor on `^## \d{4}-\d{2}-\d{2}`, be fence-aware, and assert the format block survives.
