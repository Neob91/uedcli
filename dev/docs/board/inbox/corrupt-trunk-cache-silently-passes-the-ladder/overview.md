+++
priority = "p2"
kind = "debug"
summary = "A truncated trunk extraction is cached as complete and then silently PASSES the parity ladder — an Island trunk of 102 pathnodes/weapons (no LevelInfo, no brushes) produced a bogus 'Island N1-16 byte-exact' result."
+++

# A truncated trunk cache silently passes the ladder

`actor_parity._resolve_trunk` reuses `_scratch/uedcli-parity-cache/<dx-hash>/trunk/maps/<level>/` when
`.extraction-complete` exists. The marker records that extraction finished, not that it extracted the
level: two worktrees carried an Island trunk of **102 actors starting at `PathNode838`** — no
`LevelInfo`, no brushes — under the same hash where a correct extraction yields **3653 actors starting
`LevelInfo0, Brush296, …`**.

The ladder then "passes" loudly and meaninglessly: every first-N subset is pathnodes and weapons, so
native and the editor agree on an empty world. That is how Island N1-16 was recorded byte-exact while
N=5 in fact FAILS (`island-n5-n12-pre-existing-model2-orphan-vert-4`), and how a real finding got
closed as a stale-ref false alarm.

Cached refs are per-worktree and built from that worktree's trunk, so a bad trunk also poisons every
`ref_N*.dx` beside it. The trunk carries a per-extraction level UUID in its actor refs, so a ref is
only valid against the trunk it was built from — refs and trunk must be copied together or not at all.

## What would catch it

- Assert the extracted trunk's actor 0 is a `LevelInfo` and that the actor count is within a sane
  factor of the shipped `.dx`'s export count before writing `.extraction-complete`; treat a mismatch
  as a failed extraction (exit non-zero), not a cache entry.
- Record the extracting build's actor count in the marker and re-check it on reuse.
