# `actor preview` param cleanup — consolidate `_preview_opts`

**Status: BUILT 2026-07-24** (`a97573383`; suite green) — spec revised after two cold reviews, then
shipped. The flag surface now lives in `docs/usage.md` (the CLI reference) and the durable rationale in
`decisions.md` `2026-07-24 19:01 UTC`; this file is ephemeral and may be deleted. Corrections from the
cold reviews are marked `[R]` inline (the point-actor pane framing was the substantive fix).
**Decisions ledger:** a `decisions.md` entry dated with this spec is the durable record of the
choices + rejected alternatives below.
**Code refs are symbol-anchored** (line numbers drift): `cli.py::_preview_opts`,
`dispatch.py::_render_actors_to_out` / `_render_breakdown_grid`, `preview.py::render_brushes_pgm`.

---

## 1. Motivation

`actor preview`'s flags live in one shared helper, `cli.py::_preview_opts`, reused by **three verbs**:
`actor preview`, `stash preview`, `prefab preview`. That helper carries **17 flags** with three latent
problems:

1. **Layout is two booleans that should be one choice.** `--single` + `--breakdown` + the implicit
   quad default are three values of one axis, with no mutual-exclusion group. `--breakdown` silently
   overrides `--single`/`--focus`/`--zoom`; `--single --breakdown` is accepted and one just wins.
2. **The zoom trio hides combination rules.** `--zoom BRUSH[:IDX]`, `--zoom-region X0..Z1`,
   `--zoom-factor N` interact by undocumented precedence (`_render_actors_to_out`): region beats zoom;
   factor modulates *only* zoom and is a silent no-op for region and when there is no target.
3. **Three near-identical overlay booleans.** `--show-collision` / `--show-light-range` /
   `--show-sound-range` are one comma-set wearing three flag hats.

Plus two smaller warts: `--out` was **required** (fixed this session — now optional w/ a temp
default), and `--png`'s help is **stale** ("also writes a PNG *next to* `--out`" — the code *replaces*
the extension and writes PNG *instead*).

This is a **breaking CLI change across three verbs**. The tool is LLM-facing with a small footprint,
so the precedent (`--zoom-poly`→`--zoom`, `--class` removal, `--split` removal — `decisions.md`
2026-07-23 / 2026-07-19) is a **clean rename with a helpful migration error**, not a deprecated alias.

## 2. The target flag surface

Net **17 → 13** flags, and every hidden-interaction rule removed. Grouped:

| Cluster | Was | Becomes |
|---------|-----|---------|
| Layout      | `--single` (bool), `--breakdown` (bool), implicit quad default | **`--layout {quad,single,breakdown}`** (default `quad`) |
| Framing     | `--zoom BRUSH[:IDX]`, `--zoom-region X0..Z1`, `--zoom-factor N` | **`--frame TARGET`** + **`--frame-tightness N`** |
| Overlays    | `--show-collision`, `--show-light-range`, `--show-sound-range` | **`--show collision,light-range,sound-range`** (comma-set) |
| Output      | `--out PATH` (required), `--png` | `--out PATH` (optional, temp default — done), `--png` (kept; help fixed) |
| Untouched   | `--view`, `--iso-angle`, `--brush-colors`, `--annotate`, `--focus`, `--highlight`, `--size` | unchanged |

### 2.1 `--layout {quad,single,breakdown}` — default `quad`

Replaces `--single` and `--breakdown`. One choice ⇒ mutual exclusion for free, no silent-override
surprises.
- `quad` (default) — the 2×2 Top / Front / Iso / Side grid (`preview.render_quad_pgm`). **Current
  behavior preserved** — the default does *not* flip to breakdown (Andrzej's call, 2026-07-24: guards
  against pane explosion now that point actors also get panes — §2.5).
- `single` — one view, selected by `--view` (`preview.render_brushes_pgm`).
- `breakdown` — the per-pane grid (§2.5).

`--view` still selects which view `single`/`breakdown` render; it is ignored by `quad` (which shows
all four), exactly as today.

### 2.2 `--frame TARGET` + `--frame-tightness N`

Replaces the zoom trio. **`--frame` is the single framing input**, so the "which of the three wins"
rules disappear. It accepts EITHER form:
- a **selector** — `BRUSH` (frame that actor's whole AABB) or `BRUSH:IDX` (frame one poly, the
  `brush poly find` selector). A multi-index / `:all` value is an error (use `--highlight` for a set),
  same as today's `--zoom`.
- an **explicit world AABB** — six comma-separated numbers `X0,Y0,Z0,X1,Y1,Z1` (frame exactly that
  box). Replaces `--zoom-region`'s `nargs=6`; one comma-joined token keeps `--frame` a single value.

`--frame-tightness N` (renames `--zoom-factor`, default `0.8`, range `[0,1]`): interpolates the frame
between the whole-set extent (`0` = no zoom) and the target (`1` = tightest). It applies to a
**selector** frame only; an **explicit AABB** is framed exactly (tightness is a no-op for it) — the
same rule `--zoom-region` had, now named so the pair reads together. No `--frame` ⇒ both are no-ops.

Disambiguation rule (selector vs AABB): a `--frame` value that is **six numeric comma fields** is an
AABB; anything else is a selector. (A brush literally named `1,2,3,4,5,6` is not a real actor name —
names are identifiers — so there is no ambiguity in practice.)

`[R]` **Load-bearing parser dependency:** a `--frame` AABB with a leading-negative coordinate
(`-512,0,0,512,0,256`) only parses because `cli.py::_CoordArgumentParser._parse_optional` treats any
token matching `_COORD_TOKEN` (`^[-+]?[0-9.]+(,…)*$`, arbitrary-length comma list) as a *value*, not
an option — otherwise argparse would reject it as an unknown flag. The 6-field form matches that regex,
so it Just Works, but the design silently *depends* on it. **Add a regression test** for a
negative-leading 6-field `--frame` value (it is non-obvious and load-bearing). The `--frame=…` form is
also safe if a caller prefers it.

### 2.3 `--show collision,light-range,sound-range`

One comma-set (union), matching the tool's existing idiom (`--annotate`, `--folder`). Members:
`collision` (faint red collision cylinder of colliding point actors), `light-range` (orange
`25·(LightRadius+1)` sphere), `sound-range` (blue `25·(SoundRadius+1)` sphere). Absent/empty = draw
none (today's default). An unknown member errors naming the offending token (CLI rule). Multiple
`--show` union (like `--annotate`).

### 2.4 `--out` (done) + `--png` (help fix only)

`--out` is now optional with a `uedctl-preview-*` temp default and always prints the absolute written
path — **already implemented this session** (`cli.py::_preview_opts`, `dispatch.py` mktemp branch).
This spec only *records* it.

`--png` is **kept** as the explicit "write PNG (via Pillow)" switch — it is **not** replaced by
extension-inference, because with `--out` optional there is no path to infer a format from when `--out`
is omitted. Behavior unchanged (PNG *instead of* PPM: `--out`'s extension is forced to `.png`, or the
temp file is minted `.png`). Only the **stale help/doc is fixed** to say "writes PNG instead of raw
PPM," dropping the inaccurate "also … next to `--out`."

### 2.5 `breakdown` semantics — finalized (the substantive design)

`breakdown` is defined as **"a layout that iterates `--focus` over each renderable actor, one pane per
actor, laid into a near-square `ceil(√N)` grid,"** with pane 0 the whole-scene CSG overview.

- **`--annotate` needs no special reconciliation** — but for TWO distinct reasons, one per kind:
  - *Poly indices* are scoped by the **existing focus rule**: `--focus X` restricts on-face indices to
    X (`preview.py` `_scene_geometry`: `show_idx = show_idx and (is_focus_brush or is_hi)`). breakdown
    sets `focus=<this pane's actor>`, so `--annotate`'s poly selectors draw only that pane's indices;
    `--highlight` still overrides (a highlighted poly stays numbered in every pane).
  - `[R]` *Names* are **not** scoped by focus at all — `_scene_geometry` gates names on `draws_name`
    alone, never on `focus_cf`. In breakdown, on-geometry names need `not hybrid` and legend names need
    `draw_legend`, but breakdown renders `color_by_csg=True` (⇒ hybrid) with `draw_legend=False`, so
    **all** name rendering is suppressed regardless of `--annotate`'s `name` selector. That — not the
    focus rule — is why names don't leak across panes. **This distinction matters:** if breakdown ever
    re-enables its legend, the `name` selector would suddenly draw and the focus rule would NOT contain
    it. The point stands today: **one composition, no breakdown-specific `--annotate` branch.**
- **Pane 0 (the SCENE overview) is fixed to `labels="none"`** — a plain spatial CSG map; the per-actor
  panes carry all detail. It does **not** honor `--annotate` (Andrzej's call, 2026-07-24). No legend
  (the 2026-07-24 05:27/06:43 removal stands).
- **Point actors now get their own pane each — NEW.** This changes the 2026-07-23 "point actors get
  **no** pane of their own" stance. Each point actor gets a captioned pane: its marker/sprite,
  focused + zoomed to it, name captioned — plus any `--show` overlay that applies to it (e.g. a
  light's `light-range` sphere). A point actor has no polys, so on-face poly annotation is simply
  absent in its pane. This is consistent with the 2026-07-24 direction: **identify actors via
  captioned panes, not a legend.**
  - `[R]` **Framing (do NOT reuse `_world_aabb([point])`).** The brush loop frames each pane with
    `region = _world_aabb([b], render_data)` — but for a marker-only point with no resolvable sprite
    extent and no `--show` overlay, `point_extent` is `0.0`, so `_world_aabb` returns a **degenerate
    zero-size box**; `_framing` then falls back to a 1-unit window and maps the marker to pixel
    `(pad, size-pad)` — **jammed in the bottom-left corner, halo half-clipped**, not centered. The
    non-breakdown `--zoom` path dodges this only because `_render_actors_to_out` adds a `±16` world
    margin; the per-pane loop adds none. **So a point pane must frame a synthesized non-degenerate box
    — `Location ± a fixed world margin`** (reuse the `m=16` margin, or a slightly larger `K` so a small
    `--show` sphere still fits) — never `_world_aabb([point])`. **Regression:** a lone point actor's
    breakdown pane centers its marker (not in a corner).
  - **Pane order:** pane 0 (SCENE), then one pane per actor in the actor-set order — brushes and point
    actors intermixed as they appear (no brushes-then-points regrouping; keeps ordering predictable
    from `actor find` output).
  - **Pane-count caveat:** including point actors makes a whole-level breakdown produce *more* panes.
    The existing `_BREAKDOWN_WARN_PANES` (16) stderr warning already covers this and now counts point
    panes too; its message stays "consider a subset."
- **Stale docstring corrected.** `dispatch.py::_render_breakdown_grid`'s outer docstring still claims a
  pane-0 "name-only LEGEND … every brush AND point actor, so no name escapes" — that legend was
  deleted 2026-07-24 and point actors were anonymous markers until this change. Rewrite it to match:
  no legend; every actor (brush or point) identified by its own captioned pane.

## 3. Migration errors (not silent removal)

Each removed spelling gets a `cli.py::_RemovedFlag` action so an old invocation errors with a pointer
to the new flag (and argparse prefix-abbrev can't resurrect it), matching the `--class` precedent:

| Removed | Error points at |
|---------|-----|
| `--single`         | `--layout single` |
| `--breakdown`      | `--layout breakdown` |
| `--zoom`           | `--frame` |
| `--zoom-region`    | `--frame X0,Y0,Z0,X1,Y1,Z1` |
| `--zoom-factor`    | `--frame-tightness` |
| `--show-collision` / `--show-light-range` / `--show-sound-range` | `--show collision,light-range,sound-range` |

## 4. Touch list

- **`cli.py::_preview_opts`** — the whole flag rewrite + the `_RemovedFlag` migration stubs. (One
  helper ⇒ all three verbs update together.)
- **`dispatch.py`** — `_render_actors_to_out` (read `args.layout`/`args.frame`/`args.frame_tightness`/
  `args.show`; collapse the three-way branch to a `match args.layout`); `_render_breakdown_grid`
  (iterate point actors into panes with the synthesized framing box above; fix the docstring; **fix the
  stderr summary line** `f"breakdown: {len(brushes)} brushes, …"` — it hardcodes "brushes" and now
  undercounts/mislabels once point panes exist — and the `_BREAKDOWN_WARN_PANES` count covers point
  panes too); the `--show-*` reads (`_preview_render_data`/`_resolve_point_render`) → parse the
  `--show` comma-set once; `_resolve_zoom` → reused under `--frame` (selector path) with the AABB path
  added. `[R]` **Rename the reused error strings** — `_resolve_zoom` raises `"--zoom: … is a point
  actor"` / `"--zoom BRUSH:idx frames ONE poly"` and `_render_actors_to_out` raises `"--zoom-factor
  must be in [0,1]"`; verbatim reuse would name just-removed flags (violates "errors name the real
  flag"). They become `--frame` / `--frame-tightness`.
- `[R]` **Defensive attribute reads.** The rewrite MUST read the new fields via `getattr` with defaults
  (`layout="quad"`, `frame=None`, `frame_tightness=0.8`, `show=""`), because `stash`/`prefab preview`
  test namespaces (below) are hand-built `SimpleNamespace`s that omit fields; a plain `args.layout`
  would `AttributeError`. (Mirrors the existing `getattr(args, "zoom", None)` guards.)
- **`docs/usage.md`** — the `actor preview` synopsis + the flag descriptions (and the `--png` wording
  fix); the shared block also documents `stash`/`prefab preview`.
- **`decisions.md`** — append the durable entry (choices + rejected alternatives).
- **Tests** — enumerated, because the old field names are duplicated across several hand-built arg
  objects:
  - `test_cli.py` — parser tests exercising the old flags → rewrite to new spellings; **add
    `_RemovedFlag` error tests** for each removed flag; add the negative-leading 6-field `--frame`
    regression (§2.2).
  - `test_actor_preview.py` — `_prev` helper's field names; the `stash preview` and `prefab preview`
    `SimpleNamespace` builders in the same file; and **`test_it_gives_point_actors_no_breakdown_pane`**
    — this asserts the *removed* stance (a lone point → one SCENE pane only) and will fail; rewrite its
    assertion + name + comment to the new behavior (rename to
    `test_it_gives_each_point_actor_a_breakdown_pane`) and add the "lone point pane centers its marker"
    regression (§2.5).
  - `test_stash_dispatch.py::_preview_stash_args` / any `test_dispatch.py` preview namespace — update
    to the new fields (or rely on the defensive `getattr` defaults above; still update for clarity).
- **Memory** — `uedctl-preview-default-breakdown` says "pass `--breakdown` by default". `[R]` The edit
  to `--layout breakdown` **lands in the SAME commit as the flag rename**, not a follow-up — the
  `_RemovedFlag` error is the safety net, but the window where an agent following that memory errors on
  every preview should be zero.

## 5. Rejected alternatives

- **Flip the default to `breakdown`** — Andrzej's stated preference is breakdown, but with point actors
  now getting panes a default whole-level breakdown explodes; default stays `quad`, breakdown is
  opt-in (`--layout breakdown`). *(2026-07-24)*
- **Drop `--png`, infer format from `--out` extension** — incompatible with the now-optional `--out`
  (no path to infer from when omitted). `--png` stays the format switch.
- **Deprecated aliases for the renamed flags** — LLM-facing tool, small footprint: a clean rename +
  `_RemovedFlag` error beats carrying two names (matches `--zoom-poly`/`--class`/`--split`).
- **A breakdown-specific `--annotate` mode** — unnecessary; `--annotate` composes through the existing
  `--focus` rule with zero new branching.
- **Variable-span breakdown tiles for point actors** — same square-buffer constraint already rejected
  for brushes (`decisions.md` 2026-07-23 12:22); point panes are square cells like the rest.

## 6. Open questions

None blocking. Design-detail calls made in-spec (point-pane framing box size, pane ordering,
selector-vs-AABB disambiguation) are flagged for the cold reviewers to challenge.
