+++
priority = "p3"
kind = "debug"
summary = "wall/floor spec doc predates the editor-projection rewrite, cites dead functions"
+++

# wall/floor spec doc predates the editor-projection rewrite, cites dead functions

`to-spec/texture-alignment-solver-poly-align-planar-wall/spec.md` still describes the OLD
seed-centroid implementation (`polyalign._coplanar_align`, `_ring_align`) and says "UnrealEd `POLY
TEXALIGN` parity is deliberately NOT matched ... out of scope here."

That's stale. Commit `252c4ad3` ("brush poly align: wall|floor|run subcommands, editor projection,
connected run") replaced `_coplanar_align`/`_ring_align` with `_projected_align`/`_run_align`, which
DO reproduce the editor's `FLOOR`/`WALLX`/`WALLY` `POLY TEXALIGN` family, "pinned against the
measured golden" (commit message; `dev/docs/unrealed/texalign.md`; `test_polyalign.py` around line
135). Found while investigating the `align-wall-skews-texture-on-45deg-diagonal-faces` board item —
the skew it reports on diagonal faces turned out to be this exact, tested, intentional
`|proj|`-density behavior, not a bug (see that item's own thread for the fuller writeup).

Needs the owner's yes to reword (`dev/docs/direction/` sibling rule extends to any `dev/docs/`
edit) — filed here rather than edited directly.
