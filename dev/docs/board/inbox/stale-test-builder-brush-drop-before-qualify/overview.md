---
kind: bug
---

# Stale test: builder-brush drop-before-qualify ordering test fails

`uedcli/tests/test_mapimport_import.py::test_the_drop_must_happen_before_class_names_are_qualified`
fails (`bin/test`, with `uned/UED22/Engine.u` present).

Pre-existing, introduced by `e5fb2b7` (`materialize: faithful actor order + movers written
in-package`), NOT by the texture-group fix on this branch. `git blame` puts the change at
`normalize.is_builder_brush` line 156: it now matches the BARE class name
(`(a.cls or "").rsplit(".", 1)[-1] != "Brush"`), so the builder brush is detected whether the class
is `Brush` or `Engine.Brush`. The test pins the OLD invariant — that qualifying the class to
`Engine.Brush` first would defeat the short-name match and leave the builder brush undropped — which
no longer holds.

Decide: the test's ordering constraint is obsolete now that the check is qualification-independent.
Either delete/rewrite the test, or, if the ordering still matters for `drop_editor_scratch`'s scratch
checks, restate what it should assert. Out of scope for the texture-group fix.
