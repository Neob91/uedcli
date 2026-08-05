# Is the Python rasterizer acceptable for a WHOLE level?

`actor preview` renders a named actor SET (typically a handful to dozens of brushes). `level preview`
renders the WHOLE level — a retail map is thousands of brushes / tens of thousands of post-CSG
surfaces. The Rust `render.rs` exists partly because it is fast; `preview.py` is a pure-Python stdlib
rasterizer.

Two separate costs (they do not move together):

- **CSG solve.** `native-preview-perf-an-8-shot-castle-batch` measured the carve at ~8 s of an ~11.5 s
  batch — and that carve is the *shared* native core, unchanged by which rasterizer draws. So
  consolidation does not by itself fix solve time.
- **Rasterization.** `preview.py`'s per-pixel/per-poly Python loops over a whole level's surviving
  surfaces at `--size` may be materially slower than `render.rs`. Whether that is acceptable for the
  offline "draft" tier, or needs the `make-actor-preview-faster` work (NumPy? a resolution knob?)
  landed first, is the question.

If the answer to the projection fork is (a), this must be answered too: does the offline whole-level
draft stay pure-Python, or does keeping it fast mean this depends on `make-actor-preview-faster`?

## Answer

<!-- Empty = open. -->
