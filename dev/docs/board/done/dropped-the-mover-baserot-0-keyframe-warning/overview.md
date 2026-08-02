+++
priority = "p?"
kind = "unknown"
summary = "Dropped the mover `BaseRot≠0` keyframe warning"
+++

# Dropped the mover `BaseRot≠0` keyframe warning

— 2026-07-07. The interim stderr caution on
`mover key add`/`move`/`rotate` against a base-rotated mover was noise: `KeyPos[i]` is
world-additive (`Location = BasePos + KeyPos[i]`, not rotated by `BaseRot`) and `KeyRot[i]`
field-adds to `BaseRot` — confirmed by a live measurement (90°-yaw base, `KeyPos(1)=(X=256)` → world
+X) and the disassembled editor transform, folded into
`spikes/2026-06-25-mover-keyframe-basepos-semantics.md`. Removed `_warn_base_rot` + its 3 call sites
(`dispatch.py`); regression test `test_it_does_not_warn_on_a_base_rotated_mover_key_op`; docs made
confirmed-fact (`architecture.md` "Mover support", `rationale/MIGRATION.md` 2026-07-07 12:11 UTC).
