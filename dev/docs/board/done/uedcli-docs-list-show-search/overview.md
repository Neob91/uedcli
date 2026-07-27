+++
priority = "p?"
kind = "unknown"
summary = "`uedcli docs list|show|search` — SHIPPED, with the packaging half deliberately deferred"
+++

# `uedcli docs list|show|search` — SHIPPED, with the packaging half deliberately deferred

(2026-07-26, was item 11 on `to-build.md`; spec `../specs/2026-07-24-docs-command.md`, which
doubled as the plan). uedcli now serves its own **user-facing** docs (`docs/usage.md` +
`docs/leveldesign/**`) from the CLI, so a shipped Claude skill routes a user to a page by
querying the tool and carries zero doc copies. `show` resolves through the enumerated served set
rather than a path join (traversal and developer-tree leakage die structurally); a `README.md`
folds to its directory topic and the root one to `index`; a duplicate topic key is a hard error
naming both files; every failure is a clean exit 2 via the existing `_SelectionExit`. New module
`uedcli/userdocs.py`, 58 tests in `uedcli/tests/test_docs_command.py`. Durable write-ups:
`../architecture.md` "Commands (namespaced)" and `../rationale/userdocs.md`.
**Built in the `docs-command` worktree; the build gate ran two rounds (6 findings, then 12), all
fixed** — the round-2 set included an unreadable directory reading back as an empty one
(`pathlib`'s glob swallows `scandir`'s `OSError`), a missing UTF-8 BOM strip on `docs show -`,
and two user-doc claims that overstated the search ranking.
**REMNANTS, both filed separately on `inbox.md` rather than covered by this entry:** (1) the
wheel/Nuitka `uedcli/_docs` bundle — generation, `.gitignore`, `package-data`, the Nuitka
`--include-data-dir`, the drift guard — so an installed build ships with no docs today and every
`docs` verb exits 2 there; (2) two `[OWNER — confirm]` items carrying proposed `direction/`
wording for the decisions that are his (the product intent, and the duplicate-key hard error),
which currently live only in the agent-owned `rationale/`.
