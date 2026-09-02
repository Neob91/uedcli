+++
priority = "p3"
kind = "owner-question"
summary = "commands.md: UCC ExecCommandlet stdout carries the MAP REBUILD warning channels"
+++

# commands.md: UCC ExecCommandlet stdout carries the MAP REBUILD warning channels

`unrealed/commands.md` is owner-gated, so this is a proposed addition awaiting a yes. The fact is new
and pinned by `spikes/2026-08-03-ucc-log-bsp-warnings/` (+ its `test_ucc_log_d0_channels.py`); the
`headless-materialize` spike noted `Nodes:` on stdout but not the D0 warning channels specifically.

Proposed text (append to the `Objects / packages / assets` UCC material, or the build-pipeline
section) — verbatim:

> **`UCC.exe Editor.ExecCommandlet <script>` streams the `MAP REBUILD` warning channels to stdout**
> 🔬 (2026-08-03, `spikes/2026-08-03-ucc-log-bsp-warnings/`). Running a load/build script headless
> (no GUI, no X) prints the full engine log to the process's stdout in order — including the
> BSP-build diagnostics the GUI editor buffers in `Editor.log`: `Processed %i T-points, linked:
> %i/%i sides` (unlinked = total − linked ⇒ HoM crack), `FPoly::Finalize: Not enough vertices (%i)`
> (a dropped face), `Nodes: %i -> %i`, `Portalized: … %i leaves, %i nodes`. Live-captured: an open
> box gave `Processed 4 T-points, linked: 16/20 sides`; a degenerate face gave `FPoly::Finalize: Not
> enough vertices (0)`. So the D0 drop-warning parser reads UCC stdout directly, with none of the GUI
> path's 4 KB-buffer flush discipline (no `OBJ LIST CLASS=Class` flush, no `assert_flushed`).

Related: this is the log-source evidence for board item `bsp-issue-detector` (its overview records
the GO + recommendation).
