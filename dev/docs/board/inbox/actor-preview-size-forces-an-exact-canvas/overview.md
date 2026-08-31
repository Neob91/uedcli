+++
priority = "p?"
kind = "debug"
summary = "actor preview: --size forces an exact canvas instead of a max; framed geometry can touch edge locator labels"
+++

# actor preview: --size forces an exact canvas instead of a max; framed geometry can touch edge locator labels

Found while brainstorming the CSG wire palette (`actor preview --faces wire --brush-colors csg`),
comparing `--view iso` against `--view top`.

- `--size` is applied as a forced exact canvas (e.g. `--size 900` always renders 900x900), not a
  max. When the framed content's aspect is far from square (e.g. a `--view top` scene wider than
  it is deep), most of the canvas is empty margin. The renderer should shrink whichever dimension
  the content doesn't need, treating `--size` as an upper bound.
- Not enough padding between framed geometry and the edge locator-cell labels (`A`-`L` / `1`-`12`)
  — geometry can render right up against them.
- No visual separator between the locator-cell ruler (the lettered/numbered header row and gutter
  column) and the actual scene area — they should have a clear border between them so the ruler
  reads as chrome, not part of the geometry.
