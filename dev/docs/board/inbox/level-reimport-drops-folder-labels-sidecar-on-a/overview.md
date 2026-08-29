+++
priority = "p?"
kind = "debug"
summary = "level reimport drops folder/labels sidecar on a matched actor whose body changed"
+++

# level reimport drops folder/labels sidecar on a matched actor whose body changed

Found while building `level reimport` per
`dev/docs/board/to-build/level-reimport-reimport-a-hand-edited-dx-unr/plan.md` (executed as given;
not fixed here per this repo's "implement as given, log a design gap instead of fixing it" rule).

`dev/docs/board/to-build/level-reimport-reimport-a-hand-edited-dx-unr/spec.md` states, for a
**matched** actor: "body replaced verbatim from the decode ... Folder/label sidecars are left
untouched — the compiled format carries neither." This holds for a matched actor whose body is
UNCHANGED (excluded from `only`, so `trunk.write_level` never touches its dir), but not for one
whose body genuinely changed — the exact case reimport exists for.

`_level_reimport` (`uedcli/cli/commands/level.py`) builds `new_level` from the map decode alone;
`Actor.folder`/`labels` are never populated there (nothing copies them from the existing trunk).
A matched actor with a real body diff lands in `diff.changed` → `only`, and
`trunk.write_level(level_dir, new_level, ranks, deleted=diff.deleted, only=only)` writes it from
`new_level.actors[n]`. `t3dtree.write_actor_tree` sources the `folder`/`labels` sidecar writes from
that same object (lines ~199-224): `folder=None` deletes the `folder` file, `labels=frozenset()`
deletes `labels`. Reproduced directly: an actor with `folder="dungeon.hall"` plus a real prop change
comes out with `folder=None` after the write.

The one folder-preservation test (`test_reimport_preserves_folders_and_labels_on_an_untouched_actor`
in `uedcli/tests/test_reimport_verb.py`) only covers the true no-op path, so it doesn't catch this.

Fix would be: before calling `trunk.write_level`, copy `folder`/`labels` from `existing_level.actors`
onto the matching entries in `new_level` for every matched name. Left to the owner to confirm vs.
spec update, per "a decision is implemented as given" — not changed silently here.
