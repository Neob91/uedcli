+++
priority = "p3"
kind = "investigate"
summary = "UT99 zero-default suppression unverified for enum-constant defaults"
+++

# UT99 zero-default suppression unverified for enum-constant defaults

`_emit_default` (`uedcli/uscript/compile.py`) suppresses a defaultproperties tag for a type-zero
scalar value under `emit_zero_defaults=False` (UT99) — live-probed against the real `ASPMutator`'s
`bDebugMode=False` (a bool). An explicit enum-constant default whose ordinal is 0 (e.g.
`MyState=STATE_Idle` where `STATE_Idle` is the enum's first tag) goes through the same value-zero
path but is currently EXCLUDED from suppression (`is_enum_default` guard), on the conservative
assumption that only the plain-scalar case was actually measured.

Open question: does real UT99 UCC also suppress an explicit ordinal-0 enum default the same way it
suppresses `bDebugMode=False`? Settle with a controlled fixture (an enum var whose first tag is
explicitly assigned, alongside a non-zero-ordinal sibling on the same multi-name declaration) compiled
through live UT99 UCC. No corpus package hits this today — found during code review of the
`ASPMutator` win, not from a real failure.
