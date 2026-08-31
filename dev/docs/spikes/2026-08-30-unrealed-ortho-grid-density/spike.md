# UnrealEd's ortho-viewport grid: density escalation and the two tiers

**Board item:** `add-visual-grid-for-2d-views-in-level-actor`.
**Question.** What does UnrealEd do when the selected grid size is too fine to draw in an ortho
viewport? (Owner's account, to confirm: it renders a coarser grid instead.)
**Answer.** **Confirmed.** It doubles the grid step until the lines are at least ~4 px apart, and draws
the coarser grid in place of the requested one. No error, no blank viewport, no wash.
**Confidence:** 📖 string/binary-extracted — static disassembly of the shipped `Editor.dll`, not a live
probe. Every claim below is re-checkable by `harness/grid_density.py` (13/13 passing).

---

## Where it lives

`Editor.dll` exports exactly one grid-drawing symbol:

```
?DrawGridSection@UEditorEngine@@UAEXPAUFSceneNode@@HHHPAVFVector@@1PAM2H@Z
  → void UEditorEngine::DrawGridSection(FSceneNode*, int, int, int, FVector*, FVector*,
                                        float*, float*, int)
```

RVA `0x5f740`, image base `0x10000000`. `ret 0x24` (36 bytes) confirms the nine stdcall args. The
fourth arg (`[ebp+0x14]`) is the grid size; the function returns immediately when it is 0.

## The rule

Reconstructed from the prologue and the loop at `0x1005f849`–`0x1005f902`:

```c
// Frame+0xA8 and Frame+0xD0 are named from use, not from a symbol: the arithmetic only makes
// sense as (viewport width in pixels) and (world units per pixel).
int   width = Frame->X;                       // Frame+0xA8
float zoom  = Frame->Zoom;                    // Frame+0xD0
int   count = (int)(width * zoom / GridY);    // grid cells across the viewport
int   limit = width / 4;                      // signed div-by-4 (cdq / and edx,3 / add / sar 2)

int shift = 0;
if (2 * count >= limit)                       // at or near the density threshold
    while ((count >> shift) >= limit)         // 0x1005f880: sar edx,cl / cmp edx,eax / inc esi
        shift++;                              // ESCALATE — the step doubles each pass

int step = GridY << shift;                    // what actually gets drawn
```

**So the drawn spacing is `GridY · 2^shift`** — the requested size when it fits, otherwise the next
power-of-two multiple that does. `shift` is applied three ways, all visible in the disassembly: the
loop bounds are shifted down (`sar edi, cl`, `sar eax, cl`), and each line's world coordinate is
shifted up (`shl eax, cl`) before being written through the `FVector*` out-params.

**The threshold is ~4 pixels per line.** `count` is lines across the viewport and `limit` is
`width/4`, so the loop stops once `width / lines_drawn > 4`. (The `width` term cancels
algebraically — the condition reduces to `4·zoom/GridY < 2^shift` — but the 4-px reading is what the
two quantities mean.)

## Two tiers, and which one is stronger

At `0x1005f979`, per line:

```c
alpha = ((index << shift) & 7) ? 0.5f : 1.0f;
```

Constants read from `.rdata`: `0x100dcb10 = 0.5`, `0x100d2f80 = 1.0`.

So **every 8th line is drawn at full strength and the other seven at half** — a two-tier grid with an
**8× ratio**, the coarse tier the more prominent one. Because the test is on `index << shift`, the
major lines stay pinned to multiples of `8 · GridY` in world space as the grid escalates; they do not
drift with the zoom.

## A fade near the threshold

When `2·count >= limit` the function also computes (`0x1005f8bc`, constant `0x100d2f84 = 2.0`):

```c
fade = 2.0f - (2.0f * count) / ((1 << shift) * limit);
```

and otherwise uses `1.0f`. So the grid does not pop between escalation steps — it fades as it
approaches the density at which it would double. Which lines fade, and why only some of them do, is
the colour maths below.

## World clamp

`0x1005f8d4`: the line range is clamped to `±32768` world units divided by the grid size
(`mov eax, 0xffff8000` / `idiv [ebp+0x14]`, and `0x8000` for the far edge), then shifted by `shift`.
The grid never extends past the UE1 world extent regardless of zoom.

## What this settles for us

Three things the `add-visual-grid-for-2d-views-in-level-actor` spec asserted about UnrealEd now have
evidence, and one of them was wrong:

| Spec claim | Status |
|---|---|
| "UnrealEd's 2D viewports draw a two-tier lattice" | **Confirmed** — 0.5 / 1.0 alpha tiers |
| Major tier is the more prominent one | **Confirmed** — major is 1.0, minor 0.5 |
| Major = 8 × minor (filed as *our* legibility choice) | **Confirmed as UnrealEd's own ratio** — `& 7` |
| Too-fine step → exit 2 (our invention) | **Refuted** — the editor escalates and draws |

The `8×` ratio in particular was written up as an agent-chosen default; it is in fact what the editor
does, and the spec should cite this rather than claim it.

**All of it is adopted.** The owner ruled (2026-08-30) that the preview renders the grid the way
UnrealEd does, so the spec ports §"The rule", the tier lerp, the fade and the world clamp rather than
inventing equivalents. Two notes on that port:

- An earlier draft rejected the fade on the grounds that "we have no alpha blend buffer for the grid
  layer". **That was wrong.** The editor does not alpha-blend either: `tier` and `fade` are inputs to
  an `FPlane` lerp that produces a per-line *colour*, drawn opaque. Our renderer can do the same
  arithmetic with no new machinery.
- The **base colour is not ported**. The editor lerps from a config `FColor` at `UEditorEngine+0x20C`
  toward mid-grey; our palette and background differ, so the endpoints are picked locally while the
  lerp itself is kept.

## The colour maths

The two constants feed an `FPlane` lerp, resolved from the imports
(`??GFPlane` = `operator-`, `??DFPlane` = `operator*(float)`, `??HFPlane` = `operator+`):

```c
FPlane BASE = EditorEngine->SomeColor.Plane();     // UEditorEngine+0x20C, an FColor
FPlane GREY = FPlane(0.5f, 0.5f, 0.5f, 0.0f);      // 0x100e6930

c = BASE + (GREY - BASE) * tier;                   // tier = 0.5 minor / 1.0 major
if (i & 1) c = BASE + (c - BASE) * fade;           // odd lines only
```

So a **major** line lands exactly on `GREY` and a **minor** line halfway between `BASE` and `GREY` —
the tier contrast is however far `BASE` sits from mid-grey. And the fade applies **only to odd-index
lines**, which are exactly the ones the next doubling removes: they sink back toward `BASE` before
they vanish, which is why the editor's grid does not pop while you zoom. Majors sit at multiples of 8,
so they are always even and never fade.

`Editor.ini` carries a `C_WireGridAxis=(R=119,G=119,B=119)`, but this spike did **not** pin which
`C_*` property occupies `+0x20C`, so that is a candidate, not a finding.

## The parity split

The ninth argument, `AlphaCase`, is compared against `i & 1` and the line is skipped when they match
(`0x1005f93f`). So the editor renders the grid in two passes — odds and evens separately — which is
batching for its own renderer. Gridlines never overlap, so the split has no effect on the resulting
image; our port collapses it to one pass.

## Reproducing

```
cd dev/docs/spikes/2026-08-30-unrealed-ortho-grid-density
python3 harness/grid_density.py ../../../../uned/UED22/Editor.dll
```

13/13 PASS against the tracked `uned/UED22/Editor.dll`. The harness asserts the signature, the
early-out, the escalation loop, the `width/4` threshold, the `1 << shift` scaling, both world clamps,
the `& 7` tier test, and both alpha constants — so a different `Editor.dll`, or a wrong reading of
this one, fails loudly rather than rotting as prose.

## Follow-up

`rules/spikes.md` wants a checkable finding pinned by a committed regression test. The harness above
is that check but lives in the spike, not the suite. Promoting it to a `test_engine_facts` case is
proposed on the board item, not done here — this session was speccing, not implementing.
