+++
priority = "p?"
kind = "implement"
summary = "`actor rotate` (multi-actor group rotation)"
+++

# `actor rotate` (multi-actor group rotation)

— IMPLEMENTED 2026-06-19
(offline suite green; the live materialize round-trip is substrate-gated —
`tests/test_rotate_integration.py`, `integration`-marked + deselected). Rotates a group about a
shared pivot model-side; orbit Location by the matrix + compose orientation into `Rotation` by
per-component FRotator field-addition (editor parity); `PolyList` stays local. **Done since:**
`PrePivot` honoured everywhere (2026-06-19); rotation-aware `brush clip`/`brush vertex move`.
**Deferred remnant:** honour **scale** (`MainScale`/`PostScale`) in the world transform (still
ignored — a measurement gap for the rare scaled imported brush, never stored-geometry
corruption; see `unrealed/quirks.md` "Pivots"); non-uniform-scale + rotation order-sensitivity;
a *fractional* corner on a *rotated* brush may not match `vertex move --at` (float inversion).
