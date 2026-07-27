+++
priority = "p2"
kind = "debug"
summary = "test_dxonly_fbspnode_semantics_pinned fails on master, unrelated to any board work."
+++

# `test_dxonly_fbspnode_semantics_pinned` fails on master

`bin/test` is **red on master** (2026-07-27):

```
FAILED uedcli/tests/test_native_materialize.py::test_dxonly_fbspnode_semantics_pinned
```

Pre-existing and unrelated to the board migration — the test file's last commit is the
`uedctl` → `uedcli` rename, long before this work.

It is a **pinned-semantics** test, so the failure means either the pinned `FBspNode` semantics
drifted or the pin was recorded wrong. Both matter: `dev/docs/rules/spikes.md` treats a pin as what
stops a finding rotting, so a red pin is a finding already rotting. Needs someone who knows the
native materialize path to say which.

Found while landing the board-migration scaffold.
