+++
priority = "p2"
kind = "docs"
summary = "architecture.md stale on cli/ layer; hidden import cycles; preview.py god module; D-label reuse"
+++

# architecture.md stale + structural debt the layering tests can't see

`dev/docs/architecture.md` edits need the owner's yes — this item captures the findings; the fix is a
proposal, not to be applied unasked.

1. **architecture.md stale on the CLI layer.** Lines ~62,132,790,1201 and the "Adding a verb"
   walkthrough (~1777-1790) describe a flat `cli.py` (argparse) + `dispatch.py` wiring "four mockable
   seams." Reality: a layered `cli/` package — `cli/main.py`, a routing-only `cli/dispatch.py`, a
   `cli/parsers/` tier — and the four seams (`_class_schema`/`_class_defaults`/`_struct_members`/
   `_enum_names`) live in `cli/resources.py`, not `dispatch.py`. CLAUDE.md mandates this doc as
   required reading for contributors AND subagents, so step 1 points at a file that doesn't exist.
   Highest-value fix (misdirects everyone).

2. **Hidden bidirectional lazy-import cycles**, uncaught by any layering test (which only gate
   `uprops/`, `propedit/`, `cli/`): `transform.py` ↔ `rotation.py` (function-local imports both ways,
   `transform.py:188,203,249` / `rotation.py:275,281,292,415`) and `schema_cache.py` ↔ `uprops`
   (`schema_cache.py:62-63` module-scope vs `uprops/uclass.py:217` lazy). Promoting either lazy import
   to module scope reintroduces an `ImportError` with nothing to catch it.

3. **`preview.py` is a 2290-line god module** (~2.4× the next largest), mixing rasterization
   primitives, face shading, a 2D box-packing decal subsystem, palette assignment, and annotation
   parsing in one flat file — no dependency gate can apply to its internals.

4. **Invariant D-label reuse.** architecture.md's global D1-D8 collides textually with a spec-local
   D1-D9 in `preview_game.py`'s header and a third `D4` at architecture.md:2550;
   `preview_game.py:213-214` uses bare `"D8"` colliding with the PrePivot invariant. Grepping `D8` to
   audit compliance surfaces two unrelated rules. Also: invariant D1 (read-back-gated selection) may
   describe retired editor-centric functionality — `Driver.selectname`/`select_none` have no
   non-test callers; worth an owner check on whether D1 still binds.

Proposals for 1 and 4 (doc edits) await owner approval; 2 and 3 are code refactors that can be
specced independently.
