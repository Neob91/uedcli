+++
priority = "p1"
kind = "debug"
summary = "GUI semisolid wire color is wrong -- bright green from the banned third-party source; owner says match preview.py's own deliberate coral"
+++

# Semisolid brush wire color wrong -- match `preview.py`/`level photo`

Owner report (2026-09-18): "We are rendering semisolid colors wrong. Check how `level photo` does
that."

## The mismatch, confirmed by code read

- `web/src/scene/selectionColor.ts`'s `CSG_WIRE_COLOR.semisolid = [127, 255, 0]` (bright green) --
  sourced from the third-party UE1 `Default.ini` this project's `CLAUDE.md` now BANS as GUI-PARITY
  evidence (`C_SemiSolidWire=(127,255,0)`).
- `uedcli/preview.py`'s `_CSG_PALETTE["semisolid"] = ((235, 120, 80), (125, 62, 40))` -- a warm
  coral, used by `level photo`/`actor diagram`/eval screenshots. Its own comment: "semisolid
  deliberately DIVERGES from UED's rose (223,149,157)... UED's semisolid and mover are both red/
  purple, told apart only by saturation -- a fragile cue. Coral (warm)" -- a REASONED, DELIBERATE
  style choice for this project's own 2D raster tools, not a literal UED22-parity claim.

This exact discrepancy was already flagged (but not resolved) in `GUI-PARITY.md`'s "Radii overlay
colors" Findings section today, while investigating a DIFFERENT color (`C_ActorArrow`) sourced from
the same now-banned `Default.ini` pull -- it just surfaced again, this time reported directly by the
owner from the live GUI.

## What to do

Owner's direct instruction: match `level photo`'s own value. Update `web/src/scene/
selectionColor.ts`'s `CSG_WIRE_COLOR.semisolid` to `preview.py`'s `(235, 120, 80)` (the front/vivid
value -- check whether the GUI's own color model has an equivalent use for the second, darker
`(125, 62, 40)` tuple, e.g. an unselected/back-face variant, and thread it through consistently if
so). This is a GUI-only scope match to this project's own established convention, same as the
already-closed "Brush wireframe selection color" item's scoping (not a claim about real UED22's
actual semisolid color, which stays a separate, still-open question if ever revisited).

Live-verify in the running GUI with a real screenshot of a semisolid brush's wireframe, confirming
the new color renders and is visually distinct from Mover's own wire color.

## Where to look

`web/src/scene/selectionColor.ts`'s `CSG_WIRE_COLOR`, `uedcli/preview.py`'s `_CSG_PALETTE` (read
value, don't touch preview.py itself -- this is scoped to the GUI only, matching the existing brush-
wire-color item's precedent).
