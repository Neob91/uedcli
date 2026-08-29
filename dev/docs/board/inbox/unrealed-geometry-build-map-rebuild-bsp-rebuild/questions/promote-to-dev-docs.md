## Context

`spec.md` in this item is a full reverse-engineered specification of UnrealEd's geometry-build
pipeline (`MAP REBUILD`/`BSP REBUILD`: `csgRebuild`, `bspBrushCSG`, `bspBuild`/`FindBestSplit`,
`bspOptGeom`, zone/portal assignment, bounds/collision hulls, on-disk `UModel` format, float32
fidelity requirements). It is built entirely from primary evidence (binary disassembly + live-editor
observation), explicitly excluding this project's own reimplementation as a source.

Per `CLAUDE.md`, new learnings about how UnrealEd functions belong in `dev/docs/unrealed/` — but
writing there needs your explicit yes first. Proposed: fold `spec.md`'s content into a new
`dev/docs/unrealed/geometry-build.md` (or merge relevant sections into the existing
`dev/docs/unrealed/commands.md`/`quirks.md` where they overlap), so it's discoverable the normal way
rather than buried in a board item.

Options:
1. Promote as a new `dev/docs/unrealed/geometry-build.md`, verbatim or lightly trimmed.
2. Leave it here in the board item (referenced by slug from wherever it's needed).
3. Something else (e.g. split — fold the confidence/open-questions parts into the board item's
   `rationale/`-style tracking, and only the settled facts into `dev/docs/unrealed/`).

## Answer

