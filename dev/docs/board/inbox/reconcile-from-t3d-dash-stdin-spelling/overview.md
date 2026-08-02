+++
priority = "p3"
kind = "implement"
summary = "Reconcile the `--from-t3d -` stdin spelling tool-wide: `stash capture` drops it (bare `-` only), `actor preview` keeps it."
+++

# Reconcile the `--from-t3d -` stdin spelling tool-wide

Surfaced by the `stash-capture` review (2026-08-02). `stash capture` is moving to a bare
`stash capture -` for stdin T3D and dropping `--from-t3d -` (files-only). But `actor preview` still
reads stdin T3D via `--from-t3d -` (`preview.py:52`). After the stash change, `-` means stdin for
`stash capture` but `--from-t3d -` means stdin for `actor preview` — one snippet-stdin convention,
two spellings.

Decide the tool-wide spelling: make `actor preview` (and any other `--from-t3d -` consumer) take a
bare `-` too, so there is one stdin-T3D spelling everywhere, per `conventions.md`. Enumerate every
`--from-t3d -` consumer first.
