+++
priority = "p3"
kind = "owner-question"
summary = "texframe.tex_basis_default is a one-line pass-through to builders._tex_basis, which polyalign already calls directly — deleting it is a spec change."
+++

# Should `tex_basis_default` exist at all?

**Raised while resolving round-1 review findings on S1 of `actor preview --faces`. Not acted on: the
answer is the owner's, because it edits a spec that has passed both review rounds.**

## What the code looks like

`uedcli/texframe.py`:

```python
def tex_basis_default(normal):
    from .builders import _tex_basis
    return _tex_basis(normal)
```

Two spellings of one function are reachable in the tree:

| spelling                     | callers                                                         |
|------------------------------|-----------------------------------------------------------------|
| `texframe.tex_basis_default` | `texframe.world_uv_frame` only                                  |
| `builders._tex_basis`        | `polyalign.py:252`, `builders.py:170`, four spike harnesses     |

The "public" wrapper has exactly one caller, inside its own module, while the private original is
called directly from another module. `direction/conventions.md` rejects two ways to ask one question.

## The case for deleting it

`world_uv_frame` calls `_tex_basis` directly and the wrapper goes. It adds no behaviour, no
validation, no unit conversion.

## The case for keeping it

Two reasons, both real, both weak:

1. **A named fallback seam.** Board item `de-containerization-follow-on-spec-items` spec §5 ruled the
   missing/zero-axis fallback to be "a Python default matching `builders._tex_basis`", and a named
   function makes that one ruling one symbol. But today only `world_uv_frame` reaches it, so the seam
   protects nothing that sharing `world_uv_frame` does not already protect.
2. **It localizes the `builders` import.** With the import inside the function body, importing
   `uedcli.texframe` loads 7 `uedcli` modules instead of 11, and `preview.py`'s closure drops the same
   3 (`builders`, `geometry`, `profile`) — measured 2026-07-29. Inlining `_tex_basis` into
   `world_uv_frame` keeps that: the function-local import just moves there. So this argues for the
   function-local import, not for the wrapper.

## Why this needs the owner

Board item `four-actor-preview-faces-rulings-need-a-durable` spec **§6**'s code-shape table names
`tex_basis_default` as one of the four symbols S1 moves into `texframe.py`. Removing it is a change to
that spec, not a cleanup, so it is not a silent delete.

**Decision needed:** delete `tex_basis_default` and have `world_uv_frame` call `builders._tex_basis`
directly (keeping the import function-local), amending §6's table — or keep it as it is.
