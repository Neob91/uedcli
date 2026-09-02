+++
priority = "p3"
kind = "debug"
summary = "test_dxonly_fbspnode_semantics_pinned raises IndexError instead of skipping when the checkout sits shallow in the filesystem."
+++

# `test_dxonly_fbspnode_semantics_pinned` crashes instead of skipping on a shallow checkout

`bin/test` is red on master because this test raises a bare `IndexError` rather than skipping.

Its helper `_dxonly_map_path` does `Path(__file__).resolve().parents[5]` to reach a sibling `Maps/`
directory. From `/workspace/uedcli/uedcli/tests/…` there are only five parents, so the index raises
**before** the "is the map present?" check can skip.

```
bin/test -k dxonly_fbspnode   →  IndexError: 5
```

The same test **skips cleanly from a deeper path**, such as a worktree under `.claude/worktrees/`,
which is why it is easy to miss: whether it passes depends on where the checkout sits.

**Fix:** guard the `parents[…]` index (or build the candidate paths defensively) so an unlocatable
map skips like the other retail-corpus tests.

**Pre-existing and unrelated to the board migration or to `level import`** — found while
establishing a baseline for that work, not caused by it.

*The earlier version of this item guessed the cause wrongly — it said the pinned `FBspNode`
semantics had drifted or the pin was recorded wrong. It is neither; nothing about the pin is
involved, because the helper raises before any parsing happens. The correct diagnosis above was
carried over from the `installer-url`/`level-import` branch work, where it was measured.*
