# Plan: `brush build cylinder/cone --axis x|y|z`

Build in a feature worktree (`andrzej/p2/brush-cylinder-cone-axis`), one squash-merged commit.
Slices are ordered; each lands with its tests green before the next.

## Slice 1 — builders take an `axis` and orient through the sweep frame

- `builders.cylinder`/`cone` (`builders.py:239`, `:271`) gain a keyword `axis: str = "z"`. Build the
  ring in the profile plane and run height/apex along `w`, mapping each vertex and each `_face`
  outward direction through `_SWEEP_FRAMES[axis]` via `_sweep_point` (`builders.py:342`, `:358`) —
  the same frame `extrude`/`revolve` use. `axis="z"` is the identity frame, so the emitted vertices
  are byte-identical to today.
- Reject a bad axis via `_uv_axes` (`builders.py:350`), which already raises `GeometryError` naming
  the value — reuse it, do not re-implement.
- The four in-repo direct callers of `cylinder`/`cone` (parity goldens, degrees-valued
  `angle_offset`) keep calling with no `axis`, so the default preserves them.

Tests (`tests/test_builders.py`, and `tests/test_parity*`/golden suites if they call these directly):
- `cylinder(...)`/`cone(...)` with no `axis` == the pre-change golden brush (byte-identical polys).
- `axis="x"`/`"y"` produce a brush whose long axis is X/Y (bbox spans the chosen axis by `height`,
  cross-section in the other two).
- `axis="q"` raises `GeometryError` naming `q`.

## Slice 2 — CLI surface: `--axis` on `cylinder`/`cone`, wired through dispatch

- Add `--axis`, `choices=["x","y","z"]`, `default="z"`, to `bcyl` and `bcone`
  (`cli/parsers/brush.py:166`, `:181` area) with the help text from spec §"Proposed CLI surface"
  (cone's help says "the cone's long axis" / "base ring cross-section"). No other flag changes;
  `sheet` keeps `--plane`, `cube` gets nothing.
- Pass `axis=args.axis` in `_build_brushes` for `cylinder`/`cone` (`build.py:173-178`). `--axis`
  composes with `--align-to-side` unchanged (the offset is applied within the profile plane, before
  the frame maps it), and with `--rotate` (rotation stacks on the oriented vertices, unchanged).
- `--axis` is not a float dimension → no row in `_POSITIVE_BUILD_DIMS`, so
  `test_every_builder_shape_declares_its_positive_dimensions` is unaffected.

Tests (`tests/test_generators.py`/`test_cli.py`):
- `brush build cylinder --axis z` (and omitted) == the pre-change generator golden T3D, and emits
  **no** `Rotation` prop.
- `--axis x`/`--axis y` → prism/cone oriented along X/Y (bbox), no `Rotation` prop.
- `--axis x --align-to-side` → a flat cross-section face lies on an axis in the `(u,v)` plane.
- `--axis y --rotate 0,8192,0` → rotation composes on top of the oriented vertices.
- Bad `--axis w` → argparse `choices` error, exit 2.
- Refresh `tests/fixtures/parser_baseline/{help.json,action_tree.json}` (the two new `--axis` flags).

## Slice 3 — user docs

- `docs/usage.md:673-674`: add `[--axis x|y|z]` to the `cylinder`/`cone` synopsis lines; note it
  orients the prism directly (no `--rotate`), same `--axis` meaning as `extrude`/`revolve`
  (`:678-679`). Keep it short.
- Scan `docs/leveldesign/` for a "horizontal pipe needs `--rotate`" claim and update it to
  `--axis` if present (grep `--rotate` under the brush-build recipes). No new craft knowledge — this
  is tool-behavior documentation, so no owner approval needed.

## Verify

- `bin/test -k "builder or generator or cli"` green; formatter/linter/type-checker on touched files.
- Exercise live: `brush build cylinder --height 256 --radius 32 --axis x | actor add -` then
  `actor find --name Cylinder* | actor bbox -` shows the long axis on X and `actor show` carries no
  `Rotation`.
- One subagent reviews `git diff base...HEAD` (must read `dev/docs/direction/generators.md`,
  `dev/docs/unrealed/t3d.md`, `CLAUDE.md`); fix confirmed findings; re-test.
- `git mv` the item to `done/`, cut `overview.md` to one line, squash-merge.
