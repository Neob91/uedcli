# Spec: `brush build cylinder/cone --axis x|y|z`

## Goal

Add `--axis x|y|z` (default `z`) to `brush build cylinder` and `cone`, building the prism/cone
oriented along that axis directly — the vertices are generated rotated, so **no `Rotation` field is
emitted**. The common horizontal pipe/beam/duct then needs no `--rotate` and the obvious first
attempt just works, instead of the author having to guess which of pitch/yaw/roll lays a `+Z` prism
onto Y. The `--axis` name, semantics and `(u,v)`→world mapping are already settled on the
`extrude`/`revolve` generators; this adopts them unchanged.

## Current state

- `cylinder`/`cone` always build along `+Z`: `builders.py:239` (`cylinder`) and `:263` (`cone`) put
  the ring in XY at `z=±hz`, apex/height along Z.
- `extrude`/`revolve` already carry `--axis x|y|z` meaning "the world axis the profile plane is
  normal to" (`parsers/brush.py:275,296`), mapped by `_SWEEP_FRAMES` (`builders.py:327`) via
  `_uv_axes` (`:335`): `z → u=X,v=Y`; `x → u=Y,v=Z`; `y → u=Z,v=X`, cycled right-handed so one
  winding rule serves all three.
- `cylinder`/`cone` carry `--align-to-side` (`parsers/brush.py:166,181`), a bool converted to a
  half-segment `angle_offset` in degrees by `_align_offset_degrees` (`build.py:71`) and passed to the
  builder as `angle_offset=`.
- `--at` center-anchors the shape on **every** axis (`parsers/brush.py` `_common_build_opts`).
- `Rotation` is only ever set by `--rotate`, via `generators.apply_generator_rotate`.

## Design

Add `--axis x|y|z` (default `z`) to the `cylinder` and `cone` subparsers, and an `axis="z"` parameter
to `builders.cylinder`/`cone`. The builder puts the cross-section ring in the `(u,v)` plane and runs
height/apex along `w`, using the **same** `_SWEEP_FRAMES[axis]` table `extrude`/`revolve` use.
`--axis z` reproduces today's output byte-for-byte (`u→X, v→Y, w→Z`); `--axis x` lays the prism along
X (the horizontal pipe), `--axis y` along Y.

The orientation is baked into the vertices, so the emitted actor carries no `Rotation` field.
`--rotate` still stacks on top for any other orientation (it composes over the oriented vertices,
unchanged).

Composition:

- **`--align-to-side`**: composes trivially. It offsets the cross-section angle *within the `(u,v)`
  plane*, defined relative to the shape's own axis, so it is independent of `--axis`.
- **`--at`**: unchanged — the geometric centre on every axis.
- **`cube`**: no `--axis` (symmetric, N/A).
- **`sheet`**: keep its existing `--plane xy|xz|yz`; do **not** add `--axis` — a flat panel's natural
  orientation parameter is the plane it lies *in*, not an axis it is normal to, and `--plane` already
  does this job. (Owner question below.)
- **A free direction vector**: out of scope. `--rotate` covers any non-axis orientation, matching
  `extrude`/`revolve`, which also offer only `x|y|z`.

### Proposed CLI surface

`brush build cylinder --height H --radius R [--sides N] [--align-to-side] [--axis x|y|z] <common>`
and `brush build cone --height H --radius R [--sides N] [--align-to-side] [--axis x|y|z] <common>`,
adding one flag to each (all other flags unchanged):

```
--axis x|y|z   world axis the prism's long axis runs along — the axis its n-gon cross-section is
               NORMAL to (default z, the current +Z prism). Builds the vertices oriented directly and
               emits NO Rotation field, so a horizontal pipe/beam needs no --rotate. (u,v) map onto
               the other two world axes in right-handed cyclic order, matching extrude/revolve:
               z → cross-section in X,Y; x → Y,Z; y → Z,X. For any other orientation use --rotate.
```

(For `cone` the help says "the cone's long axis" / "base ring cross-section".)

## Edge cases & errors

- `--axis` outside `x|y|z` → argparse `choices` error, exit 2.
- `--axis z` (or omitted) → output identical to today (regression-pinned).
- `--axis` + `--align-to-side` and `--axis` + `--rotate` both compose; `--rotate` applies on top of
  the oriented vertices.
- No new off-grid behaviour: an axis-oriented cylinder has the same fractional ring vertices a `+Z`
  one always had; `--axis` itself introduces none, so no advisory is added.
- `--axis` is not a float dimension, so it needs no row in `_POSITIVE_BUILD_DIMS` and does not trip
  `test_every_builder_shape_declares_its_positive_dimensions`.

## Tests

- `brush build cylinder/cone --axis z` equals the pre-change golden (byte-identical).
- `--axis x`/`--axis y` produce a prism/cone whose long axis is X/Y (bbox check) and emit **no**
  `Rotation` prop.
- `--axis x --align-to-side` puts a flat cross-section face on an axis in the `(u,v)` plane.
- `--axis y --rotate …` composes (rotation on top of the oriented vertices).
- Help text present and self-explanatory (covered by `test_help_completeness`).

## Open questions

- **`sheet`**: add `--axis`, or keep `--plane xy|xz|yz`? (`questions/sheet-axis-or-plane.md` —
  recommend keep `--plane`.)
