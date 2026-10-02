+++
priority = "p2"
kind = "chore"
summary = "Crashed golden builds orphan uned-wp volumes until the host disk fills"
+++

# Crashed golden builds orphan uned-wp volumes until the host disk fills

Hit live 2026-09-03 (built-parity localization round): a TrainingFinal prefix-search step died with
`no space left on device` seeding a new `uned-wp-*` wineprefix volume — the host was at 100% with 7
orphaned `uned-wp-01a0*` volumes (~4 GB) left by earlier crashed/killed ephemeral editor runs
(`build_ued_golden.py` and kin clean up on success, but a hard failure or kill leaves the volume).
Each ephemeral run seeds ~800 MB from the baked prefix, so a few crashes fill a small host.

Recovered by `docker volume rm` of the orphans (checked against `docker ps -a` first) +
`docker builder prune -f`. Fix ideas: `ensure_editor`/`stop_editor` (or a small reaper in
`bin/`) removes `uned-wp-*` volumes with no matching container at spin-up; or trap-based cleanup in
the golden-build harnesses. Leave `uned_wine-prefix` (persistent editor) and `uned-wp-stub-*`
untouched.
