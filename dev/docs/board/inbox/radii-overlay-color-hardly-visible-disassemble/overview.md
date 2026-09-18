+++
priority = "p1"
kind = "investigate"
summary = "radii overlay is hardly visible -- its color was borrowed from the now-banned third-party UE1 source, never RE'd against our binary; disassemble and fix"
+++

# Radii overlay hardly visible -- color needs real RE

Owner report (2026-09-18): "Radii are hardly visible in radii view. The color must be off."

## Root cause, confirmed by code read

`web/src/scene/RadiiOverlays.tsx`'s `RADII_COLOR = new THREE.Color(163/255, 0, 0)` -- a dark red,
`(163,0,0)`. Per its own comment, this value came from `Engine/Config/Default.ini`'s `C_ActorArrow`
in a **third-party UE1 source repository**, per `GUI-PARITY.md`'s own citation. That source is now
BANNED for this project (`CLAUDE.md`'s "Documentation" section, owner ruling 2026-09-18) -- RE
evidence must come only from disassembling `uned/UED22/`'s own binaries. This value was flagged even
at the time as "not yet confirmed against this project's actual DeusEx-customized `Editor.dll`/its
own installed `.ini`" (`GUI-PARITY.md`'s "Radii overlay colors" section) -- that caveat just turned
out to matter: a dark, semi-transparent red overlay is plausibly exactly why it's hard to see against
typical scene geometry.

## What to do

1. Disassemble the real `uned/UED22/Editor.dll` (and/or its shipped `.ini`, if this project's own
   substrate has one checked in or extractable, per `dev/docs/unrealed/extracting-from-dll.md`'s
   method) to find the REAL `C_ActorArrow` (or whatever the actual color source is -- confirm the
   right constant, don't assume the name carries over unverified) value this build actually uses.
   Live-capture (screenshot a real radii overlay in an isolated UED22 container, per
   `dev/docs/unrealed/rendering.md`) if that's cheaper/more conclusive than a static binary read for
   pinning the exact color.
2. Mark the finding's confidence tier per `GUI-PARITY.md`'s convention and correct its "Radii overlay
   colors" section -- the current text there also cites the banned source and needs the same
   retraction-and-redo treatment other GUI-PARITY findings got today.
3. Replicate the confirmed real color/opacity in `RadiiOverlays.tsx`, replacing the current
   `(163,0,0)` guess.
4. Live-verify the fix in this GUI with real screenshots (select an actor with radii shown, confirm
   it's now clearly visible against typical scene geometry) -- this campaign's established rigor, not
   a code-reasoning-only claim.

## Where to look

`web/src/scene/RadiiOverlays.tsx` (`RADII_COLOR`, `OVERLAY_OPACITY`), `GUI-PARITY.md`'s "Radii
overlay colors" section (current, now-suspect findings to correct).
