# Spec: `actor preview` ergonomics (was `brush preview`)

**Status:** ephemeral design scratch. Durable record → `docs/usage.md` (CLI reference) +
`architecture.md`; load-bearing choices → `decisions.md` (2026-07-21 12:06/12:22, and the 13:42
confirmations). Goes stale once built.

**Board:** `to-plan.md` (specced + two-cold-reviewer-gated + Andrzej-confirmed 2026-07-21). Overlaps
the `[implement] p3` "brush preview rendering improvements" and "Multi-actor sub-object …
BRUSH:SELECTOR" backlog items (reconciled below).

**Confirmed by Andrzej 2026-07-21 13:42:** unified `--from-t3d FILE…|-` idiom (also on `stash
capture`); `--zoom-poly` selector-only (drop bare-int); zoom does NOT highlight; §5 (bbox bridge)
**dropped**; add `--zoom-factor`.

> **⚠ VERB RENAMED (2026-07-21):** `brush preview` → **`actor preview`** — see
> `specs/2026-07-21-actor-preview.md` (rename + point-actor rendering + `--show-collision`). Every
> `brush preview` below now means `actor preview`; the two specs are built together.

---

## Architecture note (load-bearing)

Two UNRELATED preview systems; do not conflate:
1. **`actor preview`** — orthographic **wireframe** PPM renderer in **`uedcli/preview.py`**
   (`render_brushes_pgm`/`render_quad_pgm`/`render_brush_pgm`), configured by `_preview_opts`
   (`cli.py:130`), driven by `_render_actors_to_out` (`dispatch.py:379`). **The only renderer this
   spec touches.** No tiers.
2. **`level preview --native`/`--game`** — different verb (`preview_native.py` solid rasterizer;
   `preview_game.py` in-engine screenshots). Neither draws wireframe. **Out of scope.**

**Shared surface:** `_preview_opts` is shared by `actor preview` (`cli.py:725`), `stash preview`
(`cli.py:1132`), `prefab preview` (`cli.py:1176`); all funnel through `_render_actors_to_out` →
`render_brushes_pgm`. Each change below is tagged **shared** (all three) vs **brush-only**.

---

## 1. STDIN target set + unified `--from-t3d` T3D input  *(brush-only for stdin; cross-verb for `--from-t3d`)*

`actor preview`'s default target is a **NAME set** — from args (`Wall1 Wall2`) or from stdin (`-`, a
newline name list): `actor find --folder castle.stairs | actor preview -`. Route through
`_resolve_target_names` (`dispatch.py:144`) for `-` / empty-stdin-no-op / BOM handling; relax `names`
to `nargs="*"`, `-` the sole name source (mixed args rejected), empty stdin → exit 0.

**Unified `--from-t3d` (Andrzej 2026-07-21).** Replace any bespoke T3D-stdin switch with one flag,
**`--from-t3d <FILE…|->`**, that reads the target from one-or-more T3D files, or `-` for a T3D snippet
on stdin: `brush build spiral | actor preview --from-t3d -`. This is a **T3D MODE** distinct from name
mode:
- `--from-t3d` is **mutually exclusive with the name source** (args and `-`-names). Present ⇒ T3D
  mode; the parser errors on `actor preview Wall1 --from-t3d x.t3d`.
- **`-` is the sole value if present** — no mixing stdin with files (`--from-t3d - a.t3d` rejected),
  per the `-` convention.
- **Multiple files concatenate** their snippets in order (new small capability — define + test).
- `nargs="+"` on the option: since T3D mode and name mode are exclusive, the greediness is contained;
  document that `--from-t3d` consumes following file tokens.

**Cross-verb consistency — migrate `stash capture` to the same idiom.** `stash capture` today has
`--from-t3d FILE` (single) + `--from-stdin` (bool) in a mutually-exclusive group (`cli.py:1113-1117`).
Collapse to the same **`--from-t3d <FILE…|->`** (drop `--from-stdin`). This is a small breaking CLI
change to `stash capture` (+ its tests + `usage.md`), justified by one consistent T3D-input idiom
across verbs. **Supersedes the deferred `[spec]` "`stash capture -` (stdin)" backlog item** — this is
that capability, spelled the unified way. (`stash capture`'s `names` remain a subset selector against
the T3D source, unlike `actor preview` where T3D mode renders all snippet actors — each verb's
`names` = "subset of the source".)

## 2. `--zoom-poly` takes a `BRUSH:idx` selector (selector-only)  *(shared)*

`--zoom-poly` becomes a **`BRUSH:idx` selector** (the `<name>:<idx>` form `brush poly find` prints and
`poly align`/`poly set` consume), addressing a poly on ANY named brush — **not** `actors[0]`.
**Confirmed: no bare-int back-compat** — the old `--zoom-poly IDX` int form is dropped (clean break;
update its tests).
- **Reuse the EXISTING shared parser** `surface.parse_poly_selector` + `resolve_polys` (`surface.py`,
  already used by `poly set`/`align`). The BRUSH:SELECTOR-generalization backlog item's "generalize
  the parser" premise is stale for the poly case (the helper exists) — say so there.
- **Arity:** `--zoom-poly` frames ONE poly; a multi-index / `:all` selector value is a clean error
  naming the value (the set form belongs on `--highlight-poly`).
- **Error path:** `resolve_polys` raises `ValueError` naming the brush, but `actor preview` dispatch
  catches only `KeyError` (`dispatch.py:3039`) — wire the `ValueError` catch so no traceback reaches
  the user (name the value). A `BRUSH:idx` naming a brush not in the previewed set → clean named error.

## 3. Split `--zoom-poly` from `--highlight-poly`; zoom does NOT highlight  *(shared)*

Two fully-independent flags:
- `--zoom-poly BRUSH:idx` — **frames only** (zooms). **Confirmed: zooming no longer highlights** its
  target (a behavior change from today's conflation, `dispatch.py:381`).
- `--highlight-poly BRUSH:idx` — draws the poly **emphasized**, no effect on framing. **Repeatable**
  (append) and accepts the set form (`BRUSH:1,2`) so several faces highlight at once. Emphasis =
  **the brush's OWN CSG hue, made vivid + bolder** (not red) — see §4.

**Renderer-signature change (the real work):** today `highlight` is a bare `int` pinned to actor 0
(`dispatch.py:385` `actors[0].brush.polys`; `preview.py:248` `is_hi = (ai==0 and idx==highlight)`).
Thread a **collection of `(actor-name, poly-idx)`** through
`render_brush_pgm`/`render_brushes_pgm`/`render_quad_pgm` (`preview.py:215/222/309`) and resolve the
zoom AABB (`dispatch.py:385`) by name. Out-of-range index → clean named error (was a silent no-op).

## 4. Color brushes by CSG op (match UnrealEd)  *(shared — colors stash/prefab preview too)*

Color each brush's wireframe by `CsgOper` (additive/subtractive/mover distinct). Lands in `preview.py`
`render_brushes_pgm` (`preview.py:222`), reading the op via `_csg_oper(actor)` (`dispatch.py:554`,
`CSG_Add` default). On the shared render path ⇒ also colors `stash`/`prefab preview` (desirable).

**Palette CONFIRMED (Andrzej-provided UED brush-color legend, 2026-07-21).** Match UnrealEd's own
brush wire colors, keyed on the full brush classification (not just CsgOper) — the preview knows
PolyFlags, so color all six:

| Brush class | UED hue |
|-------------------|---|
| Subtracted        | yellow / gold |
| Added (solid)     | blue |
| Semi-solid        | pink |
| Non-solid         | green |
| Mover             | magenta / purple |

Classification: `CsgOper` (add vs subtract) refined by the effective solidity PolyFlags
(`PF_Semisolid`→pink, `PF_NotSolid`→green, on the ADD side), and mover (`_csg_oper`/mover-class)→
magenta. Read the op via `_csg_oper(actor)` (`dispatch.py:554`). **Red is NOT used** — freed (UED's
red is its *builder* brush, which we don't render); the highlight derives from the brush's own hue
(below) instead.

**Highlight = the brush's own hue, emphasized (Andrzej 2026-07-21).** A `--highlight-poly` target is
drawn in **its brush's CSG hue at full saturation + a bolder line**, NOT a separate red — so a
highlighted poly still reads as its own CSG type. **⚠ NOT literally "brighter":** on the WHITE
background, lightening a hue moves it toward white (loses contrast) and collides with the front/back
shade axis (back faces are already the lighter shade). So emphasis = **max-saturation same hue +
increased line weight** (and ignore the facing dim on the highlighted poly), which works on white and
stays orthogonal to the shade cue. Needs a **line-weight** parameter in the renderer (`preview.py`
`_line` highlights by color only today — a signature addition alongside the §3
`highlight`→`(name,idx)`-set change).

**Two-axis encoding constraint:** `actor preview` is **dark-on-white** (`preview.py:36`) and already
encodes facing by **shade** (front black / back grey, `preview.py:282-287`). Each hue above needs a
front/back **shade pair** (darker/lighter) so the facing cue survives, and every hue must stay legible
on a WHITE bg (UED's are tuned for a grey/black viewport — adapt luminance, keep hue). Pin the chosen
RGB pairs (and the highlight vivid+bold treatment) as a regression; the durable home for the UED hue
fact is `dev/docs/unrealed/rendering.md` (add with an evidence marker citing this legend, when §4 is
built). **One owner** for the `preview.py` color work with the "brush preview rendering improvements"
backlog item (filled faces / depth-sort / captions) — both edit the draw loop + palette; sequence,
don't double-pass.

## 5. `--zoom-factor <n>` — zoom tightness knob  *(shared)*

**New (Andrzej 2026-07-21).** A continuous framing-tightness control for a zoom target:
- `--zoom-factor 0` = no zoom — the target is shown at natural size within the whole-set frame (the
  current default framing).
- `--zoom-factor 1` = tightest framing that still keeps the target **fully in view** (fill the frame
  with the target + a small margin — today's `--zoom-poly`/`--zoom-region` behavior).
- Intermediate = linear interpolation between the two frames (whole-set extent ↔ target extent).

It **modulates** `--zoom-poly`/`--zoom-region` (the target), not a standalone framing. **Default
`0.8`** (Andrzej 2026-07-21) — a mostly-tight-but-not-flush frame when a target is given; with no
target it is a no-op (nothing to zoom toward). Lives on the shared helper (`_render_actors_to_out`) so
all three preview verbs get it.

*(The former §5 "feed `actor bbox` into `--zoom-region`" bridge is **DROPPED** — Andrzej 2026-07-21.
Auto-framing + `--zoom-poly` + `--zoom-factor` cover the cases; the different-set framing was niche
and unmotivated.)*

---

## Where each change lives (summary)

| Change | Surface | Key file(s) |
|--------------------------|-----------|-------------------------------------------------|
| §1 stdin names           | brush-only| `cli.py` (preview parser), `dispatch.py` branch |
| §1 `--from-t3d` unify     | cross-verb| `cli.py` (preview + `stash capture`), `dispatch.py` |
| §2 selector              | shared    | `dispatch.py` (`_render_actors_to_out`), `surface.py` reuse |
| §3 highlight split       | shared    | `preview.py` (`highlight` int → `(name,idx)` set), `dispatch.py` |
| §4 CSG color             | shared    | `preview.py` (`render_brushes_pgm` palette) |
| §5 `--zoom-factor`       | shared    | `dispatch.py` (`_render_actors_to_out`), `preview.py` framing |

## Testing

- §1 names: name-list stdin previews the subset; args still work; `-` sole name source; empty stdin →
  exit 0, no file.
- §1 `--from-t3d`: file(s) render; `--from-t3d -` renders a stdin snippet; multiple files concatenate
  in order; `--from-t3d` + names → clean mutual-exclusion error; `--from-t3d - a.t3d` → rejected.
  **`stash capture`**: same matrix; `--from-stdin` removal doesn't leave a dangling reference;
  existing capture tests migrated.
- §2: `BRUSH:idx` frames the right poly on a **non-first** brush; bad/out-of-range/`:all`/multi
  selector → clean named error, **no traceback** (assert dispatch catches `ValueError`); brush not in
  set → named error; old int-form tests removed/updated.
- §3: zoom-only frames WITHOUT highlighting (the behavior change); highlight-only; both on different
  faces; multiple `--highlight-poly` accumulate; highlight on a non-first actor renders.
- §4: additive + subtractive + mover render in three colors distinct from the red highlight AND
  preserving the front/back shade; palette pinned once chosen; **stash/prefab preview still render**
  (shared helper intact).
- §5: `--zoom-factor 0`/`0.5`/`1` produce the natural / interpolated / tightest frames around a
  `--zoom-poly` target; no target → no-op.

## Docs to update

- **`decisions.md`** — the confirmed calls (unified `--from-t3d`, selector-only, zoom≠highlight, §5
  dropped, `--zoom-factor`, `stash capture` migration).
- `docs/usage.md`: `actor preview` names/`--from-t3d`/`--zoom-poly`/`--highlight-poly`/CSG
  color/`--zoom-factor`; and `stash capture`'s new `--from-t3d <FILE…|->`.
- `docs/leveldesign/` preview-loop guidance.
- `architecture.md`: `preview.py` `highlight` signature + shared-surface note.

## Open questions

1. ~~Exact UED brush colors (§4)~~ **Resolved 2026-07-21** — the UED legend (table above); implementer
   picks the front/back shade RGB pairs adapted for the white bg and pins them as a regression.
2. Do `stash`/`prefab preview` want the §2/§3 selector+highlight surface too (shared makes it nearly
   free)?
