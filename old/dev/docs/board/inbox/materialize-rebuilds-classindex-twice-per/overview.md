+++
priority = "p2"
kind = "implement"
summary = "materialize rebuilds ClassIndex twice per invocation"
+++

# materialize rebuilds ClassIndex twice per invocation

`run_materialize` (`uedcli/apply.py`) builds `verify_index = ClassIndex.from_files(host_search_dirs)`
(~line 497) for post-verify, then calls `_materialize_native(..., index=verify_index, ...)`, which
calls `_assembly_level(result, materialized_order, pkg_dirs)` (~line 374). `_assembly_level` builds
its own independent `ClassIndex.from_files(pkg_dirs)` (~line 125) over the same directories instead
of taking the already-built `verify_index`. Each `ClassIndex.from_files` decodes discovery schema for
every `.u` on the composed search path.

`level materialize` is the single hottest command in the repo right now: `ladder_run.py`
(`NATIVE-MATERIALIZE.md`) calls it thousands of times across the active parity campaign. Cutting one
of two `ClassIndex` builds per call is a direct win on that loop.

Fix: thread `verify_index` into `_assembly_level` as an optional `index` param (build only if
`None`), mirroring what `_path_pass` already does around line 295-297.

Related: `speed-up-the-offline-test-suite` (to-spec) parked a question on splitting
`schema_cache.py`'s disk-cache/in-process-memo switch — that fix would compound this one, since a
short-lived `ClassIndex` here gets no benefit from the in-process memo while
`UEDCLI_SCHEMA_CACHE=off`.

Found by: 2026-09-12 performance audit (subagent-driven, CLI/package-I/O scope).
