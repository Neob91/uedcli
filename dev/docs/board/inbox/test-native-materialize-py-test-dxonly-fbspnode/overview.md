+++
priority = "p3"
kind = "debug"
summary = "`test_native_materialize.py::test_dxonly_fbspnode_semantics_pinned` crashes with a bare `IndexError` instead of skipping, when the checkout sits shallow in the filesystem"
+++

# `test_native_materialize.py::test_dxonly_fbspnode_semantics_pinned` crashes with a bare `IndexError` instead of skipping, when the checkout sits shallow in the filesystem

Its
helper `_dxonly_map_path` does `Path(__file__).resolve().parents[5]` to reach a sibling `Maps/`
dir; from `/workspace/uedcli/uedcli/tests/…` there are only five parents, so indexing raises
before the "is the map present?" check can skip. Reproduced 2026-07-27 in the main checkout
(`bin/test -k dxonly_fbspnode` → `IndexError: 5`); the same test SKIPS cleanly from a deeper path
such as a worktree under `.claude/worktrees/`, which is why it is easy to miss. Fix: guard the
`parents[…]` index (or build the candidate paths defensively) so an unlocatable map skips like the
other retail-corpus tests. **Pre-existing and unrelated to `level import`** — found while
establishing a baseline for that work, not caused by it. *(2026-07-27.)*
