+++
priority = "p0"
kind = "implement"
summary = "uedcli serve rebuilds the full class/schema index on every request -- makes Load/Rebuild/scene slow, worst on a cold process"
+++

# GUI serve rebuilds ClassIndex on every request

Owner-observed: a plain Reload took ~30-60 seconds on a freshly-restarted `uedcli serve` process.
Root-caused live during this session, filed as top priority per owner request.

## The mechanism

`uedcli/serve/app.py`'s `_scene_inputs(project)` builds `(search_files, index, defaults)` --
`index` is the schema-aware class/mover resolver, built fresh every call via
`packages.schema_resolver()`/`resources.mover_index()`, which decode discovery schema for every
`.u` package on the composed search path. `_scene_inputs` is called on EVERY `/load`, `/rebuild`,
`/scene`, `/atlas`, and `/lightmap` request -- its own docstring calls this "cheap: no CSG solve
here," which is only true relative to a CSG solve, not in absolute terms.

There IS a persistent on-disk schema cache (`uedcli/schema_cache.py`, on by default,
`UEDCLI_SCHEMA_CACHE=off` to disable), but it still has to touch and validate every package file's
freshness on each call. Worst case is a just-restarted process: no in-memory memo yet, so the first
real request after a restart pays the full per-package decode cost with a cold cache -- this is
what produced the ~30-60s observed Reload.

## Same root cause as an existing, different-command item

`dev/docs/board/inbox/materialize-rebuilds-classindex-twice-per/overview.md` documents the identical
"ClassIndex rebuilt redundantly" pattern in `level materialize`'s own code path (`uedcli/apply.py`).
That item is about the CLI's `run_materialize`/`_assembly_level`; this item is the GUI serve
process's own instance of the same underlying inefficiency -- a different call site, same root
cause (no per-process memoization of the built `ClassIndex`/resolver objects across requests).

## What to do

Memoize the built `index`/`schema_resolver`/`mover_index` objects at the process level (not just the
on-disk schema cache), invalidated only when actually needed (a `--project`'s games config changes,
which `_scene_inputs`'s own docstring says is rare -- "a one-time project setup"). The docstring's
stated reason for recomputing every time ("so a `--project`'s on-disk games config can change
without a `serve` restart") is a real but rare case being paid for on every single request,
including the hot path (`/scene`, called after every Load/Rebuild/pan/zoom-triggered refetch).
Consider a cheap staleness check (config file mtime) gating a full rebuild, rather than
unconditionally rebuilding every time.

Cross-check with the sibling item's own note: "`speed-up-the-offline-test-suite` (to-spec) parked a
question on splitting `schema_cache.py`'s disk-cache/in-process-memo switch" -- a real
in-process memo here would need to interact correctly with that switch, not fight it.

## Where to look

`uedcli/serve/app.py`'s `_scene_inputs` (and every one of its 5 call sites: `/load`, `/rebuild`,
`/scene`, `/atlas`, `/lightmap`), `uedcli/schema_cache.py`, `dev/docs/board/inbox/
materialize-rebuilds-classindex-twice-per/overview.md` (the sibling CLI-side item).
