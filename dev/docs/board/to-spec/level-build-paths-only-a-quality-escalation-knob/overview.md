+++
priority = "p2"
kind = "implement"
summary = "`level build` (paths only) + a `--quality` escalation knob"
+++

# `level build` (paths only) + a `--quality` escalation knob

`LIGHT APPLY` folding into `level apply` is DONE 2026-06-21. `BSP REBUILD` quality args CONFIRMED
2026-06-23 (`LAME`/`GOOD`/`OPTIMAL`); `PATHS DEFINE`/`PATHS BUILD LOWOPT`/`HIGHOPT` CONFIRMED.
Still open: wire a `--quality` knob into `level apply` (`BSP REBUILD LAME` default, `GOOD`/
`OPTIMAL` on demand) and implement `level build` as a standalone paths-only verb. No longer
spike-gated.
