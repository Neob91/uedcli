+++
priority = "p?"
kind = "unknown"
summary = "`level preview --game` — WARM reusable container + live map delivery"
+++

# `level preview --game` — WARM reusable container + live map delivery

— BUILT + live-verified
2026-07-17 (spec `specs/2026-07-17-game-preview-warm-container.md`, 4 review rounds; decisions
2026-07-17 06:57/07:30/08:31). `--game` now delivers into ONE warm per-user container
(`uedcli-game-preview-<uid>`, flock + fingerprint-label reuse + inline idle watchdog); map delivery
is a hash-named (`materialized__…`/`copied__…`, dot-free/lowercased/capped) build written to
`uedcli/tmp/preview/`, bind-mounted at `/resources/preview`, POST-boot symlinked into Maps — the
SP-R-confirmed reload path (`spikes/2026-07-17-game-preview-reload-keying/`). Live: cold 79s → reuse
17s → idle self-death (exit 0). `.dx`+`.unr` inputs; `--keep-alive` pins; `--rebuild` mints a fresh
name. Post-build review gate (2 cold reviewers) resolved: `stop_game`/lock-hang bounding, `--game`
actor-typo → named error, docker-hang → named error not traceback, pin preserved across forced
reboots, skip-travel when already on the map, `.dx`/`.unr` ext-qualified stems, +16 warm-core
tests. **Remnants (→ inbox):** additive re-farm on reuse + dangling-symlink sweep (currently the
fingerprint reboots on overlay change instead); the boot-time `/resources/preview`-not-globbed
assertion.
