# What closes this item — offline wiring pin + one live run, or a standing gated live test?

## Context

Most of the `/stubs` wiring is already offline-assertable: the env var equals `stub_cache_root()`,
`/stubs` leads the Paths, the remap targets `/stubs/…`. The genuinely live-only fact is that a real
container populates and loads from that mount. That fact needs a retail install and a built stub,
neither present in CI.

Options:

- A. Close on an OFFLINE test of the wiring plus a one-time documented live confirmation (spike
  finding); no permanently-running live test.
- B. Also add a substrate-gated integration test that boots a real editor and asserts the
  `OBJ LOAD FILE=/stubs/…`, skipped when no install is configured.

Recommendation: A. The load-from-`/stubs` behavior is the same `OBJ LOAD FILE=` path every apply
already exercises; the offline pin guards the wiring that can actually drift, and a standing live
test buys little over the existing materialize integration coverage while adding a flaky,
install-dependent job.

## Answer

<!-- Empty = open. -->
