+++
priority = "p?"
kind = "unknown"
summary = "`mover key` keyframe model rework"
+++

# `mover key` keyframe model rework

— BUILT 2026-07-20. Spec: `spec.md`; decisions 2026-07-20 16:18 UTC. `mover key
add` removed; new **`mover key count <name> [<n>]`** gets/sets `NumKeys` (2..8, non-destructive) via
the shared `movers.set_num_keys`; `NumKeys` off `propedit.HARD_REJECT` so `actor prop set
NumKeys=<n>` is identical in effect. `move`/`rotate <i>` are edit-only (`1 ≤ i < NumKeys`) with a
**required** `--from-base`/`--from-world` frame on `--to` (`--by` frame-agnostic). Touched
cli/dispatch/movers/propedit + usage.md/architecture.md/README + leveldesign recipes; tests in
test_movers/test_actor_prop/test_dispatch/test_name_not_found_sweep. Engine-fact pin
`test_it_keeps_numkeys_when_a_key_is_zeroed` (spike `spikes/2026-07-20-mover-numkeys-trailing-zero/`).
