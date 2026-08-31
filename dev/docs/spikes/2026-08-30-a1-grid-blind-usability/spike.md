# Blind usability of the A1 addressable grid on a complex render

**Board item:** `remove-numbering-grid-from-level-actor-preview`.
**Question.** Can an agent reliably use `actor preview`'s A1 cell addressing on a complex, real render —
both to go from a described region of the image to a set of actor Names, and from a Name back to a
place in the image?
**Answer.** **Yes, decisively** — 6/6 exact on the graded tasks, against 0/6 for a control with the
addressing withheld. Where the grid is too coarse to separate two actors, agents correctly report that
rather than guessing (4/4). The feature works; the item's complaint is about its being forced on, not
about its being useless. This refutes removing it.

---

## Why it needed measuring

The item asks to delete the gutter. The gutter is one third of a feature whose stderr legend and
`--json` map are the only channel identifying an actor in a `single`/`quad` preview, so the cost of
removal depends on whether that channel actually works. The static numbers suggested it does not:

- 307 actors, of which only **21 of 144 cells** are occupied — auto-framing puts the level in roughly
  the top-left sixth of the pane;
- the legend is **308 lines**;
- cells collide hard — `C2` holds **60** actors, `C4` 56, `B2` 50.

Those numbers are about the *pane*, not about what an agent achieves with it. This spike measures the
achievement.

## Method

**Scene.** `hexagon_good.t3d` (307 actors, a real LUM trunk), `--layout single --view top --size 1024`,
default `--grid 12`. Committed here as `scene-hexagon-top.png` with its `--json` map and stderr.

**Blind.** Each trial is a fresh subagent that is told only that someone ran `actor preview` and given
the image plus the captured stderr. Nothing in any prompt mentions a grid, a gutter, a cell, or that an
addressing scheme is under evaluation. The prompts are recorded verbatim in `harness/tasks.json`.

**Two arms, same image.**

| Arm | stderr it gets | Withholds |
|---|---|---|
| **grid** | the real legend, `Name  Cell  (Span)` | nothing |
| **control** | the same lines with cell and span stripped — names only | the addressing, and only that |

The control still gets the full actor list, which a caller would have from `actor find` anyway, so the
only variable is the addressing.

**Tasks.** Ground truth is computed from the `--json` cell map by `harness/make_fixtures.py`, so it is
derived from the same projection the image is drawn from and cannot drift from it.

| Task | Direction | What it probes | Truth |
|---|---|---|---|
| `T1-sparse-region` | region → names | the easy case: an isolated cluster with no neighbour | 28 actors, cells H10–J12 |
| `T2-dense-discriminate` | region → names | the hard case: two similar rooms in adjacent cells | 5 actors, cell B3 |
| `T3-locate` | name → place | the reverse direction | `Brush30` is in B3 |

Two replicates per task per arm; region tasks scored as an exact set match plus P/R/F1
(`harness/score.py`).

## Results

**Grid arm — 6/6 exact.**

| Trial | Result |
|---|---|
| T1 ×2 | **exact**, P=1.00 R=1.00 F1=1.00 — all 28 names, no misses, no spurious |
| T2 ×2 | **exact**, P=1.00 R=1.00 F1=1.00 — `Brush26 Brush27 Brush29 Brush30 Light46` |
| T3 ×2 | **correct** — both named cell B3 and both correctly identified it as the *left* hexagonal room |

**Control arm — 0/6.** Every control trial returned `UNKNOWN`. With the names but no addressing, the
image cannot be joined to the list at all.

T2 is the load-bearing result. "The left-hand of the two hexagonal rooms" cannot be answered from the
legend alone — the legend does not say which cell column is on the left. The agent has to read the
image, see that the left hexagon sits in column B and the right in column C, and then select on the
legend. It did that exactly, twice, on a 307-actor scene where the two rooms are adjacent and similar.
That is the join the whole feature exists to support.

## The density limit, and how it fails

`T1`–`T3` all target regions that *are* separable at 12×12. The over-dense cells are not, so a fourth
probe tested what happens inside one.

`Brush13` and `Light54` are both in cell `C2` but four fine-cells apart horizontally (established by
re-rendering the identical scene at `--grid 52`, where `C2`'s 58 stable actors spread over 15 distinct
cells, columns 8–12). Trials were asked which is further left, with `CANNOT-TELL` offered as an explicit
third option and both name orderings run to catch position bias.

**4/4 answered `CANNOT-TELL`**, in both orderings.

So the grid **degrades gracefully**: below its cell size it yields no answer rather than a confident
wrong one. That is the benign failure mode — an agent that cannot resolve a sub-cell question knows it
cannot, and can re-render with a higher `--grid N` or a tighter `--frame`. The addressing never
fabricated a discrimination it could not support.

The limit is real and should be documented: **a cell resolves a region, not an actor.** A question whose
answer lies inside one cell needs a denser grid or a tighter frame.

## What this decides

Removing the addressing outright — the item as filed — would delete the only working name↔image channel
`single` and `quad` have, on the strength of an intuition this spike refutes. So it is kept.

The owner's ruling on top of that evidence (2026-08-30): keep it **on by default** with a
`--no-locator-cells` opt-out, rename `--grid N` to `--locator-cells N`, and draw the labels fainter.
The spike settles only that the capability is real; on-by-default versus opt-in was the owner's call,
and they took on-by-default so an agent that does not know to ask for the addressing still gets it.

The one limit to carry into the docs: **a cell resolves a region, not an actor.**

## Side finding (filed separately)

Rendering the same T3D twice produces **different Names for the 8 unnamed brushes** — each render mints
a fresh `Brush_<random>` (e.g. `Brush_ei4244` in one run, `Brush_2t943a` in the next). So
`actor preview --from-t3d … --json` is not reproducible across runs and two renders of one file cannot
be diffed by name. The 299 named actors are stable, and both arms of this spike used a single render, so
nothing here is affected. Board item: `actor-preview-from-t3d-mints-random-names-for`.

## Reproducing

```
uedcli actor preview --from-t3d hexagon_good.t3d --layout single --view top --size 1024 \
    --json --out scene-hexagon-top.png > scene-hexagon-top.json 2> scene-hexagon-top.stderr.txt
python3 harness/make_fixtures.py scene-hexagon-top.json Top harness/tasks.json scene-hexagon-top
python3 harness/score.py scene-hexagon-top.truth.json T2-dense-discriminate answers/T2-grid-r1.txt
```

`answers/` holds each trial's verbatim final message.

## No regression test

Per `dev/docs/rules/spikes.md`, a checkable standing fact gets a committed test. This spike's result is
a **one-off design decision** — whether the feature is kept at all — not a standing fact about the
engine or our code, so it carries no test. The facts it rests on that *can* rot (the cell math, the
legend format, the `--json` shape) are already pinned by `test_preview.py` and `test_actor_preview.py`.
