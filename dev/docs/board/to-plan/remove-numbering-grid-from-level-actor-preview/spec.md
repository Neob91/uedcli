# Keep the addressable grid: rename it `locator-cells`, make it opt-out and fainter

**Status:** spec (ephemeral — fold into `architecture.md` + `docs/usage.md` on build, then this file may
be deleted).
**The slug is now wrong and stays anyway.** Slugs are permanent (`board/README.md`), and the item's
resolution reversed: the blind spike showed the grid works, so it is kept rather than removed.
**Owner rulings, 2026-08-30:** keep it, default ON with an opt-out, rename off `grid`, draw the labels
fainter, and keep `--json` meaningful in both modes.
**Evidence:** `dev/docs/spikes/2026-08-30-a1-grid-blind-usability/`.
**Sibling:** `add-visual-grid-for-2d-views-in-level-actor` (world gridlines, `--grid-size`) — a
different feature that this rename gets out of the way of.

---

## 1. What it is today

`preview.py`'s "addressable coordinate grid", always on, no way to disable:

1. **A painted label gutter** — columns `A,B,C…` across the top, rows `1,2,3…` down both sides, no
   gridlines. `_draw_grid_gutter` draws into a band `_framing`'s `gutter` argument reserves on the top
   and both sides, insetting the geometry.
2. **A stderr legend** — `Pillar  D4  (C3–E5)`: centroid cell plus covered span, pane-qualified under
   `quad`, `(hidden)` when the actor drew no pixel.
3. **A `--json` payload** — `{image, grid:{cols,rows}, actors:{<name>:{panes:{<Pane>:{cell,span}}, hidden}}}`.

`--grid N` (default 12, bound `[1,52]`) sets the density. The address is a region of the
image/projection, never a world coordinate.

## 2. Why it is kept

The item was filed as a removal. The spike measured whether the addressing is usable at all on a
complex render, blind, and it is:

- **Grid arm 6/6 exact** against **0/6** for a control given the same image and the same actor list
  with only the cell/span stripped — every control trial answered `UNKNOWN`.
- The decisive trial named the five actors of the **left** of two adjacent, similar hexagonal rooms on
  a 307-actor scene, exactly, twice. That requires reading the image and joining it to the legend.
- Inside the 60-actor cell `C2`, **4/4 answered `CANNOT-TELL`** in both orderings — it degrades
  gracefully rather than fabricating.

The static density numbers that motivated removal (307 actors in 21 of 144 cells) describe the pane,
not what an agent achieves with it. So the complaint is that it is **forced on and visually loud**, not
that it is useless — and that is what this spec fixes.

## 3. The change

### 3.1 Rename: `grid` → `locator-cells`

```
--locator-cells N      density: N columns × N rows. Default 12. Must be in [1, 52]
--no-locator-cells     turn the whole feature off
```

`grid` has to go because it now means three different things: `brush snap --grid N` (world units), the
sibling item's `--grid-size` (world gridlines), and this (image-space addressing). Only this one is not
about world geometry, so it is the one that moves.

**"locator" names the feature; "cell" stays the unit.** An address is still a cell (`D4`), so the
internal vocabulary that is already correct stays put — `ActorCell`, `_cell_of_pixel`, `_actor_cells`,
`_cell_address`, `_col_label` are all unchanged. Only the symbols carrying the old feature name move:

| today | becomes |
|---|---|
| `GRID_LABEL` | `LOCATOR_LABEL` |
| `_draw_grid_gutter` | `_draw_locator_gutter` |
| `_grid_gutter_px` | `_locator_gutter_px` |
| `_GRID_MAX` | `_LOCATOR_MAX` |
| `_grid_legend_lines` | `_locator_legend_lines` |
| `_grid_json` | `_preview_json` (§3.4 — it is no longer only the locator payload) |
| the `grid=` render parameter | `locator=` |

Per "no back-compat cruft", `--grid` is deleted outright — no alias, no deprecation. An old invocation
gets a clean unknown-argument error.

### 3.2 Opt-out, not opt-in

Default stays **on**. `--no-locator-cells` turns off all three parts together — gutter, legend and the
JSON cell payload — because they are one feature and a half-on state has no use.

`--locator-cells` and `--no-locator-cells` are **mutually exclusive**; passing both is a clean exit 2
naming both flags, rather than one silently winning.

With it off, `_framing`'s `gutter` reserve is **0**, so the geometry gets the pane's full drawable
rect back. That is the visible win beyond the labels disappearing.

### 3.3 Fainter labels

`LOCATOR_LABEL` goes from `(140,140,140)` to `(105,105,105)` — clearly subordinate to the geometry
while still legible on the current black background.

**Provisional.** `move-the-preview-background-off-pure-black-to` changes `BG` to `#404040`, and 105 is
tuned against black. The final value is picked on the render ladder that item needs anyway; this spec
does not pin it. `dev/docs/rationale/preview.md` records that deriving a preview constant from a
contrast target produced two wrong answers before the owner picked one off a ladder, so the same
applies here.

### 3.4 `--json` stays meaningful in both modes

`--json` currently carries nothing but the cell map, so switching the locator off would empty it. It
keeps a payload either way:

**Locator on** (default) — unchanged except the key rename:

```json
{"image": "...",
 "locator": {"cols": 12, "rows": 12},
 "actors": {"Pillar": {"panes": {"Top": {"cell": "D4", "span": "C3–E5"}}, "hidden": false}}}
```

**Locator off** — the addressing drops out, the visibility answer stays:

```json
{"image": "...",
 "actors": {"Pillar": {"hidden": false}}}
```

`_collect_cells` takes `n=None` in that mode and returns an empty `cell`/`span`, but still computes
`hidden` the same way it always does — a real answer to a real question ("did this actor draw
anything?"), not a stub. The CLI omits `cell`/`span` rather than emitting empty strings.

**`hidden` answers the image that render actually wrote, not an abstract fact independent of the
locator.** Under `--faces wire` it stays identical on/off (`_collect_cells`'s `drew` is every actor
with points, never touching pixel positions). Under `--faces textured` it is **not** guaranteed to
agree: `--no-locator-cells` drops `_framing`'s `gutter` reserve to 0 (§3.2), which shifts `to_pxf` for
every point, which can move which face wins a pixel's depth test and so change `_face_is_occluded`'s
verdict — measured, a real divergence (3/90 in a size/view sweep; board item
`locator-on-vs-off-can-disagree-on-hidden-under`). Both answers are honest about the image each mode
actually rendered; whether cross-mode agreement is a real requirement is open — see this item's
`questions/cross-mode-hidden-stability-under-faces-textured.md`.

The two shapes are distinguished by the presence of the `locator` key, so a script can branch on it.

**`hidden` is not promised to agree across the two modes (owner, 2026-08-30).** It answers *the image
this render actually produced*. Turning the locator off drops the gutter reserve (§3.2), which shifts
the framing and therefore the depth buffer, so under `--faces textured` an actor's occlusion verdict
can differ between a locator-on and a locator-off render of the same scene — measured at 3 divergences
in 90 render pairs. Both answers are correct about their own image. `--faces wire` is unaffected: its
`hidden` comes from `set(geom.actor_points)` and never touches the projection. Accepted cost, recorded
in board item `locator-on-vs-off-can-disagree-on-hidden-under`; forcing agreement was considered and
rejected because it would make a locator-on filled render's `hidden` stop describing its own image.

### 3.5 Settled details

Everything below is decided so the implementer chooses nothing (owner, 2026-08-30):

- **All three verbs.** `actor preview`, `stash preview` and `prefab preview` all call
  `render_actors_to_out`, so all three get both flags and identical behaviour.
- **`breakdown` is unchanged**: the locator rides **pane 0 only**, as today. Per-actor panes get no
  gutter. (The sibling gridline item deliberately differs — gridlines ride *every* pane, because a
  ruler is most useful on a pane zoomed to one brush, whereas an address for the whole scene belongs
  on the scene pane.)
- **`quad` is unchanged**: all four panes carry a gutter, iso included. The address is image-space, so
  it is as meaningful on the iso pane as anywhere.
- **stderr header** reads `locator: 12×12 columns A–L, rows 1–12`.
- **JSON key** is `"locator"` — it holds `{cols, rows}`, not a list of cells.
- **The "no cell for X (no projectable geometry)" note** is suppressed with the locator off: there are
  no addresses for it to be missing from.
- **Degenerate actors stay omitted** from `--json` in *both* shapes, exactly as today — an actor with
  nothing to project contributes no row.
- **`span`** stays `null` in JSON and omitted from the legend line when the AABB is a single cell.
- **Empty actor set** → `{"image": …, "locator": {…}, "actors": {}}`, and nothing is drawn: the
  renderer returns before the gutter block when the scene has no points.
- **Error text** — `--locator-cells and --no-locator-cells are mutually exclusive`, and
  `--locator-cells must be in [1, 52], got 0`.

## 4. Surface

**`uedcli/preview.py`** — the renames in §3.1; the section comment (drop "Owner-ruled 2026-08-02,
LOCKED", which this supersedes); `_collect_cells` gains the `n=None` path; the `cells_out` fill moves
out from under the `if locator is not None` guard so `hidden` is collected in both modes. The renderer
**already** accepts the parameter as `int | None` with None meaning off, so no new plumbing is needed —
only the CLI never passes None today.

**`uedcli/cli/parsers/_arguments.py`** — replace the `--grid` argument with `--locator-cells` and
`--no-locator-cells`, both with real `help=`.

**`uedcli/cli/rendering.py`** — resolve the two flags into one `int | None`; the mutual-exclusion and
range checks; gate the legend on the locator being on; `_grid_json` → `_preview_json` with the two
shapes.

**`docs/usage.md`** — the synopsis line, the addressable-grid bullet, the `--grid` bullet, the `--json`
bullet, and the two "find it by the grid cell reported on stderr" pointers in the annotate section.
Required in the same change (`CLAUDE.md`: user-facing docs stay current with the CLI).

**`docs/leveldesign/general/design-craft.md`** — the "addressable grid" bullet, which also names
`--grid N`. Missed in the original list (spec bug, not an oversight in the build); it documents CLI
behaviour, not new craft knowledge, so it needs no separate owner approval.

**Not touched:** `dev/docs/architecture.md` and `dev/docs/rationale/preview.md` — §5.

## 5. Two dev/docs files go stale — do not edit them here

Both describe this feature as always-on at `--grid 12`:

- `dev/docs/architecture.md` "Preview internals".
- `dev/docs/rationale/preview.md` — its whole "The addressable grid's default density is `--grid 12`
  (agent choice)" section is the rationale for a flag that no longer exists under that name, and its
  framing of the grid as always-on is superseded.

`CLAUDE.md` forbids creating, editing or rewording anything under `dev/docs/` outside the board without
the owner's explicit yes. Proposed replacement text is parked in
`questions/dev-docs-updates-for-the-locator-rename.md`; the build does not touch these files until that
is answered. The 2026-08-02 always-on ruling may also have a `direction/` home — leave it alone and
raise it there too.

## 6. Tests

- **Default is on** — a render with no flags draws gutter pixels in `LOCATOR_LABEL` and prints the
  legend to stderr.
- **`--no-locator-cells`** — no gutter pixel anywhere in the band, no legend on stderr, and the
  geometry occupies the wider drawable rect (assert the framing gained the gutter back rather than just
  that labels are absent, since only the second catches a reserve left in by mistake).
- **Mutual exclusion** — both flags together exits 2 naming both.
- **Range** — `--locator-cells 0` and `53` exit 2 naming the value; `1` and `52` are accepted.
- **`--json` both shapes** — locator on carries `locator` + per-pane `cell`/`span`; locator off omits
  `locator` and every `cell`/`span` but still reports `hidden`, and `hidden` is **identical** between
  the two runs for the same scene (the property that makes the reduced form honest).
- **Colour** — `LOCATOR_LABEL` is pinned so the value is changed deliberately, not drifted into.
- **`--grid` is gone** — passing it is an unknown-argument error, not a silent no-op.
- Existing cell-math tests in `test_preview.py` are unaffected by design: the renames leave
  `_cell_of_pixel`/`_actor_cells`/`_col_label` untouched.

**Two committed fixture sets must be regenerated, and neither is optional:**

- **`uedcli/tests/fixtures/parser_baseline/`** — `help.json` and `action_tree.json` characterize the
  live parser, so replacing `--grid` with two new flags invalidates both. Regenerate with
  `python -m uedcli.tests.parser_baseline`; a failure never rewrites them by itself. Check the diff
  mentions no flag other than the ones this change touches.
- **`uedcli/tests/fixtures/preview_wire_golden_{iso,quad}.png`** — byte-compared wireframe renders that
  include the gutter labels, so the `140 → 105` colour change diverges them. Bless with
  `UEDCLI_BLESS_GOLDEN=1`. **Before blessing, diff the pixels and confirm every changed pixel is
  exactly `(140,140,140) → (105,105,105)`** — the goldens are the primary guard against a fill, depth
  or cull regression leaking into `wire`, so blessing them blind would discard that guard. (Measured on
  the real change: 1656 px iso, 5760 px quad, all of them that one substitution and no geometry pixel
  moved.)

## 7. Rejected

- **Removing the feature** (the item as filed) — refuted by the spike; it would delete the only working
  name↔image channel `single`/`quad` have.
- **Opt-in rather than opt-out** — considered and reversed by the owner on 2026-08-30. On by default is
  what makes an agent that does not know to ask for it still able to read the render.
- **`--cells`** — too generic; says nothing about what the cells are for, and reads as a geometry
  subdivision in a level-editing tool.
- **`--index`** — 959 existing uses of "index" in the tree (poly index, array index). The collision is
  worse than the brevity is worth.
- **`--region` / `--marker`** — both taken: `--frame` regions and point-actor markers.
- **`--coords`** — actively misleading; the address is never a world coordinate, which is the one thing
  the feature's docs go out of their way to say.
- **Splitting the off-switch in two** (separate opt-outs for the painted gutter and the legend/JSON) —
  one feature, one switch. The spike's control arm shows the readback carries value alone, but nobody
  has asked for that split and it doubles the flag surface.
- **`--json` degrading to `{image}`** with the locator off — the empty-object shim the "no silent
  half-answers" convention forbids. §3.4 keeps a real answer instead.
