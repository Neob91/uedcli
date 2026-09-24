+++
priority = "p3"
kind = "unknown"
summary = "Audio identity: a 2-part ref never resolves to a 3-part identity (plan A3 wording)"
+++

# Audio identity: a 2-part ref never resolves to a 3-part identity (plan A3 wording)

Not a code bug — plan A3's "2-part ref resolves to a 3-part identity" test bullet was impossible under
the collision rule (identity = `Package.Name` when unique, else `Package.Group.Name`): a 3-part
identity only exists because the bare name collides, which is exactly when a 2-part ref is ambiguous.
`audioindex.AudioIndex.resolve` implements the coherent four-case behavior (`test_audioindex.py` pins
it); the impossible bullet is dropped as impossible, nothing else in the plan depended on it.
