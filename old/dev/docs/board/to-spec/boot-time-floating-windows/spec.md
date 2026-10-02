# Spec — boot-time floating windows cover the panes

## Goal

Stop the editor's boot-time floating windows (the Log Window, and the Textures/Master browser) from
painting solid black over the viewport panes, per the permanent fix in `unrealed/rendering.md`
("Perspective pane black" §2).

## Current state

- `uned/entrypoint.sh:99` launches the editor with `-log`, which spawns the floating Log Window.
- `uned/UED22/UnrealEd.ini` has 7 `[* Browser]` sections (Actor/Group/Music/Sound/Texture/Mesh at
  `X=516,Y=259`; Master at `X=508,Y=185`) — all on-screen, so a floated browser overlaps the panes.
- Today the black windows are only shoved aside by a runtime `wmctrl` sweep (`driver.dexec_bash`),
  re-run per shot because `MAP IMPORTADD` re-raises them.

## Approach

Move the fix to boot so no window ever floats over the panes:

1. `uned/entrypoint.sh:99` — drop `-log` from the wine launch (removes the Log Window).
2. `uned/UED22/UnrealEd.ini` — set `X=2000`, `Y=2000` on all 7 `[* Browser]` sections.
3. Rebuild the image.

Safe wrt log parsing: `qualify`/`driver.read_log_since` read `/opt/UED22/Editor.log` (driver.py:22),
which the editor writes on its own — not the `-log` console window — so dropping `-log` does not
affect OBJ DEPENDENCIES / loaded-class parsing.

Keep the runtime `wmctrl` sweep: `MAP IMPORTADD` can still re-raise a browser mid-session, so the boot
fix reduces but does not replace it (rendering.md already says this).

Note on the title's "boot-time `xmessage`": the entrypoint spawns no `xmessage` at boot. The only
`xmessage` is the runtime GC-progress dialog already dismissed by `driver.dismiss_blocking_dialog`
(driver.py:540). This part of the item looks mis-described; dropping `-log` does not touch it.

## Test

None practical (container-image behavior). Optional: a doc/ini assertion that every `[* Browser]`
sits at 2000/2000.

## Open questions

None.
