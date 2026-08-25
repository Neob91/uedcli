+++
priority = "p1"
kind = "debug"
summary = "load_actor_body StopIteration on non-blank unparseable actor.t3d crashes every read verb"
+++

# load_actor_body StopIteration on non-blank unparseable actor.t3d

DONE (commit 25d1409). `load_actor_body` (`t3dtree.py`) now raises a value-naming error on an empty
parse, and `TrunkLevelSource.load` wraps the read in `except (OSError, ValueError) -> CommandError`
(matching the stash/prefab siblings). A corrupt/merge-marker `actor.t3d` is a clean exit 2 naming the
actor, not a raw `StopIteration`. Regression tests in `test_level_source.py`.
