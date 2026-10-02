+++
priority = "p2"
kind = "implement"
summary = "`brush poly find --facing` component-predicate grammar + brush-SET input"
+++

# `brush poly find --facing` predicate grammar — DONE

`--facing` now predicates on the face VISIBLE normal (`query.visible_normal`, inverse-transpose +
subtract flip): presets flat/wall/ramp + floor/ceiling, or AXIS:SPEC on nx/ny/nz (`;`/`,`/`..`).
`brush poly find` takes a brush SET (`nargs="+"`/`-`, warn-skip non-brush). New `facing_spec.py`;
`poly list`/find `--json` carry normal/orientation/role. Subtract-flip pinned by a regression on
`brush_subtract.t3d`.

Deferred (owner approval): the subtract-normal-flip fact for `dev/docs/unrealed/t3d.md` (pinned in
the regression test meanwhile) and a `docs/leveldesign/` retexture-by-orientation workflow.
