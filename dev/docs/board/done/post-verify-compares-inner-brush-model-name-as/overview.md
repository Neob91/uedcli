+++
priority = "p?"
kind = "unknown"
summary = "Post-verify inner brush model Name: not a bug — store/load neutralization keeps both sides in sync"
+++

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

## Resolution (not a bug)

`t3dtree.dump_actor_body` neutralizes a stored brush's `model_name` to the constant `Model` (and
`Brush=Model'MyLevel.Model'`); `load_actor_body` re-derives it to `Model_<actorname>`. The native
writer names models `Model_<actor>` too, so both post-verify sides derive the SAME name — the model
name never mismatches for a real stored/captured trunk. The `Model823` failure was a synthesized
round-trip-test fixture that set the name directly, bypassing store/load neutralization; not a real
materialize path. Verified live: bar `Brush1` expected+built both `Model_Brush1`, geometry equal.
No code change needed.
