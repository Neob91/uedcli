#!/usr/bin/env python3
"""Render the `--focus` dim-alpha ladder for `actor preview --faces flat`, and measure how far each
candidate lands from the background.

Owner decision 2.12: the constant is chosen from a real before/after render, not from arithmetic. This
produced the pictures and the numbers beside them; the outcome was **0.35** (see `../findings.md`).

    PYTHONPATH=<repo> python3 render_ladder.py <project-dir> <outdir> \
        --level demo --actors Room,Pillar,Crate --focus Pillar [--alphas 0.15,0.25,…] [--annotate all]

Writes `dim-nofocus.png` (the reference, same scene with no `--focus`) plus `dim-<alpha>.png` per
candidate — two decimals, so the names sort and match the table in `../findings.md` — and prints for each candidate the PER-CHANNEL distance from `BG` (max/min over the three
channels) of every fill colour the scene actually dims, alongside the mid-grey (128) figure the
"~14 levels" prediction was quoted for. Per channel and not a mean: `BG` is neutral, so a saturated
hue fades unevenly and the MIN channel is how close to invisible the surface gets.

**Needs a resolvable project**, not just a T3D snippet: `--faces flat` loads the game's class hierarchy
to tell a mover from a real subtraction (decision 2.13), so it needs the per-user games config too.
"""
import argparse
import os
from collections import Counter
from types import SimpleNamespace

from uedcli import preview
from uedcli.cli import dispatch

DEFAULT_ALPHAS = "0.15,0.25,0.30,0.35,0.40,0.45,0.50,0.70"


def _render(project, actors, out, *, focus, alpha=None, annotate="none", size=700):
    if alpha is not None:
        preview._DIM_FILL_ALPHA = alpha
    args = SimpleNamespace(cmd="actor", sub="preview", project=project, names=list(actors),
                           from_t3d=None, view="iso", layout="single", annotate=annotate,
                           iso_angle=30.0, frame=None, frame_tightness=0.8, highlight=None,
                           focus=focus, show="", size=size, out=str(out), brush_colors=None,
                           faces="flat")
    rc = dispatch.dispatch(args)
    assert rc == 0, f"render failed: rc={rc}"
    return out


def _pixels(path):
    from PIL import Image
    with Image.open(path) as im:
        return Counter(im.convert("RGB").getdata())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("outdir")
    ap.add_argument("--level", help="sets UEDCLI_LEVEL for the run")
    ap.add_argument("--actors", required=True, help="comma-separated actor names to render")
    ap.add_argument("--focus", required=True, help="which of them to focus")
    ap.add_argument("--alphas", default=DEFAULT_ALPHAS)
    ap.add_argument("--annotate", default="none",
                    help="passed straight to `actor preview`; anything but 'none' suffixes the "
                         "filenames, so an annotated ladder does not overwrite the plain one")
    a = ap.parse_args()
    if a.level:
        os.environ["UEDCLI_LEVEL"] = a.level
    actors = a.actors.split(",")
    bg = (preview.BG,) * 3
    tag = "" if a.annotate == "none" else "-" + a.annotate.replace(":", "").replace(",", "")
    ref = _render(a.project, actors, f"{a.outdir}/dim-nofocus{tag}.png", focus=None,
                  annotate=a.annotate)
    # Which fill colours the reference shows in quantity — those are what a candidate dims.
    subject = [(c, n) for c, n in _pixels(ref).most_common() if c != bg and n > 400]
    print(f"reference {ref}: " + ", ".join(f"{c}x{n}" for c, n in subject))
    for alpha in (float(s) for s in a.alphas.split(",")):
        out = _render(a.project, actors, f"{a.outdir}/dim-{alpha:.2f}{tag}.png", focus=a.focus,
                      alpha=alpha, annotate=a.annotate)
        got = _pixels(out)
        rows = []
        for c, n in subject:
            blended = tuple(round(alpha * ch + (1 - alpha) * preview.BG) for ch in c)
            d = [abs(preview.BG - ch) for ch in blended]
            rows.append(f"{c}->{blended} d={max(d)}/{min(d)} px={got.get(blended, 0)}")
        grey = round(alpha * 128 + (1 - alpha) * preview.BG)
        print(f"alpha {alpha:g} {out}: mid-grey 128 -> {grey} ({preview.BG - grey} levels) | "
              + " | ".join(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
