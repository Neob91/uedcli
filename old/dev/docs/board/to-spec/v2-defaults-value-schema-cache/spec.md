# Spec — v2 defaults-value schema cache

DRAFT. Extends the persistent schema cache to the defaults-VALUE render path. One owner fork (§9).

## Goal

`actor prop get` and `actor find --prop` render a class's default property VALUES. The schema
(own-props) path is already cache-backed and buf-less on a warm hit (`schema_cache.load_package_schema
need_props=True`, `uprops.py:392`). But the defaults-VALUE path still does a full live
`load_package` per ancestor package to read raw DEFAULTS blocks and render them — so rendering
defaults re-parses the multi-MB `.u` even when the schema cache is warm. v2 caches the
defaults-render primitives per package so the whole defaults-value render is buf-less warm (the
review's HIGH-1 full fix).

## Current state — the defaults path is not cached

The discovery + own-prop primitives are cached (`schema_cache.py`, `SCHEMA_CACHE_VERSION = 2`,
`schema_cache.py:68`): `PackageSchema` holds `class_list`/`cmap`/`super_refs`/`abstract`/`own_props`.
`resolve_class_properties` (`uprops.py:351`) reads it warm.

The render path still loads the live `Package` (`buf`):

- `resolve_class_defaults` (`uprops.py:1198`) walks the ancestor chain, `load_package` per package
  (`uprops.py:1227`), and per class calls `class_default_tags` + `render_default_tag`.
- `class_default_tags` (`uprops.py:606`) reads the raw DEFAULTS tag list off `pkg.buf` at the UClass
  body tail.
- `render_default_tag` (`uprops.py:1116`) resolves enum names (`resolve_enum_names`, `uprops.py:758`),
  struct member trees (`struct_members`, `uprops.py:681`; `resolve_type_export`, `uprops.py:714`,
  which chains `load_package` on a foreign package, `uprops.py:740`), and object refs
  (`render_object_ref`, needs `pkg.names`/`imports`/`exports`).
- `resolve_class_default_tags` (`uprops.py:1161`) — the raw-tag variant `mapimport` uses — has the
  same live-load chain (`uprops.py:1186`).

There is no whole-package struct/enum enumerator (`enum_values` exists, `uprops.py:407`; no
`iter_structs`/`iter_enums`). `SCHEMA_CACHE_VERSION` is folded into the key + the `v<N>/` path and
guarded by a committed frozen golden (`tests/test_schema_cache.py`, `fixtures/schema_golden_fire_v2.marshal`).

## Design

Follow the module's load-bearing principle (`schema_cache.py:10`): **cache per-package primitives,
recompose cross-package in-process.** v2 adds a defaults blob per package holding what the render
needs; `resolve_class_defaults` recomposes the ancestor chain from the cached per-package tags,
never touching `buf` on a warm hit.

New per-package primitives to cache (spec §4.1b):

- **raw DEFAULTS tags per class** (`class_default_tags` output) — the sparse per-class defaults block;
- **local enum tables** (`enum_values` per local enum export) — for byte→name;
- **per-Struct member schemas** (`struct_members` output per local struct export) — for struct
  rendering;
- **compact name/import/export tables** — what the object-ref renderer and cross-package type
  resolution index against;
- a **whole-package enum/struct enumerator** (new — no `iter_structs`/`iter_enums` today) to populate
  the two tables above at decode.

Cross-package resolution (an imported enum/struct, or an object ref into a foreign package) is done
by **chaining `load_package_schema` on the foreign package** — the same "recompose in-process from
per-package blobs" move the schema union already uses — so no whole live `Package` is loaded.

Re-plumb the render consumers off the live `Package`/`buf` onto the cached primitives:
`resolve_class_defaults` / `resolve_class_default_tags` / `render_default_tag` / `struct_members` /
`resolve_type_export` / the object-ref renderer.

Mechanics:

- **Bump `SCHEMA_CACHE_VERSION` → 3** and refresh the frozen golden (`golden_bytes` must serialize the
  new defaults blob so a decoder/format change trips the test — `schema_cache.py:201`).
- Add the defaults primitives as a **third blob** (`.dflt`) beside `.disc`/`.prop`, loaded only by a
  `need_defaults=True` caller, so `class list` and a plain schema read never pay for it (the same
  split rationale as `.disc` vs `.prop`, `schema_cache.py:15-23`).
- Persist via the existing `marshal` + `_atomic_write` path; the footprint GC already caps total
  bytes (`SCHEMA_CACHE_MAX_BYTES`) and the larger defaults blobs are cited as the reason a cap is
  worth having (`schema_cache.py:73`).

### CLI / behaviour surface

No new verb, flag, or output. `actor prop get` / `actor find --prop` produce byte-identical text;
only the warm-run cost drops (no `load_package` on the defaults path). `cache clear` / `cache gc` /
`UEDCLI_SCHEMA_CACHE=off` cover it unchanged.

### The §9 open question — how to handle object refs (the one owner fork)

The compact name/import/export tables are cached ONLY so the object-ref renderer can produce
`Class'Package.Name'` warm. The alternative is to **pre-render each default's object ref to its final
text at decode time**, storing the string in the defaults blob and dropping the three tables entirely
— a much smaller v2 blob.

- **Recommended — pre-render, drop the tables.** `render_object_ref` output is style-independent (no
  float formatting — unlike other value types), so freezing it at decode is safe across CLI vs T3D
  `style`. It also removes the need to cache the (largest) tables.
- **Alternative — cache the tables.** More faithful (nothing baked at decode), but larger blobs and a
  more complex warm path. Only justified if a caller needs the raw ref numerically, which the render
  consumers do not.

## Edge cases & errors

- A corrupt DEFAULTS block: same as today — `class_default_tags`/render raise `SchemaError` (no
  fallback). The decode-time failure stores a `None`/sentinel per class exactly like `_decode_props`
  (`schema_cache.py:280`), so one corrupt class doesn't drop the package's defaults blob.
- An imported enum/struct whose owning package is off the search path → `SchemaError` naming the
  package (as `resolve_type_export` does now, `uprops.py:738`).
- A cache write failure stays a loud `CacheWriteError` at exit 2 (`schema_cache.py:363`); a
  corrupt/wrong-version blob is a miss (re-decode).
- `UEDCLI_SCHEMA_CACHE=off` bypasses read+write — the defaults render decodes live, byte-identical.

## Tests

- Warm-hit test: `actor prop get` / `actor find --prop` over a class with enum, struct, and
  object-ref defaults produces identical text with **no** `load_package` call on the defaults path
  (assert the buf-less path, mirroring the existing `need_props` warm test).
- Cross-package: a class whose default references an imported enum/struct/object renders warm via
  `load_package_schema` chaining, no live `Package`.
- Golden refresh: `test_frozen_golden_bundle_matches_fresh_decode` extended to the `.dflt` blob at
  `SCHEMA_CACHE_VERSION = 3`; a decoder/format drift trips it.
- Per-class corrupt-defaults sentinel: one corrupt class doesn't poison the package's defaults blob.
- Whichever §9 branch is chosen: if pre-rendered, assert the stored object-ref text equals the live
  render across both `style`s; if tables cached, assert the warm object-ref render matches live.

## Open questions

See `questions/`. One fork: §9 — pre-render object-refs to text at decode (drop the cached tables) vs
cache the compact tables.
