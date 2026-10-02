+++
priority = "p3"
kind = "debug"
summary = "actor diagram --size 0 or negative tracebacks with IndexError"
+++

# `actor diagram --size 0` (or negative) tracebacks with `IndexError`

**Pre-existing, not introduced by `--faces`, and deliberately out of that slice's scope** — found while
fixing the neighbouring large-`--size` crash, which IS fixed (`preview._alloc_buffers` now catches
`OverflowError` as well as `MemoryError`, so a huge `--size` refuses cleanly naming the size).

## Reproduce

```
uedcli actor diagram --from-t3d uedcli/tests/fixtures/level_small.t3d --size 0   # rc 1, IndexError
uedcli actor diagram --from-t3d uedcli/tests/fixtures/level_small.t3d --size -5  # rc 1, IndexError
```

Both traceback out of `preview.DensityGrid.add_segment`. `DensityGrid.build` computes
`n = (size + cell_px - 1) // cell_px`, which is 0 for `size=0` and negative for `size=-5`, so `cells` is
empty and the first `cells[row * n_cols + col] += 1` indexes an empty list.

## Why it is worth fixing

`CLAUDE.md`: **never let a Python exception reach the CLI user** — a bad value must be a clean error
naming it. `--size` is a plain `type=int` with no validation, so every non-positive value tracebacks, and
`--size 0` is an easy typo. It affects all three preview verbs (`actor`/`stash`/`prefab diagram`) in every
mode, `wire` included.

## The fix

Validate `--size` as a positive integer, with the error naming the offending value — either in `cli.py` or
beside the existing `--frame-tightness must be in [0, 1], got …` check in
`dispatch._render_actors_to_out`, which is the house pattern for this. Whether the floor should be higher
than 1 (a 1-pixel pane is degenerate for framing too) is a judgement call, not part of the crash.

Pin it with a regression test per the "cover each path" rule; `test_preview_faces.py` already pins the
refusal at the other end of the range
(`test_the_depth_buffer_is_a_float_array_and_an_absurd_size_refuses_cleanly`).
