# Diagonal-wall helper: a `brush shear` filter, a dedicated diagonal-wall builder, or both?

## Context

The motivating flow is building a grid-aligned 45° wall without hand-computing corner coords. Two
shapes:

- **`brush shear` filter (recommended).** `brush shear -|FILE --face +Z --by DX,DY,DZ` displaces one
  end face of any piped brush by a grid delta — the exact manual `brush vertex move` flow, one verb.
  General (any prism end, any brush), composes with `brush build`, and reuses the `--facing`
  vocabulary. Turns a box into a parallelepiped (a leaning/diagonal wall) staying watertight and
  on-grid.
- **A diagonal-wall builder.** `brush build <diagonal-wall>` taking two grid endpoints + thickness +
  height, emitting the slanted wall directly. Reads well for the one wall case, but it is a bespoke
  parametrized shape that only builds that one thing, and its endpoints/thickness/height re-do what
  cube + shear already give.
- **Both.** More surface to build, document and keep true.

Recommendation: the `brush shear` filter only. It automates the described workflow, generalises
beyond the one wall, and fits the existing generator/filter family.

## Answer

<!-- Empty = open. -->
