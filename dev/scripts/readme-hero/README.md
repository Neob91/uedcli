# README hero generator

Regenerates the animated hero in the top-level `README.md`
(`docs/images/readme/build-synced.svg`).

```
dev/scripts/readme-hero/build-hero.sh [OUT.svg]   # default OUT: docs/images/readme/build-synced.svg
```

- `build-hero.sh` runs the real uedcli pipeline (build a room, clip its corners at
  45°, add a corridor, duplicate the room, add a semisolid column per room, rotate
  each) against a throwaway scratch level, rendering an `actor diagram` frame after
  each step.
- `render-synced-svg.py` assembles those frames plus a terminal transcript into one
  looping SVG, both panels driven off a single timeline so they stay in sync.

The commands shown in the SVG are the commands actually run, so the animation always
reflects real output. If you change a step in `build-hero.sh`, update the matching
line in `render-synced-svg.py`'s `rows` (and vice versa) — they are kept in lockstep
by hand.

Needs `bin/uedcli` built and the `dev/games` sample project present (not shipped
publicly). Actor names are auto-assigned per run and flow from the pipeline into the
shown commands, so a fresh run produces a consistent SVG.
