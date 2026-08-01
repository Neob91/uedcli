# Does `brush build sheet` get `--axis`, or keep its existing `--plane xy|xz|yz`?

## Context

`cylinder`/`cone` are gaining `--axis x|y|z` (the axis the cross-section is normal to), matching
`extrude`/`revolve`. `sheet` already takes `--plane xy|xz|yz` for its orientation. The item flagged
"sheet?" as open.

Options:

- **Keep `--plane` on sheet (recommended).** A flat panel's natural parameter is the plane it lies
  *in*; a cylinder's is the axis it runs *along*. These are genuinely different questions, and
  `--plane` already reads well for a sheet. The mild cost: two orientation spellings across the build
  family (`--plane` for sheet, `--axis` for the four others).
- **Replace with `--axis` on sheet too.** One orientation vocabulary across every `brush build`
  shape. But `--axis z` for "a panel in the XY plane" is a step removed — the author names the normal,
  not the surface — and it drops the natural two-axis name for a flat thing.

Recommendation: keep `--plane` on sheet. Add `--axis` to `cylinder`/`cone` only.

## Answer

<!-- Empty = open. -->
