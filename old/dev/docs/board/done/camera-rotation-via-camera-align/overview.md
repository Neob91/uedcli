+++
priority = "p?"
kind = "unknown"
summary = "Camera rotation via `CAMERA ALIGN`"
+++

# Camera rotation via `CAMERA ALIGN`

— perspective `CAMERA ALIGN NAME=<actor>` ADOPTS the
named (point) actor's full rotation (pitch/yaw/roll); the pure-console, no-mouse rotation setter
(pose a `Light`, `SELECTNAME`, `CAMERA ALIGN`, delete). RMB-drag also rotates (scriptable). The
earlier "preserves rotation" claim was corrected 2026-06-20. (Was wired as the VNC-era `level
preview --rotate`; that flag is gone — the same `CAMERA ALIGN` pose now drives the
editor-screenshot `level preview` renderer, above.) See `unrealed/commands.md` `CAMERA ALIGN`.
