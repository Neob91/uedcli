+++
priority = "p1"
kind = "debug"
summary = "load_actor_body StopIteration on non-blank unparseable actor.t3d crashes every read verb"
+++

# load_actor_body StopIteration on non-blank unparseable actor.t3d

`t3dtree.py:132-135` (`load_actor_body`). `parse_t3d` never raises on unparseable text — it returns
a `Level` with an empty `.actors` dict — so `a = next(iter(lvl.actors.values()))` (line 135) raises
raw `StopIteration`. `read_actor_tree` (line 271-272) skips only a fully BLANK body
(`if not text.strip(): continue`, added to fix an earlier instance of this exact bug — see
`test_read_level_skips_an_empty_torn_body`). A non-blank-but-unparseable body — unresolved git
merge-conflict markers, a truncated hand-edit — reaches `load_actor_body` unguarded.

`trunk.read_level` re-exports this same reader, the ONE shared reader for trunk, stash, and prefab.
So this breaks ANY verb that loads the ambient level: `actor show`, `actor find`, `level status`,
`actor prop get`, … as a raw traceback, not a clean exit 2. Not caught by `dispatch.py`'s guard set.

Trigger: leave `<<<<<<< HEAD …` conflict markers (or any garbage) in one
`actors/<name>/actor.t3d`, then `actor show Foo`. Realistic for the git-native trunk after a bad
merge.

Test coverage: partial — only the 0-byte case is covered; the corrupt-`meta.json` tests don't cover
corrupt `actor.t3d`.

Fix: on empty `lvl.actors`, raise a value-naming error (the dir `name`) that `dispatch.py` turns into
a clean exit 2. Regression test with conflict-marker body.

Confirmed by direct read; StopIteration reproduced empirically by the auditing subagent.
