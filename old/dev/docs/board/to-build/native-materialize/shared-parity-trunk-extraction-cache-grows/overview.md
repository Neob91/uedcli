+++
priority = "p3"
kind = "debug"
summary = "Shared parity trunk-extraction cache grows unbounded, no pruning policy"
+++

# Shared parity trunk-extraction cache grows unbounded, no pruning policy

Found building `sweep_corpus.py` (`dev/docs/spikes/2026-08-31-native-parity-report/harness/`), the
corpus-wide parity sweep driver.

`parity_pipeline.build_root()` deliberately keys the trunk-extraction cache under the CALLING
worktree's own `_scratch/` (never `/tmp`, per a bind-mount constraint documented on that function) --
which meant a fresh disposable worktree never reused a prior sweep's extracted trunks, forcing a
re-extract every sweep even for an already-measured level. `sweep_worker_shim.py` fixes this by
redirecting to `sweep_lib.shared_trunk_cache_root()`: a FIXED location,
`<main checkout>/.claude/worktrees/uedcli-parity-trunk-cache/`, shared by every worktree on this box
and outliving any single worktree's own creation/removal (same sharing pattern
`tool_assets.umodel_dir()` already gets incidentally, `board/inbox/
docker-mount-source-permission-fails-from-main`).

**The tradeoff this buys:** unlike the old per-worktree `_scratch/`, this location is never cleaned up
by deleting a worktree -- it only grows. Measured: 18 trunks so far cost ~183M
(`_scratch/uedcli-parity-cache` before the move). Disk on this box is already tight (30G free / 466G,
94% used at measurement time). Not a blocker for now (18 levels tops out around 200-400M), but if the
corpus grows or trunks get re-extracted after a format change without ever clearing stale ones, this
has no ceiling and no pruning policy.

Not fixed here -- out of scope for a sweep-driver task, and a pruning/retention policy (age-based?
content-hash-only-keep-latest? manual `rm -rf`?) is a real decision, not an obvious default. Whoever
picks this up: decide a retention rule, or at minimum document "run `rm -rf
.claude/worktrees/uedcli-parity-trunk-cache` to reclaim space, it will just re-extract on next use."
