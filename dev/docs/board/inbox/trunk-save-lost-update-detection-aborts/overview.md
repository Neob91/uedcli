+++
priority = "p3"
kind = "chore"
summary = "Trunk-save lost-update detection aborts at whole-save granularity (known tradeoff)"
+++

# Trunk-save lost-update detection aborts at whole-save granularity (known tradeoff)

The `TrunkLevelSource.save` compare-and-abort (spec `specs/2026-07-25-trunk-write-safety.md`, D3)
aborts the ENTIRE save if any one actor in `changed ∪ deleted` was touched concurrently — so a large
batched pipeline (`actor find … | actor prop set -` over hundreds of actors) loses its whole save
when a single target raced, and a persistent concurrent writer could livelock the retry. This is the
deliberate abort-not-merge semantics (Andrzej 2026-07-25) and is recoverable (uedcli is stateless per
invocation; the re-run reloads fresh and recomputes), so it is not a correctness bug — logged as a
known coarse-granularity tradeoff, not surfaced as a surprise. A finer-grained "write the
non-conflicting subset, report the conflicts" mode is the possible future refinement. (From the D3
spec review, 2026-07-25.)
