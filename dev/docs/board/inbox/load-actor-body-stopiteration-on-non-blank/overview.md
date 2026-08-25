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

Fix (double-checked — TWO parts, both needed):
1. In `load_actor_body`, on empty `lvl.actors` raise a value-naming error (the dir `name`).
2. Wrap `TrunkLevelSource.load()` (`cli/level_sources.py:55-63`) in
   `except (OSError, ValueError) as e: raise CommandError(...)` — its stash/prefab siblings
   (`:148-152`, `:195-201`) already do this; the trunk path (the one this trigger exercises) does
   NOT, and `dispatch.py`'s guard catches neither bare `StopIteration` nor bare `ValueError`. Part 1
   alone still escapes uncaught for trunk-level commands.
Regression test with a conflict-marker body.

Double-checked (self + Sonnet): bug CONFIRMED (`dispatch.py:26-82` catch list excludes
`StopIteration`); fix PARTIAL as first written — needs part 2 above.
