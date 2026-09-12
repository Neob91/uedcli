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

## Answer
