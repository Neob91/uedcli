# Two `dev/docs/` files describe the grid as always-on `--grid 12` — may I update them?

## Context

The locator rename (`spec.md`) deletes `--grid` and makes the feature opt-out. Two files outside the
board describe it in the old terms and would be left wrong. `CLAUDE.md` forbids editing anything under
`dev/docs/` outside the board without your explicit yes, so nothing here is touched until you answer.

1. **`dev/docs/architecture.md`, "Preview internals"** — describes the addressable grid as always on.
2. **`dev/docs/rationale/preview.md`** — its whole final section, "The addressable grid's default
   density is `--grid 12` (agent choice)", is the reasoning for a flag that no longer exists under that
   name, and it opens "The always-on coordinate grid (owner-ruled 2026-08-02)".

There may also be a `direction/` topic carrying the 2026-08-02 always-on ruling. I have not gone
looking, and I have not touched `direction/`.

## Proposed edit

**`architecture.md`** — minimal: swap `--grid N` for `--locator-cells N` and "always on" for "on by
default, off with `--no-locator-cells`". No restructuring.

**`rationale/preview.md`** — retitle the section to "The locator grid's default density is
`--locator-cells 12` (agent choice)" and change its opening sentence to:

> The locator grid (owner-ruled 2026-08-02 as always-on; made opt-out and renamed 2026-08-30) leaves
> the DEFAULT cell count to us.

The rest of that section — why 12, the rejected 8/16/26, the rejected world-space cell — is unaffected
and stays as written. Its `Refs` line needs the renamed symbols (`_draw_locator_gutter`,
`_LOCATOR_MAX`, `_locator_legend_lines`).

The section does **not** need the spike's result folded in: that belongs to the item, not to the
density choice.

Alternatives if you would rather not: leave both files as-is and accept they are stale, or have me
delete the `rationale/preview.md` density section outright rather than reword it.

## Answer

<!-- Empty = open. Write the decision here. -->
