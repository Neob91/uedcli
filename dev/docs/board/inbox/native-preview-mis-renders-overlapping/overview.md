+++
priority = "p1"
kind = "debug"
summary = "Native preview mis-renders overlapping subtractive DOORWAYS, and `doctor` says \"no issues\""
+++

# Native preview mis-renders overlapping subtractive DOORWAYS, and `doctor` says "no issues"

A doorway = a second subtract overlapping the room (or connecting two rooms). In
`--native` it renders as a wedge/partial opening with **magenta on the CSG-generated cut faces**
(missing-texture sentinel — those new faces inherit no texture even when `brush poly list` shows the
authored faces textured). Reproduced minimally (two rooms straddling x=0 + a through-wall subtract →
imperfect wedge opening, untextured=gray). So the DEFAULT feedback loop is unreliable for the single
most fundamental connective operation, with **zero warning**. Unknown whether it's a preview-only
artifact or a real build defect — disambiguating needs the `--game`/materialize tier the offline
loop can't reach. Root cause lives in the native CSG core / `preview_native` (owned by the
native-materialize line — COORDINATE, don't touch those files). Repro: `_scratch/doorprobe/`.
(Agent A + my repro.)
