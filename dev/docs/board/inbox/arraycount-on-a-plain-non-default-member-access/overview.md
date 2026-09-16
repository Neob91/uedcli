+++
priority = "p3"
kind = "debug"
summary = "ArrayCount on a plain (non-default) member access not implemented"
spikes = ["dev/docs/spikes/2026-09-14-utserveradmin-class-ref-gaps/"]
+++

# ArrayCount on a plain (non-default) member access not implemented

`lower._array_count_dim` handles a bare local/param/own-member array and a `.default` chain (any
nesting) — both needed by the real UT99 `UTServerAdmin`. A PLAIN member access as the sole argument
(`ArrayCount(SomeObj.SomeArrayField)`, no `.default` qualifier) raises `NotImplementedError` — not
exercised by any fixture, not guessed at.

Fix needs a side-effect-free type inference for an arbitrary (non-`.default`) base expression
(mirroring `_meta_class_of`'s style but for ordinary object types, not meta), since `_array_count_dim`
must know the base's type WITHOUT double-lowering it (the real `self.expr()` call that produces the
Dependency side effects happens once, separately, in `_call_named`'s ArrayCount branch).
`probe_array_count_plain_member.py` (spike above) has a live-verified golden for this exact shape
(`ArrayCount(B.Maps)`) ready to use once the mechanism exists.
