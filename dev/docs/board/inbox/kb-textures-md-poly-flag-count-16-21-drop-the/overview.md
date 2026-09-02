+++
priority = "p3"
kind = "owner-question"
summary = "[OWNER — confirm] kb/textures.md poly-flag count 16→21 (drop the five (no --add-flag) tags)"
+++

# [OWNER — confirm] kb/textures.md poly-flag count 16→21 (drop the five (no --add-flag) tags)

`add-the-missing-surface-poly-flags` (now in `done/`) made `bigwavy`/`smallwavy`/`lowshadowdetail`/
`brightcorners`/`highshadowdetail` settable via `--add-flag`. `dev/docs/unrealed/leveldesign/kb/textures.md`
still claims uedcli "exposes 16 flag names" and tags those five *(no `--add-flag`)*. That is now wrong,
but the file is craft/owner-gated so it was not edited. This is a correctness follow-up, not a merge
blocker: the directional agreement test (`test_flag_catalog.py`) passes on the code alone.

Proposed diff (needs the owner's yes before applying):

- `:30-32` — replace "uedcli exposes 16 flag names via `--add-flag`; `Bright Corners`, `Small/Big
  Wavy`, and `High/Low Shadow Detail` are real poly-flags not in that set (they need a raw bit
  write), tagged *(no `--add-flag`)*." with "uedcli exposes all 21 flag names below via `--add-flag`."
- `:44-49` — drop the *(no `--add-flag`)* tag from the five rows (`Bright Corners`, `Small Wavy`,
  `Big Wavy`, `High Shadow Detail`, `Low Shadow Detail`).

Not to touch: the stale `dev/docs/spikes/bspspike/flags.py:29-31` table has different (wrong) bit
values — a grep hazard, not the source of truth.
