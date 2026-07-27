+++
priority = "p3"
kind = "chore"
summary = "Warm `--game` remnants (deferred from the 2026-07-17 build)"
+++

# Warm `--game` remnants (deferred from the 2026-07-17 build)

Not built, low-impact:
(1) **additive re-farm on reuse** + dangling-symlink sweep — currently a project-overlay change
trips the fingerprint and reboots (correct but heavier than an in-place re-farm), and a NEW base
map appearing mid-session isn't picked up until a reboot; (2) the **boot-time assertion** that
`/resources/preview` never enters `Paths`/`r*` (today it's structurally true — leading `p`, farm
globs only `r*` — so the assertion is belt-and-suspenders). *(The `--map` same-content-different-
extension clash was FIXED in the review gate — `copied_map` now carries the ext into the stem.)*
See `specs/2026-07-17-game-preview-warm-container.md`.
