# A world-space gridline overlay for `actor diagram`'s orthographic panes

**Status:** spec (ephemeral — fold into `architecture.md` + `docs/usage.md` on build, then this file may
be deleted).
**Owner rulings folded in (2026-08-30):** two power-of-two tiers chosen from zoom; major tier more
prominent than minor; the override pins the *minor* step and is spelled `--grid-size`; coordinates are
reported as a **bounding box at the top** of the pane, not as per-line labels.
**Depends on:** `remove-numbering-grid-from-level-actor-preview` — see §7.

---

## 1. The gap

`actor diagram` frames a scene automatically: `_framing` fits the projected geometry to the pane and
derives `scale = draw / span`. Nothing in the output says what that scale is. So the image answers
"what shape is this" and cannot answer either of:

- **How big is it?** A 256-uu closet and a 16,000-uu plaza render to the same pane at the same
  apparent size. There is no ruler.
- **Where is it?** The panes carry no world coordinate at all. The only addressing today is the
  A1-style label gutter, and that address is deliberately a region of the *image*, never a world
  coordinate (`preview.py` "addressable coordinate grid"), so it moves with the camera and cannot be
  carried back into a `Location`.

UnrealEd's own 2D viewports solve this with a two-tier world gridline lattice — confirmed against
`Editor.dll` (`dev/docs/spikes/2026-08-30-unrealed-ortho-grid-density/`). `actor diagram` has no
equivalent, so every judgement about scale or position has to leave the image and go back to
`actor bbox` / `actor show`.

## 2. Scope — orthographic panes only

Gridlines are drawn on the three orthographic views and **not** on `iso`:

| View    | Pane axes (world) | Gridlines |
|---------|-------------------|-----------|
| `top`   | X (→), Y (↑)      | yes       |
| `front` | X (→), Z (↑)      | yes       |
| `side`  | Y (→), Z (↑)      | yes       |
| `iso`   | mixed             | **no**    |

`_ORTHO_AXES` already names the first three; `iso` is excluded because its screen axes are not world
axes. A world lattice under the iso projection is a slanted rhombic mesh whose on-screen spacing is not
a world distance in either screen direction, so it would read as decoration rather than a ruler.

Per layout:

- **`quad`** — Top / Front / Side gridded, the Iso pane bare.
- **`single`** — gridded when `--view` is orthographic, bare under `--view iso`.
- **`breakdown`** — one view for every pane (`--view`), so all panes are gridded or none. Each pane
  frames **independently** (pane 0 the whole scene, each later pane one actor's AABB), so each pane
  picks **its own** step from **its own** scale. That is the intended behaviour, not a defect: a pane
  zoomed to one brush should get a finer grid than the whole-scene pane above it.

This is the shared `preview.py` renderer, so `stash diagram` and `prefab diagram` inherit it. It does
**not** touch `level photo --native` (`preview_native.py`), a separate renderer — a gridline overlay
there is out of scope and not filed by this item.

## 3. Port UnrealEd's `DrawGridSection`

**Owner ruling, 2026-08-30: render the grid the way UnrealEd does.** The algorithm is recovered from
`Editor.dll` by static disassembly — `dev/docs/spikes/2026-08-30-unrealed-ortho-grid-density/`, whose
harness re-asserts every constant below (9/9) against the tracked `uned/UED22/Editor.dll`. Source
function `UEditorEngine::DrawGridSection` (`UnEdRend.cpp`, named by its own `appFailAssert` string),
called from `UEditorEngine::DrawWireBackground` under `check(Viewport->IsOrtho())`.

### 3.1 The algorithm

```c
if (step == 0) return;                              // editor's own early-out

count = (int)(width_px * world_per_px / step);      // grid lines across the pane
limit = width_px / 4;                               // >= 4 px between lines

shift = 0;
fade  = 1.0f;
if (2*count >= limit) {                             // near or past the threshold
    while ((count >> shift) >= limit) shift++;      // ESCALATE: step doubles each pass
    fade = 2.0f - (2.0f*count) / ((1 << shift) * limit);
}

drawn = step << shift;                              // the spacing actually rendered

lo = max(-32768/step, first_visible) >> shift;      // world clamp, then scale down
hi = min( 32768/step, last_visible ) >> shift;

for (i = lo; i < hi; i++) {
    world = (i * step) << shift;
    tier  = ((i << shift) & 7) ? 0.5f : 1.0f;       // every 8th line is major
    c     = BASE + (GREY - BASE) * tier;            // GREY = (0.5, 0.5, 0.5)
    if (i & 1) c = BASE + (c - BASE) * fade;        // only odd lines fade
    draw_line(world, c);
}
```

### 3.2 What each piece means

- **Escalation.** When the requested spacing is too fine, the step **doubles** until the lines are at
  least ~4 px apart, and the coarser grid is drawn in its place. It never refuses and never draws a
  wash. This is the behaviour the owner described and the spike confirmed.
- **The tiers are a colour lerp, not opacity.** `tier` interpolates from the base colour toward a
  fixed mid-grey `(0.5, 0.5, 0.5)`. A **major** line (every 8th) lands exactly on mid-grey; a **minor**
  line lands halfway between the base colour and mid-grey. So the tier contrast is set by how far the
  base colour sits from mid-grey — a dark base gives a strong split, a grey base gives almost none.
  Nothing is alpha-blended, so our renderer needs no blend buffer for this (an earlier draft of this
  spec wrongly assumed it would).
- **The fade is an anti-pop, and it is why it only touches odd lines.** Odd-index lines are exactly the
  ones that disappear at the next doubling. As the pane approaches that doubling, `fade` runs 1 → 0 and
  those lines sink back toward the base colour, so they are already invisible when they are dropped.
  Even lines — including every major line, since majors sit at multiples of 8 — never fade. Zooming
  therefore shows a continuous grid rather than a lattice that halves with a jump.
- **`i & 1` and the parity passes.** The editor takes a ninth `AlphaCase` argument and skips lines
  where `(i & 1) == AlphaCase`, so it renders the grid in **two passes**, odds and evens separately.
  That is batching for its own renderer. **We collapse it to one pass** — gridlines never overlap each
  other, so draw order between the two parities cannot change a pixel. Deliberate deviation, recorded
  here so it is not read as an oversight.
- **World clamp.** Line indices are clamped to ±32768 world units before the shift, so the grid never
  runs past the UE1 world extent no matter how far out the pane is framed.

### 3.3 What we keep from the editor, and the one thing we set ourselves

Adopted verbatim: the doubling rule, the 4-px threshold, the `& 7` major tier, the `0.5`/`1.0` tier
values, the fade formula, and the ±32768 clamp.

**The base colour is ours.** The editor reads an `FColor` from `UEditorEngine+0x20C` (one of its
`C_*` palette entries — `Editor.ini` carries a `C_WireGridAxis=(R=119,G=119,B=119)`, but the spike did
**not** pin which property sits at that offset, so this is not a claim about which one it is). Our
palette is not the editor's and our background is changing (§4), so the base colour is a local choice
feeding the same maths.

`--grid-size N` supplies `step`. Without it:

> `step` is the **largest power of two `<= span / 16`**, floored at 1 uu, where `span` is the pane's
> framed world extent.

That lands 16–32 minor divisions across the pane at any zoom, so the grid reads as a ruler rather than
a lone crosshair. The escalation loop then does nothing on the default path (the step already clears the
4-px threshold) and acts only as the safety net for an explicitly-too-fine `--grid-size`.

**Why this is ours and not the editor's.** UnrealEd has no auto-framing — its grid size is whatever the
user picked from the toolbar dropdown, and escalation exists to rescue that fixed choice when you zoom
out. We auto-frame every pane, so there is no user-picked step to start from and the default has to be
derived from the framing. The *mechanism* (§3.1) is ported exactly; only this starting value is local.

**Rejected:** *the coarsest power of two that still yields at least one line* — specced first and
built, then measured: on a 7712-uu pane it picks 4096 and draws **two** gridlines, which tells you
nothing about scale. The failure is that "at least one line" optimises for the wrong end of the range.

Both tiers stay powers of two because `drawn = step << shift` and majors are `8 × drawn`.

## 4. The colours

**Decided (owner delegated, 2026-08-30).** The port needs two endpoints for the §3.1 lerp
`c = BASE + (TARGET - BASE) * tier`:

```
BG            = (64, 64, 64)    # #404040 — board item `move-the-preview-background-off-pure-black-to`
_GRID_BASE    = (64, 64, 64)    # the lerp origin — deliberately EQUAL to BG
_GRID_TARGET  = (96, 96, 96)    # the lerp target, i.e. what a MAJOR line renders as
```

Which yields, with `tier` 0.5/1.0 from §3.1:

| line | rendered | contrast vs background |
|---|---|---|
| minor (7 of every 8) | `(80, 80, 80)` | +16 |
| major (every 8th) | `(96, 96, 96)` | +32 |

**Why `BASE == BG`.** The fade lerps odd lines *toward* `BASE` as they approach being dropped (§3.2).
Setting `BASE` to the background is what makes them fade to genuinely **invisible** rather than to some
residual colour, so the anti-pop is complete. UnrealEd lerps toward a config colour that is not
necessarily its background; ours is the cleaner degenerate case of the same formula, not a deviation
from it.

**Why `TARGET = 96` and not the editor's `128`.** A literal port sets `TARGET` to mid-grey `(128)`,
which is *brighter* than `BACK` (120) — the dimmest neutral geometry — so major gridlines would
out-read the faintest real surface. 96 keeps 24 levels of headroom below `BACK` while still giving the
major tier double the minor tier's contrast against the background. The tier *structure* is ported
exactly; only the absolute endpoints are scaled down to fit our palette.

Both are neutral greys: the CSG wire palette and the per-actor tints carry meaning, and a coloured grid
would compete with them.

**Not measured against a render ladder** — the owner chose to set them directly rather than run one.
If the first real renders read wrong, these three constants are the whole knob.

## 5. `--grid-size N`

```
--grid-size N     minor gridline spacing in world units; must be a power of two, >= 1
```

Supplies `step` in §3.1. Validation is **only** the power-of-two check (owner, 2026-08-30):

- **`N` not a power of two ≥ 1** → exit 2 naming the value: `--grid-size must be a power of two, got 100`.
- **`N` too fine for the pane** → **not an error**: §3.1 escalates and draws a coarser grid, exactly as
  the editor does. The caption reports the step actually drawn (§6), so the substitution is visible.
- **`N` so coarse that no line lands in the pane** → draw nothing, exit 0 (owner, 2026-08-30). The
  caption still names the requested step.
- **`--view iso` with `--grid-size`** → exit 2 naming the conflict: iso draws no gridlines, so the flag
  cannot do anything, and accepting a no-op flag is the silent half-answer the conventions forbid.
- Escalation is **per pane**: `quad` and `breakdown` frame panes differently, so one pane may escalate
  while another does not. Each pane's caption reports its own drawn step, so the image is never silent
  about which grid it shows.

The name `--grid-size` is the owner's (2026-08-30). It is a *new* flag, not a repurposing: the old
`--grid N` (A1 cell density) is renamed to `--locator-cells N` by
`remove-numbering-grid-from-level-actor-preview`, so an invocation carrying the old flag gets a clean
unknown-argument error rather than a silently different meaning. That rename is what frees the word
`grid` here for the only sense that is actually about world geometry.

## 6. The stderr report — nothing is drawn in the image

**Owner ruling, 2026-08-30.** There is **no caption drawn into any pane**. The grid reports itself on
**stderr only**, and it reports **set vs visible**, not minor vs major.

One line per gridded pane, pane-qualified under `quad`, unqualified under `single`:

```
Top: X -1024..2048  Y -512..1536  grid set 32, visible 64
```

- **The world extent** of the framed region in that pane's two axes (`top` → X/Y, `front` → X/Z,
  `side` → Y/Z), named by axis letter. This is the region `_framing` actually fitted, including the
  `_FRAME_PAD` border — it describes what the image covers, which is what makes it a scale reference.
  Integers when integral, else one decimal.
- **`set`** — the step that was asked for: the explicit `--grid-size N`, or the §3.3 auto-derived
  default when the flag is absent.
- **`visible`** — the step actually drawn, `set << shift`. Equal to `set` whenever nothing escalated,
  which is every default-path render (§3.3 picks a step that already clears the threshold). They differ
  only when an explicit `--grid-size` was too fine for the pane, and then the pair is exactly the
  information the user needs: *you asked for 32, you are looking at 64.*

**Major spacing is deliberately not reported.** Reporting it was specced and built, and measured wrong:
the caption printed `8 × drawn` while the lattice puts majors every `8 × set` world units, because the
tier test is `((i << shift) & 7) == 0` against the pre-escalation index. At `--grid-size 32` escalating
once, the caption read `512` while the majors measured every **256** uu — 4 drawn lines apart, not 8.
(Board item `grid-caption-major-8x-drawn-is-imprecise-once` has the bit-math; it also notes that at
`shift >= 3` every drawn line becomes major and the tier split vanishes.) Rather than print a corrected
`max(drawn, 8 × set)`, the field is dropped: `set`/`visible` is what a user acts on, and the major tier
is a legibility cue to be looked at, not a number to be quoted.

**Why nothing is drawn in the image.** An in-pane caption was specced, built, and then measured to
**overwrite 30 px of CSG-coloured geometry** with caption grey on the `quad` golden at `--size 256`,
while also truncating (`X 5168..7729`, no Y axis, no grid field) because 128-px panes cannot hold the
string. Text silently erasing geometry is the same defect class as a gridline covering a face (§4).
Reserving a caption band would fix the overlap but not the truncation, which is horizontal. stderr has
neither constraint, and the locator legend already establishes stderr as this renderer's readback
channel.

## 7. Interaction with the locator gutter

`remove-numbering-grid-from-level-actor-preview` is the sibling item. Its outcome is now settled: the
addressable gutter is **kept, on by default**, renamed `--locator-cells N` with a `--no-locator-cells`
opt-out. So both states occur in normal use and both are handled:

- **Locator on** (the default) — its label band insets the drawable rect; gridlines fill what is left.
- **Locator off** (`--no-locator-cells`) — the `gutter` reserve is 0 and gridlines fill the full rect.

Nothing else couples them: §6 draws no caption, so there is no placement to negotiate, and both
features report on stderr independently.

Neither state changes anything in §§3–6. This item does not depend on that one shipping first and can be
## 8. Rejected and deferred

**Rejected.**

- *A world-space addressable cell grid* (`D4` naming a world region rather than an image region) — the
  A1 grid's own spec rejected it and the reasoning still holds: geometry lands anywhere, so a fixed
  world grid does not divide the *image* evenly and the addresses move with the camera. Gridlines are a
  ruler, not an addressing scheme, and this item does not reintroduce one.
- *A fixed default spacing in world units* — auto-framing means one fixed step gives a single line on a
  plaza and a solid wash on a doorframe. Rejected in favour of zoom-dependent selection.
- *Erroring on a too-fine `--grid-size`* — specced first, then **refuted by the binary**: UnrealEd
  escalates and draws a coarser grid. Matching the editor beats inventing a refusal.
- *Our own `size/64` density rule and a two-tier scheme of our own design* — both written first, both
  dropped: the owner ruled we render the grid the way UnrealEd does, so the 4-px threshold, the tier
  lerp and the fade are ported rather than invented (§3). The stated objection to the fade — "we have
  no alpha buffer" — was **wrong**: the editor is not alpha-blending, it is computing a per-line colour.
- *The editor's two parity passes* — collapsed to one (§3.2). Gridlines never overlap, so the split
  cannot change a pixel; it is batching for the editor's renderer, not part of the visual result.
- *A decimal 1/2/5×10ⁿ step ladder* — the standard charting ladder, but the geometry is authored on
  powers of two and a 500-uu line lands nowhere a brush snaps to.
- *Requiring `--grid-size` on every invocation* — the auto step is reported in the caption, so it is not
  a silent guess, and mandatory spacing would make the common preview harder for no gain.
- *Per-line coordinate labels in the margin* — considered and passed over in favour of the stderr report;
  at 32–64 minor divisions the margin cannot hold a label per line anyway, and labelling only the major
  lines still crowds a 256-px pane.
- *Gridlines on the `iso` pane* — §2.

**Deferred (not built, not filed as work).**

- Emphasising the world-origin axes. A natural third tier, but not ruled in; raise it as a question if
  reading the first renders makes it feel missing.
- A gridline overlay for `level photo --native` (§2).
- Any grid on a future perspective mode (`dev/docs/spikes/2026-08-05-perspective-in-preview-py/`).

## 9. Tests

- **Against the editor's arithmetic** — the port is a transcription, so test it as one: a table of
  `(width_px, world_per_px, step)` cases asserting `shift`, `drawn`, `fade` and the per-index `tier`
  exactly as §3.1 computes them, including the `2*count >= limit` gate that decides whether `fade` is
  computed at all. `dev/docs/spikes/2026-08-30-unrealed-ortho-grid-density/harness/grid_density.py`
  re-derives the same constants from `Editor.dll`, so the two can be cross-checked.
- **Escalation** — a step too fine for the pane doubles until lines are ≥ 4 px apart; `drawn == step <<
  shift`; majors stay `8 × drawn`; and the caption reports the drawn step, not the requested one. Under
  `quad`, a step that fits one pane and escalates in another gives two drawn steps and two captions —
  not an error.
- **The fade touches only odd lines** — for a framing mid-escalation, assert every even-index line
  (majors included) carries its unfaded colour and every odd-index line is lerped toward `BASE` by
  `fade`; and that `fade` is exactly `1.0` when `2*count < limit`.
- **Tier assignment** — `((i << shift) & 7) == 0` lines get the mid-grey endpoint and all others the
  halfway colour, and majors stay pinned to multiples of `8 × drawn` in **world** space across two
  different zooms (the property the `<< shift` in the test is there to preserve).
- **World clamp** — a pane framed past ±32768 draws no line beyond it.
- **`--grid-size`** — a power of two ≥ 1 is honoured; a non-power-of-two exits 2 naming the value;
  `--grid-size` with `--view iso` exits 2 naming the conflict.
- **Too coarse** — a step so large no line lands in the pane renders cleanly with no gridlines, exit 0,
  and the caption still names the step.
- **View scoping** — a rendered `iso` pane contains no gridline pixels and no stderr line; each of
  `top`/`front`/`side` does. Under `breakdown`, per-pane steps differ when the panes' scales differ.
- **Draw order** — render a scene where a face covers a known gridline pixel and assert that pixel
  carries the face colour, not a grid colour: the grid is a backdrop and never paints over geometry. Assert the grid greys are unaffected by `--focus` (not dimmed) and by `--faces textured`.
- **stderr report** — one line per gridded pane, pane-qualified under `quad` and unqualified under
  `single`; axis letters follow the view; the extent matches `_framing`'s fitted region, not the
  geometry bbox; `set` is the requested/auto step and `visible` is `set << shift`. Assert `set ==
  visible` on a default render and `set != visible` on one forced to escalate.
- **Nothing is drawn in the image** — assert no pane contains the caption colour, at `--size` 256 and
  1024, under `single` and `quad`. This is the regression guard for the overlap defect: an in-pane
  caption previously erased 30 px of CSG-coloured geometry on the `quad` golden.
- **Major spacing is not reported anywhere** — no `/` pair, no `major` field, on stdout or stderr.
- **Empty scene** — no gridlines and no caption; the renderer returns before a framing exists, so there
  is no scale to draw against.
- **Line weight** — 1 px at every `--size`, matching the existing wire strokes.
- **All three verbs** — `actor diagram`, `stash diagram` and `prefab diagram` share
  `render_actors_to_out`, so each gets the flag and the same behaviour.
- **Golden** — one small committed golden PNG for a fixed scene at a fixed `--size` and `--grid-size`,
  so a change to the lattice geometry or the greys is visible in review rather than silent.
