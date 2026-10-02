# Should the live materialize round-trip test use a synthetic trunk, or a real base-content game map?

## Context

The live round-trip test (`test_materialize_builds_and_verifies_live`) is today an unconditional-skip
placeholder. Filling it needs a fixture choice:

- **Synthetic trunk** (recommended): build a small hand-authored one-actor trunk, materialize, verify.
  Deterministic, needs only the `dx-lum-uned` container — no game install. Doesn't exercise a real map's
  quirks (native content, existing actors, real order).
- **Real base-content map** (the item's literal ask): load e.g. a Deus Ex map, move a real actor,
  materialize, verify the move survives. Higher fidelity, but requires the DX install present and a
  chosen map+actor guaranteed to exist. `Maps/Entry.dx` has no `Light`; the original idea self-skipped
  when the actor was missing — that fragility must be replaced by a deterministic actor pick, not a skip.

Both could coexist (synthetic as the always-on gate, real-map as install-gated). The fork is whether
live tests may depend on a real game install at all.

Recommendation: do the synthetic build+verify now; add the real-map round-trip only if you want live
coverage over shipped game maps.

## Answer

<!-- Empty = open. -->
