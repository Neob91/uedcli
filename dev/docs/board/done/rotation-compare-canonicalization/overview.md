+++
priority = "p?"
kind = "implement"
summary = "`Rotation` canonicalization at compare time — built, then replaced by typed effective-value compare"
+++

# `Rotation` canonicalization at compare time

Comparing an actor's `Rotation` against its class default used to need a text fold of the rotation
string. That mechanism was built and then removed: the compare seam now decodes both sides to typed
effective values, where expanding a partial struct against the class default falls out of the
general rule. Kept as design history.

This item exists to hold the spec, which no board entry owned.
