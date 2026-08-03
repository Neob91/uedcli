+++
priority = "p3"
kind = "owner-question"
summary = "rationale/MIGRATION.md line 116 points at board/to-build/bsp-issue-detector/plan.md, now deleted"
+++

# MIGRATION.md cites the now-deleted bsp-issue-detector plan.md

`dev/docs/rationale/MIGRATION.md:116` maps an old ledger plan to its current home:

    | plans/2026-06-24-uedcli-bsp-detector-plan.md | still checked, as board/to-build/bsp-issue-detector/plan.md |

Building the materialize BSP checks (`done/bsp-issue-detector`) moved that item to `done/` and deleted
its `plan.md` (a done item is trimmed to a reference line). So that path no longer exists; the row is
stale.

`rationale/` needs owner approval to edit, so this is filed rather than fixed. Proposed change: repoint
the row to `board/done/bsp-issue-detector/` (or drop the "still checked" note). No test enforces this
citation today, so it is not breaking the suite.
