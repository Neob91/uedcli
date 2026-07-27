+++
priority = "p1"
kind = "owner-question"
summary = "Native materialize: M0 landed; wire apply.run_materialize as the SOLE path only after N-1 CSG parity"
+++

# Native materialize: M0 landed; wire apply.run_materialize as the SOLE path only after N-1 CSG parity

p1. The native glue (`uedcli/native/`) + Rust crate
(`uedcli-native/`) are in: a trivial carved-room `.dx` assembles, passes the always-on offline
self-check, and re-parses with both parsers; §6 gate 5 (Rust `model_write` == Python oracle) passes;
`fpoly.rs` is the N-1 start. **Deviation from spec §3/§4 ("editor DITCHED, native is the ONLY
path"):** `apply.run_materialize` still drives the editor. Flipping it now would make `level
materialize` non-functional for real (multi-brush) levels — the Rust CSG core (csg/build/passes/
zones/linecheck/light/paths) is N-1..N-5 and unbuilt — and would break the editor-mock materialize
tests. I did NOT rip out the working editor path with a non-functional replacement; the cutover is
gated on: (1) N-1 CSG reaching Tier-S parity (§6 gate 3), (2) N-3 full trunk-actor typed-property
serialization (`_trunk_to_actorspecs` currently carries class + Location only), (3) migrating
`test_apply`/`test_materialize*` off the editor mock. Confirm this sequencing is what you want.
