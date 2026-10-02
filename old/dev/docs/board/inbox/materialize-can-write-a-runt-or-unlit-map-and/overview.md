+++
priority = "p2"
kind = "implement"
summary = "materialize can emit a runt or unlit map and exit 0; add a post-build sanity floor + report baked-lighting and size."
+++

# materialize can write a runt or unlit map and report success

Source: `dev/docs/spikes/levelbuild-friction/` finding #1b. `--no-verify` (and some success paths) can
write a tiny or unlit `.dx` and exit 0, so a broken build reads as a good one. Related flag already
noted, unowned, in board item `spec-review-round-1`.

Fix (not just verify — owner ruling): (1) a post-build sanity floor that FAILS the build when output is
implausibly small or carries no lighting bake, naming the value; (2) materialize REPORTS whether
lighting baked and the output size, so success is legible.

Watch: the floor must not false-fail a legitimately tiny map — calibrate the threshold against a known
small good build, not a guessed constant.
