+++
priority = "p3"
kind = "debug"
summary = "architecture.md's Surface texture alignment section predates the editor-projection rewrite"
+++

# architecture.md's Surface texture alignment section predates the editor-projection rewrite

`architecture.md` lines ~1867-1891 ("Surface texture alignment") still says `--wall`/`--floor`/
`--ring` are FLAGS (not subcommands), that `--fresh-frame` exists, and that uedcli's alignment
"is NOT a port of the editor's... anchoring on the seed face's centroid" for `--wall`/`--floor`.

All three are stale since commit `252c4ad3` ("brush poly align: wall|floor|run subcommands, editor
projection, connected run"): the modes are now subcommands (`wall`/`floor`/`run`/`one-tile`),
`--fresh-frame` was deleted, and `wall`/`floor` now DO reproduce the editor's `FLOOR`/`WALLX`/
`WALLY` `POLY TEXALIGN` family (world-axis anchored), pinned against the measured golden
(`dev/docs/unrealed/texalign.md`). Same root cause as, and found alongside,
`wall-floor-spec-doc-predates-the-editor` (the `to-spec/texture-alignment-solver-poly-align-planar-wall/spec.md` staleness).

This section will also need updating for the `align wall`/`align wall-pan` WALLDIR/WALLPAN rework
(board item TBD, in progress) — that work will need the owner's yes to touch this file anyway;
folding this staleness fix into the same approval is probably the efficient path.

Needs the owner's yes to reword — filed here rather than edited directly.
