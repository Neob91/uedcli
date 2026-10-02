+++
priority = "p2"
kind = "implement"
summary = "Keep the addressable grid but rename it locator-cells, make it opt-out, and draw it fainter."
spikes = ["dev/docs/spikes/2026-08-30-a1-grid-blind-usability/"]
+++

# Remove numbering grid from level actor diagram

**The slug is stale and stays** — slugs are permanent, and this item's resolution reversed.

Filed as a removal of `preview.py`'s always-on addressable coordinate gutter. A blind spike
(`dev/docs/spikes/2026-08-30-a1-grid-blind-usability/`) then showed agents use the addressing
reliably: **6/6 exact** against **0/6** for a control with the cells stripped, and a graceful
`CANNOT-TELL` where the grid is genuinely too coarse. The complaint is that it is forced on and
visually loud, not that it is useless.

So instead of deleting it: rename `--grid N` to `--locator-cells N`, add `--no-locator-cells`, keep it
**on by default**, draw the labels fainter, and keep `--json` meaningful with the locator off.
Spec: [`spec.md`](spec.md).
