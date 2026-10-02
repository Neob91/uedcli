# v2 defaults cache: pre-render object-refs at decode, or cache the compact tables?

## Context

The v2 defaults blob needs object-ref defaults (e.g. a `Texture=Class'Package.Name'` default) to
render buf-less on a warm hit. Two ways (spec §9):

- **Recommended — pre-render, drop the tables.** Store each default's object ref as its final
  `Class'Package.Name'` text at decode time. `render_object_ref` output is style-independent (no float
  formatting), so freezing it is safe across CLI vs T3D `style`. This removes the need to cache the
  compact name/import/export tables — the largest primitives — so the v2 blob stays small.
- **Alternative — cache the compact tables.** The object-ref renderer runs warm off the cached tables;
  nothing is baked at decode. More faithful, but larger blobs and a more complex warm path, and the
  render consumers never need the ref numerically.

Either way v2 bumps `SCHEMA_CACHE_VERSION` to 3 and refreshes the frozen golden. This is the only real
fork in the item; the rest (per-package defaults tags, local enum/struct tables, the new enumerator,
cross-package resolution by chaining `load_package_schema`, the third `.dflt` blob) follows the
module's established "cache per-package, recompose in-process" design and is agent-decidable.

## Answer

<!-- Empty = open. -->
