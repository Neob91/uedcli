+++
priority = "p2"
kind = "debug"
summary = "Several inbox items have kinds outside the vocab, so test_board.py is red"
+++

# Invalid board kinds fail test_board

`test_board.py:155` enforces `kind` ∈ `[chore, debug, docs, implement, owner-question, unknown]`.
Several `inbox/` items were filed with kinds outside that set, so the offline suite is red (surfaced
now that `bin/test` runs in the dev container — the failure pre-dates that change). Offenders and a
suggested valid kind:

- `deusex-boot-wedge-is-memory-pressure-deadlock` — `finding` → `unknown`
- `deusex-exe-game-preview-boot-blocked-by-forced` — `finding` → `unknown`
- `generic-base-driver-clean-cannot-hide-the` — `finding` → `unknown`
- `spike-fex-fextest-img-to-run-x86-deusex-exe-on` — `spike` → `unknown`
- `uedpreviewlink-header-wrongly-calls` — `bug` → `debug`
- `verify-hudhidecommands-config-var-resolves-from` — `verify` → `unknown`

Fix = correct each item's `kind` frontmatter (they belong to other sessions' spikes, so a triage
pass, not a blind rewrite). Then `bin/test` (full) goes green.
