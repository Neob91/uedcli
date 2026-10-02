+++
priority = "p2"
kind = "debug"
summary = "stash/prefab write_tree_box has no lock — concurrent writers silently clobber"
+++

# stash/prefab write_tree_box has no lock

DONE (commit 25d1409). `write_tree_box` (`stashlib.py`) now takes a per-box `flock` on
`<root>/.locks/<box>.lock` before the staging swap, and `validate_member_name` rejects leading-dot
box names (`.locks`/`.staging` collision, caught in review). Regression tests in `test_stashlib.py`.

Not addressed (separate concern): true compose-parity with the trunk's per-actor delta write —
`write_tree_box` is still a full-snapshot replace; the flock only serialises writers cleanly. File a
new item if disjoint-edit composition is wanted here.
