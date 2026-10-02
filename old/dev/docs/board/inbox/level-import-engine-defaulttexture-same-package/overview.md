+++
priority = "p1"
kind = "debug"
summary = "level import: Engine.DefaultTexture (same-package class) fails author-time texture validation"
+++

# level import: Engine.DefaultTexture (same-package class) fails author-time texture validation

Owner asked for this at p0; board's priority vocab tops out at `p1` (highest), so filed there.

## Symptom

`level import` (and any other author-time ingest path through `uedcli/cli/ingest.py`'s
`validate_ingest_actors`) rejects a brush face textured `Engine.DefaultTexture` with `texture not
found: Engine.DefaultTexture — no Texture of that name on the package path (author-time
validation)`, even though the export is real: `Engine.u` export 4022, class `Engine.Texture`,
`outer=0` (top-level in the package).

Reproduced importing an external Deus Ex mod map, `Maps/20_Downtown.dx` from
`git@github.com:neob91/dx_lum.git` (not part of this repo) — 6 of ~5859 actors' brush faces
reference it and fail.

## Root cause

`uedcli/utexture.py`'s `class_fqcn_of_export(pkg, i0)` only resolves a class's fully-qualified name
when the class is an IMPORT from another package. When the object's class is defined in the SAME
package as the object itself (`Texture` the class and `DefaultTexture` the instance both live in
`Engine.u`), it returns `None` ("not a texture, skip") — so `textures(pkg, class_index)`'s widened
`Engine.Texture`-descendant match never sees it.

The obvious fix — delegate to `Package.object_path()`, which already walks both the import case and
the same-package-export case — does NOT work as a one-liner: `utexture.py` has its OWN, separate,
more minimal `Package` class (not the one in `uedcli/upackage.py`), which has no `object_path` and
does not track the package's own name/stem at all. A real fix needs to thread the package's name
through `class_fqcn_of_export`/`textures()` and their call sites inside `TextureResolver`.

## Status

A subagent was dispatched to implement the real fix (thread package name through, add a regression
test, run `bin/test`). Last checkpoint: full suite still running. Uncommitted in this worktree
(`megagrant-demo`) as of filing — check `git status`/`git diff -- uedcli/utexture.py` before
assuming it's done.

**Not part of this issue** — a separate, deliberate, temporary, env-gated hack sits in
`uedcli/mapimport.py` (`UEDCLI_UNSAFE_SKIP_UNRESOLVED_ACTOR_CLASSES`, class-resolution bypass) and
`uedcli/cli/ingest.py` (same env var, texture-resolution bypass) for a DIFFERENT, unrelated problem
(the `dx_lum` map's `LUM_Core` mod classes can't be compiled in this sandbox). Those are marked
"not for commit" in-line and should be reverted independently of this fix, not folded into it.
