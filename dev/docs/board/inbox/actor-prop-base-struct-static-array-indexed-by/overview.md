+++
priority = "p1"
kind = "debug"
summary = "actor prop: base struct static-array indexed by member silently writes index 0"
+++

# actor prop: base struct static-array indexed by member silently writes index 0

`propedit/paths.py:53-88` (`resolve_path`). The `array_dim` guard fires only when the first path
segment is an `int` (line 53). When the base prop is itself a struct-typed static array and the
token is `Anchors.X` (identifier, not int), `index` stays `None` and the loop descends into member
`X` with no error. The nested-member-array case IS guarded (lines 66, 78-80: "index it first") — the
base level just isn't.

Trigger: actor with `Anchors(2)=(X=1,Y=2,Z=3)`, run `actor prop set Anchors.X=99`. The member-set
path in `edit.py:287-300` defaults `idx=0`, finds no unindexed stored line, materialises element 0's
default via `full_struct_text`, sets `X=99`, and appends a new UNINDEXED `Anchors=(X=99,…)` line —
which T3D reads as element 0. Siblings (`Y`/`Z`) take element-0's default (usually zero). Original
`Anchors(2)` is untouched; exits 0. `rp.canonical` prints `Anchors.X` (no index), so the diagnostic
can't reveal it. `get` / `unset` / `find --prop` inherit it (`unset` silently no-ops).

Silent wrong write — violates "no silent half-answers." Reachable for any placeable class with a
struct-typed static-array field other than `KeyPos`/`KeyRot` (those are HARD_REJECT).

Fix: add a base-level guard mirroring lines 78-80 — a struct static array accessed by member without
an index must exit 2 naming the prop. Cover with a regression test.

Double-checked (self + Sonnet adversarial pass): bug CONFIRMED, fix CONFIRMED. The guard is the
single choke point every consumer goes through (`edit.py:194,318,422`) and it fires only when
segments remain after an unconsumed index — the whole-array (`Anchors`) and indexed
(`Anchors.2.X`/`Anchors(2).X`) paths are unaffected.
