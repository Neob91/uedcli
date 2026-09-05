+++
priority = "p3"
kind = "bug"
summary = "actor_parity ref/native caches can silently hold a non-prefix (corrupt) actor set"
+++

# actor_parity ref/native caches can silently hold a non-prefix (corrupt) actor set

Island `ref_N10.dx` held actors at trunk indices {0,1,2,3,4,5,12,13,14,15} (WeaponCrowbar3@12,
WeaponLAM0@13, PathNode705@14, PathNode710@15), missing PathNode99@9 — not the first-10 prefix at
all. `ref_N9`/`ref_N11`/`ref_N12` were correct prefixes. The gate then reported 6 phantom N=10
residuals (name/import/export/actors-array diffs) that looked like native bugs but were the stale
ref. Rebuilding `ref_N10` (unchanged trunk) flipped N=10 to PASS with no code change.

Cause unknown — a one-off from an interrupted/racy `actor_parity ref N` build, most likely. The trap:
the parity gate cannot distinguish a corrupt/stale reference from a genuine native divergence, so a
bad cache costs real investigation time and could block a ladder step indefinitely.

Cheap guard: `actor_parity` (or the gate) could assert the built package's surviving actor set equals
the expected first-N trunk prefix before comparing, and refuse a cache whose actor set isn't a
prefix. Would have caught this immediately.
