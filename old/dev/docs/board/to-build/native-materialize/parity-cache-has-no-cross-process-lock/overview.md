+++
priority = "p2"
kind = "debug"
summary = "parity cache has no cross-process lock -- concurrent sweeps can race on the same content-hash entry"
+++

# parity cache has no cross-process lock -- concurrent sweeps can race on the same content-hash entry

Found building/testing `sweep_corpus.py` (`dev/docs/spikes/2026-08-31-native-parity-report/harness/`).
Live-observed 2026-09-02: `/tmp/uedcli-parity-cache/*/meta.json` has 17 of 18 corpus entries stuck at
`status: "building"` or `"extracting"` with no `golden.dx` -- stale markers left by earlier
concurrent-agent attempts this session that died mid-build (the contention-timeout incidents this
task exists to fix) or were still running when superseded. This is HANDLED correctly on the read
side: `parity_lib.is_cache_complete` only trusts `status == "complete"` AND `golden.dx` present, so
`parity_pipeline.ensure_golden` correctly treats a stuck "building" entry as a cache MISS and
re-attempts, never waiting on it or trusting it as in-progress-elsewhere. No bug there.

**The real gap: nothing stops TWO processes from re-attempting the SAME stuck hash concurrently.**
`ensure_golden` has no lock around `cache_root/<hash>/` (unlike the trunk write pattern elsewhere in
this codebase, e.g. `trunk.write_level`'s per-level flock, `<maps-dir>/.locks/level-<name>.lock`,
`architecture.md` "The core write pattern"). If a stray/leftover process from an earlier sweep and a
fresh sweep both target the same not-yet-complete level at the same time, both see `cache_hit=False`
and both run `extract_trunk`/`build_golden` against the SAME `trunk_dir`/`golden_path` concurrently --
two docker containers writing overlapping output, `meta.json` written by whichever finishes last (the
earlier live-editor contention incidents this session, `TimeoutError: editor not idle`, are plausible
symptoms of exactly this, not just raw CPU contention).

Not reproduced deliberately (would require deliberately racing two real editor builds, expensive and
somewhat destructive to try just to confirm). Not fixed here -- `parity_pipeline.py` is shared
infrastructure this task didn't create, and the fix (a flock around each cache entry, mirroring
`trunk.write_level`'s pattern) is a design call for whoever owns that file, not a call `sweep_corpus.py`
should make unilaterally by, e.g., adding its OWN ad hoc locking that only protects sweep-driven
callers and not a bare `parity_report.py` CLI invocation.

**Mitigated in the meantime, not fixed:** `sweep_corpus.py` defaults to `--concurrency 1` (serializes
its OWN calls, so it never races itself), and this session's stale "building"/"extracting" entries
were left alone rather than deleted (some may still be legitimately in progress from another agent;
deleting them blind risked pulling the rug out from under a real in-flight build).
