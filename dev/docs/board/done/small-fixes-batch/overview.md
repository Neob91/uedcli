+++
priority = "p?"
kind = "unknown"
summary = "Small fixes batch — five of `to-build.md` #9 BUILT 2026-07-25"
+++

# Small fixes batch — five of `to-build.md` #9 BUILT 2026-07-25

(one commit each; 9.4, the
schema-aware `mover key` gate, landed separately — see the entry above).
**9.1** `class show` now EXITS 2 naming an unreadable/missing ANCESTOR package instead of printing
own-only props with a stderr note — the degrade branch, its `--category` special case and
`test_class_show_category_rejects_degraded_schema` are deleted (`direction.md` "No silent
half-answers"); the fallback's last user, `ClassIndex._package`, went with it. **9.2**
`driver.map_save` WAITS FOR and VERIFIES its own output (and returns the size): driving is
fire-and-forget and `MAP SAVE` answers nothing over the console, so it polls the file inside the
container, raising `DriverError` naming the path on timeout — instead of letting a wedged editor
surface as an opaque `docker cp` exit 1. (The review gate caught that the first cut checked ONCE,
immediately, which false-fails a slow save. The engine fact is pinned in `unrealed/commands.md`
"Driving is fire-and-forget"; the "truncated golden" this entry originally cited as the other
motive was later RETRACTED — spike §91 showed that golden is deterministic, not truncated.)
**Its accept rule was REPLACED 2026-07-25** — the two-equal-sizes + `stat`-exit-code version
described here is gone; see the entry below and `decisions.md` 2026-07-25 11:31 UTC.
**9.3** `actor folder set/unset` are PRODUCERS (touched Names → stdout, count → stderr), so the
folder and label dimensions now behave identically and folder edits chain in a pipeline.
**9.6** `uedcli cache gc [--max-bytes N] [--max-entries N]` wires the shipped
`schema_cache.sweep()` to the CLI (reclaim orphaned `v<N>/` dirs + LRU-evict to a cap; a negative
cap exits 2). Docs updated in the same commits (`usage.md`, `architecture.md`).
**9.5 was MOOT as written** — its premise (the two `test_native_materialize.py` box-sweep tests
die on the spike harness import) does NOT reproduce: both PASS at HEAD, because `line_check.py`
now sits in the spikes tree and self-inserts its sibling harness on `sys.path`. Marking two GREEN
tests skipped would have deleted real coverage of the "pawn falls through the floor" bug, so
instead `_load_line_check()` now turns a harness-side `ImportError` into a SKIP naming the spike
env while letting a `uedcli` `ImportError` propagate (a real regression must stay red). Flagged on
`inbox.md` for Andrzej.
