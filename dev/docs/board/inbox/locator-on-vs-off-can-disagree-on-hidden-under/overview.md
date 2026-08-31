+++
priority = "p?"
kind = "unknown"
summary = "--faces textured: locator on/off can report a different `hidden` for the same actor"
+++

# locator on vs off can disagree on `hidden` under `--faces textured`

Found reviewing `locator-cells` (board item `remove-numbering-grid-from-level-actor-preview`,
`uedcli/preview.py` `_collect_cells`/`render_brushes_pgm`).

`--no-locator-cells` drops `_framing`'s `gutter` reserve to 0 (spec §3.2), which changes `to_pxf` for
every point in the pane. Under `--faces textured` a filled render's `hidden` comes from
`_face_is_occluded(zbuf, ...)`, which depth-tests at PIXEL positions — so a different `to_pxf` can move
which face wins a given pixel, changing `_face_is_occluded`'s verdict and therefore `hidden`, for a
scene that is otherwise unchanged.

Measured: 90 rendered locator-on/off pairs across a size/view sweep, 3 divergences. Example:
`size=160 view=top`, one actor reports `hidden=False` with the locator on and `hidden=True` with it
off, same scene, same actors.

Under `--faces wire`, `_collect_cells`'s `drew` set is `set(geom.actor_points)` — every actor with
points, independent of `to_pxf` — so this does not reach `wire`. `--json`'s reduced `{hidden}` shape
(spec §3.4) is only exercised by tests under `wire`, where the two modes agree; the divergence is real
but untested by anything shipped in that item.

Each answer is honest about the image that render actually wrote — this is not a bug in either
render, and no code changed to "fix" it. Whether cross-mode `hidden` stability is a real requirement is
the owner's call: see the `cross-mode-hidden-stability-under-faces-textured` question on board item
`remove-numbering-grid-from-level-actor-preview`.
