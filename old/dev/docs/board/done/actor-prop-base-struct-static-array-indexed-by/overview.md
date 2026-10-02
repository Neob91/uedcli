+++
priority = "p1"
kind = "debug"
summary = "actor prop: base struct static-array indexed by member silently writes index 0"
+++

# actor prop: base struct static-array indexed by member silently writes index 0

DONE (commit 25d1409). `resolve_path` (`propedit/paths.py`) now rejects a base-level struct static
array addressed by member with no index (`Anchors.X`) — exits 2 naming the array instead of
fabricating element 0 and leaving the real element untouched. Regression tests in
`test_actor_prop.py` (set + get + the still-working `Anchors.2.X` spelling).
