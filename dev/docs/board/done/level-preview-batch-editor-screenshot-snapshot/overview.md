+++
priority = "p?"
kind = "unknown"
summary = "`level preview` — batch editor-screenshot snapshot renderer"
+++

# `level preview` — batch editor-screenshot snapshot renderer

— BUILT + **live-verified
end-to-end** 2026-07-06 (4 clean fresh-boot passes; `test_preview_integration.py`: two distinct
poses, mean-abs-diff 9.9 > 3.0, both bright mean ~146). `POS@ROT[:MODE][=NAME]` shot grammar +
rotation presets + `--out-dir`/`--mode`; per-command ephemeral editor grouped by mode (one boot
per mode via a full-window `[U2Viewport2] RendMap`/ShowFlags ini override); per shot: `CAMERA
ALIGN` pose → `ACTOR SELECT NONE` → `wmctrl` sweep → click-repaint → `driver.screenshot` → chrome
crop `(104,92,1596,1104)`. Modes shaded/lit/wire/zones/polys/skybox (radii deferred — ShowActors
enum value TBD, see the `level preview` modes item in `inbox.md`). **Replaces the old VNC `level preview --rotate` handoff.** Two
live-boot bugs found + fixed along the way: the override-ini bind source must be daemon-visible
(`.uedcli/tmp/`, not the sandbox-private `/tmp`), and `_wait_ready` must require a resolved
`window=<id>` (not the transient `window=<unresolved>` line). Recipe: `unrealed/rendering.md`
"Posed shots"; spec `specs/2026-07-06-uedcli-level-preview-snapshots-design.md`; decisions
2026-07-06 12:01/12:59/15:58.
