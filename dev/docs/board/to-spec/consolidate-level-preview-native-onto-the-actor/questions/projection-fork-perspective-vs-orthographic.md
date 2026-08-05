# The projection fork — what does the offline tier become?

This is the central decision; everything else follows from it.

`level preview --native` renders **freely-posed perspective** whole-level stills (the shared SHOT
grammar: `at:X,Y,Z;rot:P,Y` / `look:@Actor` / `orbit:@Actor;radius;azimuth;elev`, plus `--fov`).
`actor preview`'s renderer (`preview.py`) is an **orthographic schematic** — fixed top/front/side/iso
panes, no camera, no pose. Keeping actor preview's logic therefore cannot be a drop-in swap.

Pick one:

- **(a) Teach `preview.py` a perspective camera.** Add a perspective projection + the SHOT pose
  grammar to the Python rasterizer, so the offline `level preview` tier keeps freely-posed
  whole-level shots but drawn by `preview.py` (concave-correct fill, exit-2 on missing texture,
  faithful CSG core). Most work; preserves every current `--native` capability and kills the bugs.
- **(b) Offline tier becomes orthographic-only.** Drop freely-posed perspective offline; `level
  preview` offline renders the whole level in `actor preview`'s ortho views (top/front/side/iso).
  Perspective stays available only via `--game`. Less work; a real capability loss (no offline
  perspective).
- **(c) Delete `--native` entirely.** No offline whole-level tier; whole-level offline is
  `actor preview <all-names>` (ortho), and perspective is `--game` only. Simplest; removes the most
  code; loses the fast offline perspective draft altogether.

Consideration to weigh: how often is the offline *perspective* draft actually used vs the ~1-minute
`--game` path, and vs an ortho schematic? If perspective offline is rarely the thing that unblocks
you, (b)/(c) buy a large code deletion.

## Answer

<!-- Empty = open. -->
