# Delete `texframe.tex_basis_default` and have `world_uv_frame` call `builders._tex_basis` directly, or keep it?

## Context

Raised while resolving round-1 review findings on S1 of `actor diagram --faces`. Not acted on: the
answer is the owner's, because it edits this spec, which has passed both review rounds.

`uedcli/texframe.py`:

```python
def tex_basis_default(normal):
    from .builders import _tex_basis
    return _tex_basis(normal)
```

Two spellings of one function are reachable: `texframe.tex_basis_default` (called only by
`texframe.world_uv_frame`) and `builders._tex_basis` (called by `polyalign.py:252`, `builders.py:170`,
four spike harnesses). The "public" wrapper has one caller inside its own module while the private
original is called directly from another module. `direction/conventions.md` rejects two ways to ask
one question.

Case for deleting: `world_uv_frame` calls `_tex_basis` directly; the wrapper adds no behaviour,
validation, or unit conversion.

Case for keeping (both real, both weak): (1) a named fallback seam — `de-containerization-follow-on-spec-items`
spec §5 ruled the missing/zero-axis fallback to be "a Python default matching `builders._tex_basis`",
and a named function makes that one symbol; but only `world_uv_frame` reaches it, so the seam protects
nothing sharing `world_uv_frame` doesn't already. (2) It localizes the `builders` import — with the
import function-local, importing `uedcli.texframe` loads 7 modules instead of 11; inlining into
`world_uv_frame` keeps that, so this argues for the function-local import, not the wrapper.

This spec's §6 code-shape table names `tex_basis_default` as one of the four symbols S1 moves into
`texframe.py`. Removing it amends §6's table, so it is not a silent delete.

## Answer

<!-- Empty = open. Write the decision here. -->
