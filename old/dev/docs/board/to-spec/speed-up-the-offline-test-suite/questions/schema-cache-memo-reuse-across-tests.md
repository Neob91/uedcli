## Question

`schema_cache.py`'s `_enabled()` switch gates both the persistent disk cache AND the in-process
memo (`_DISC_MEMO`/`_PROP_MEMO`) together. The offline suite forces it off suite-wide
(`_schema_cache_off` in `conftest.py`), which is the real cost behind the `test_dispatch.py::
test_actor_find_*` (75s) and `test_board_script.py` (72s) clusters — every `--prop`-touching
dispatch call fully re-decodes its package from bytes, every time, by design (that's what "off"
means; an earlier draft of this spec wrongly blamed a memo-clearing fixture — the memo is never
even populated when the cache is off, so there was nothing to clear).

Getting a safe speed win here means adding a THIRD mode to `schema_cache.py`: memo warm (so
repeated calls to the same real package path reuse the in-process decode within one pytest run),
disk cache still off (so the persistent-cache-poisoning concern the `off` mode exists for is
unaffected). That's a change to production code, not a test fixture — is it worth doing as part of
the test-suite-speed effort, or should it be its own board item?

**Follow-up raised live, checked:** would a warm cross-test memo invalidate a test that writes a
package and re-reads it expecting fresh content? Yes, in principle — the memo is keyed by
`realpath`, not by file stat, so a stale entry would be served across a same-path rewrite. This is
already a REAL, known hazard, not hypothetical: `test_schema_cache.py::test_stat_change_is_a_miss`
and `::test_utime_restored_stale_bytes_ARE_served_the_old_entry` both write new bytes to the same
path mid-test and call `_clear_memos()` themselves before re-reading, specifically to avoid it. I
checked the other two files that write package bytes in the offline suite
(`test_pkg_cache.py`, `test_uprops.py`) — neither routes its write-then-read through
`schema_cache.load_package_schema`'s memoized path, so neither is exposed. I did not find any test
outside `test_schema_cache.py` that would collide. That narrows the risk but doesn't retire it: any
future test doing package-write-then-reread through `schema_cache` would need to remember to call
`_clear_memos()` itself, the same way `test_schema_cache.py` already does — an easy thing to forget.

## Answer
