+++
priority = "p2"
kind = "chore"
summary = "Offline bin/test cut from ~1196s/14243 tests to ~375s/4915 tests"
+++

# pytest suite slow: unmarked docker tests + repo-wide parametrize inflation

**Fixed.** Ten `uscript_*` tests that spun real docker+wine+UCC were gated only by a runtime
`skipif`, not `@pytest.mark.integration`, so `-m "not integration"` didn't exclude them on a
docker-enabled host — added the marker (owner decision: this does mean `-k <module>` on those files
now also needs `-m integration`). `test_board.py`/`test_doc_links.py` parametrized one pytest item
per board item / per tracked repo file (9247 of 14243 collected tests) — collapsed each into a
single loop-based test that asserts on the full list of failures. Result: 4915 collected tests,
~375s full offline run (was ~1196s). Commits `144d88f`, `b582713`.

The unbatched `bin/board` shell-out and the `test_materialize_verb.py` 3.5s-per-test mystery, also
found during this investigation, were not part of the fix — split out to
`bin-board-shells-out-unbatched-over-762-items`.
