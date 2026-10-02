+++
priority = "p?"
kind = "unknown"
summary = "`--target` coverage on the read verbs"
+++

# `--target` coverage on the read verbs

— BUILT 2026-07-19 (2-reviewer cold-gated). Added
`--target level|stash|prefab` to `actor show`, `level status`, `level doctor`, `event graph`, and
`stash capture` (naming the SOURCE) — the CLI-usability-probe race escape hatch. `actor build`
DELIBERATELY SKIPPED (Andrzej 2026-07-19: a generator reads no box; the race is on `actor add`).
Added uniform `display_name`/`kind` to the three `LevelSource` classes; rewrote `_level_status`
through the seam (kind-labelled header, git hint only for a trunk); capture rejects `--target` +
`--from-*`. Decision superseded by board item `level-is-the-ambient-uedcli-level-target-tree`;
architecture/usage reconciled; regressions
in `test_target_flag.py`. Commit `73d952536`.
