+++
priority = "p2"
kind = "owner-question"
summary = "[OWNER — confirm] wire renders a mirrored brush with its front/back shades swapped"
+++

# [OWNER — confirm] `--faces wire` renders a mirrored brush with its front/back shades swapped

**Raised because the owner's ruling — "mirrored brushes SHOULD WORK CORRECTLY" — was given about the
FILLED modes, and I implemented it there only.** `--faces wire` still shows the inversion. That may be
exactly what was intended (it is untouched, long-standing behaviour, and it is what the byte-identity
golden pins), or it may be a second instance of the same bug. Not chosen either way.

## The mechanism

A negative-determinant linear part (`brush scale --by -1,1,1`) is a **reflection**. It reverses the
handedness of every vertex ring, so a transformed face's Newell normal comes out as the **negative** of
its true outward normal, and `preview._is_front` answers the opposite of the truth for every face of that
brush. Measured on a subtract cube under `MainScale.X=-1`: the wall that lands at x=+256 carries a
computed normal of −X, so `_is_front` calls it camera-facing when it faces away.

Filled modes now correct that (`_is_front_corrected`). `wire` does not.

## What it costs `wire`, exactly

`wire` culls nothing, so facing feeds only two things there:

- **the front/back SHADE** — a camera-facing edge is drawn in the brush's darker hue and an obscured one
  in the paler hue. On a mirrored brush those are swapped, so the facing cue reads backwards.
  Measured: an XY sheet with `MainScale.X=-1` viewed from TOP draws 216 px of the BACK (paler) hue and
  **0** px of the FRONT hue, while facing the camera.
- **`occluders`**, hence the graded opacity of on-face poly-index decals — a mirrored brush contributes
  the wrong faces, so its own numbers are graded off the wrong set.

Nothing is deleted or hidden: every face still draws, in the right place, in the right brush's hue. It is
a wrong *shade*, not a wrong picture.

## Why it was not just fixed

- The ruling named the modes it was about, and this is not one of them.
- `wire` is the default and the mode with the byte-identity guarantee. Correcting it changes the bytes of
  `uedcli/tests/fixtures/preview_wire_golden_{iso,quad}.png` — the primary regression guard for the whole
  `--faces` feature, captured from the pre-feature tree — and would need that golden re-blessed, which is
  a decision about the wireframe itself, not about `--faces`.
- Three of the thirteen brushes in `uedcli/tests/fixtures/level_small.t3d`, this repo's own real editor
  export, are mirrored, so the change is visible on real content and not a corner case.

## If the answer is "fix wire too"

One line: drop the `filled and` guard on `mirrored` in `preview._scene_geometry`, so `wire` also goes
through `_is_front_corrected`. Then re-bless both `wire` goldens (`UEDCLI_BLESS_GOLDEN=1 bin/test -k
wire_golden`) **after** confirming the new shading by eye, and note in `architecture.md` that the goldens
were re-blessed for this and why. The current behaviour is pinned by
`test_wire_is_deliberately_left_uncorrected_on_a_mirror`, which is the test to delete.
