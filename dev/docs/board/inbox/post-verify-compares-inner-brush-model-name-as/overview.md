---
kind: question
---

# Post-verify compares inner brush model Name as authored content

The compare geometry text (`normalize._geometry_text` -> `emit.emit_brush`) emits
`Begin Brush Name=<model_name>`, so the inner brush UModel Name is part of what the post-verify
compares. The native writer always names a CSG brush's private shape `Model_<actorname>`
(`native.assemble` line 228). So a trunk brush whose stored model name is NOT `Model_<actorname>`
(e.g. a captured `Model823`) would fail post-verify on geometry line 1: built `Model_<name>` vs
intended `Model823`.

Observed while writing the offline round-trip test (`test_native_roundtrip.py`) — worked around there
by naming the fixture models `Model_<actor>`. Unconfirmed whether real captured trunks hit this
(depends on how capture names brush models).

Question: is the inner brush model Name authored content, or engine bookkeeping that the compare
should canonicalize out (like the LevelInfo actor name and the poly Normal already are)? If the
latter, `_geometry_text` should drop/normalize it.
