# Testing strategy during the migration

Proposed, not yet confirmed: two complementary methods, both usable without shipping Python in the
final binary (test-time and runtime dependencies are separate).

- **Differential testing (primary).** Keep `old/`'s compiled binary as a live test-time oracle. For
  each verb, run both `old/` and the new Rust implementation against identical inputs and diff
  stdout/exit code/produced T3D bytes. As a verb passes consistently, retire its `old/`
  implementation. Catches drift on arbitrary new inputs, not just recorded ones.
- **Fixture extraction (complementary).** Many existing tests are already input/expected-output
  pairs (T3D golden files, byte-parity captures). Extract those into data fixtures once, then point
  `cargo test` at the same fixtures — no live Python needed, but only covers cases someone already
  thought to test.

Combining both: differential testing catches drift while `old/` still exists; fixture extraction
preserves the specific cases once `old/` is gone and there's nothing left to differential-test
against.

## Answer

