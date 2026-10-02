+++
priority = "p2"
kind = "implement"
summary = "`brush build cylinder/cone --axis x|y|z` — SHIPPED"
+++

# `brush build cylinder/cone --axis x|y|z` — SHIPPED

Added `--axis x|y|z` (default z) to `brush build cylinder`/`cone`: the ring is built in `(u,v)` and
mapped through the same `_SWEEP_FRAMES[axis]` frame `extrude`/`revolve` use, so the prism/cone is
oriented directly and emits no `Rotation`. `--axis z` is byte-identical to the prior +Z output
(verified against the pre-change builder). `sheet` keeps `--plane`, `cube` takes neither (owner
2026-08-02). One subagent review found no issues; its two help-text nits were fixed.
