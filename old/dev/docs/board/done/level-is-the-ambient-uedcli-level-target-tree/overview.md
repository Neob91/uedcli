+++
priority = "p1"
kind = "unknown"
summary = "Level is the ambient `$UEDCLI_LEVEL`; `--target`→`--tree`; drop `level select`"
+++

# Level is the ambient `$UEDCLI_LEVEL`; `--target`→`--tree`; drop `level select`

— BUILT
2026-07-20 (2-reviewer cold gates on BOTH the spec and the build; all findings resolved). Fixes the p1
CLI-probe finding (shared unlocked pointer → concurrent cross-writes): the machine-local
`.uedcli/current-level` pointer + `level select` verb are GONE, replaced by the per-process
`$UEDCLI_LEVEL` env (resolved via `level_select.resolve_level(env_level=…)`, precedence `--tree` >
env > clean exit-2 naming both set-methods). `--target KIND/NAME` renamed `--tree KIND/NAME`
everywhere and extended to `level materialize`/`preview` (level-kind only). A **mutating** verb
resolved from the env echoes `editing level 'X' (from $UEDCLI_LEVEL)` to stderr (at
`TrunkLevelSource.save`), the visibility guard against a stale export. Spec
`spec.md`; decisions 2026-07-20 21:30 UTC (supersedes 2026-07-05
19:07/19:28). Suite-wide test sweep (`test_tree_flag.py`, env-based `test_level_select.py`,
`set_selected`→`monkeypatch.setenv`). **Remnant:** the p2 `level delete/rename/clone` spec item
(to-spec) still references "retarget the selected pointer" — reword to `$UEDCLI_LEVEL` when specced.
