+++
priority = "p3"
kind = "finding"
summary = "games.<name>.ignore_props config exists but no verb ever passes it to run_materialize"
+++

# `ignore_props` config exists but no verb wires it to `run_materialize`

Found chasing a `level photo --game` comparison shot for a GUI lighting investigation.

`config.py`'s `Substrate.ignore_props` and `cli/resources.py`'s `ignore_props_for(project)` are
fully implemented, and `apply.py::run_materialize` accepts an `ignore_props` kwarg and uses it
correctly in its post-verify compare. But `ignore_props_for` has no callers anywhere in
`uedcli/cli/*.py`, and `preview_game.py::materialized_dx` (the `level photo --game` path) calls
`run_materialize(...)` without passing `ignore_props` at all. Grepped every `run_materialize(`
call site outside tests -- only the one in `preview_game.py`, unwired.

Net effect: setting `ignore_props` in `~/.uedcli/config.toml` (e.g. `["Engine.Actor.bOwned"]`,
literally the example in `Substrate.ignore_props`'s own doc comment) has NO effect on `level
photo --game` -- it still hard-fails the post-verify on any authored non-default `bOwned` (or
whatever other engine-added prop), even though the mechanism exists specifically for this case.

Reproduced live: `_scratch/perf/proj_dx`'s UNATCO trunk authors `BioelectricCell1` with
`bOwned=True`; `level photo --game --tree level/UNATCO` fails every time with
`post-verify mismatch: ... actor 'BioelectricCell1' differs on property bOwned` regardless of
`ignore_props` config, `--rebuild`, or a fresh container.

Not fixed here -- wiring `ignore_props_for(project)` into `materialized_dx`'s `run_materialize`
call (and checking whether `level materialize`'s own CLI command needs the same wiring) is a
small, real fix but outside a GUI session's scope; flagging for whoever owns `preview_game.py`/
the materialize CLI surface.
