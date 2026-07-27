+++
priority = "p2"
kind = "unknown"
summary = "M0 native `.dx` game-load smoke — what's needed (not done this run)"
+++

# M0 native `.dx` game-load smoke — what's needed (not done this run)

p2. The M0 box
  (`materialize.build_carved_box_package`, written by the test to `_scratch/m0_box.dx`) passes the
  offline self-check + both parsers, but was NOT loaded in-game (the running containers are dev
  shells/dind, not a booted headless DeusEx on :7777). To close: (1) drop the `.dx` in the game's
  `Maps` search path; (2) boot headless DeusEx (uplayctl-style) and `open m0_box.dx`; (3) assert boot
  to :7777 with no load error, the player spawns at `PlayerStart0`, and a `Screenshot` renders
  non-black. Caveats the M0 box will expose first: surfs are UNTEXTURED (`texture_ref=0` → renders
  black even if it loads — add a texture import via `pkgref` before judging render), and the actor
  set carries class + Location only (N-3 typed-prop serialization). This is the §6 gate-4 game-load
  smoke, first real test of from-scratch synthesized values.

<!-- ── AI brainstorm (2026-07-16, "uedcli:creative" session) — un-triaged idea capture;
     checked against every board queue for duplicates before writing. Grouped by theme. ── -->
