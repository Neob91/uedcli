# Close this debug item as already-fixed by the typed compare (no write-side change)?

## Context

The report (2026-07-16): `actor rotate`/`actor prop` store `Rotation=(Pitch=0,Yaw=8192,Roll=0)`;
the editor re-exports `(Yaw=8192)`; the trunk fails H3 post-verify. The overview proposed a
write-side fix (omit zero FRotator fields, e.g. via `rotation.emit_frotator`).

Since then (2026-07-25) the typed, member-wise compare view landed and makes the two spellings
compare equal — pinned by `test_normalize.py::test_a_yaw_only_actor_compares_equal_to_its_editor_reexport`
("THE ORIGINAL REPORTED BUG"). So the symptom is already gone.

The proposed write-side fix is now **unsafe**: omitting fields for an identity rotation drops the
whole `Rotation` prop, which re-imports as the *class default* — non-zero for `TNM.LavaSpitter` —
the exact silent-corruption bug recorded in `dev/docs/unrealed/t3d.md` (instance 1). It also
violates the standing rule "the write side never omits an actor property to mean zero".

Recommendation: **close as fixed.** Keep explicit-field writes. The only residual work is a
test-only step — confirm an end-to-end `actor rotate` (or `actor prop set`) → `level materialize`
→ H3-pass regression exists for a yaw-only actor, and add one if not. No code change to the write
or normalize paths.

## Answer

<!-- Empty = open. -->
