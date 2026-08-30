+++
priority = "p1"
kind = "docs"
summary = "leveldesign/ and usage.md are barely cross-linked"
+++

# leveldesign/ and usage.md are barely cross-linked

Only 2 links go FROM `docs/leveldesign/**` INTO `usage.md`, repo-wide:

- `docs/leveldesign/general/geometry-and-bsp.md:105` → `[usage.md](../../usage.md)` "Brush shape &
  surfaces"
- `docs/leveldesign/deusex/recipes/deusex-door.md:137` → `[`../../../usage.md`](../../../usage.md)`
  "for the full verb reference"

ZERO links go the other way (`usage.md` → any `leveldesign/**` page), despite
`docs/leveldesign/README.md` promising the craft guide is verb-family content "mapped onto the
verbs." An agent reading `usage.md` for a verb has no pointer to the matching craft page, and an
agent in `leveldesign/` has almost no pointer back to the verb it needs.
